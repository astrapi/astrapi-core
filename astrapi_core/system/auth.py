"""core/system/auth.py – WebAuthn/Passkey-Login für die UI.

Opt-in pro App (`app.yaml: auth.enabled`, siehe ui/app.py::create() und
ui/auth_middleware.py) -- ohne diesen Schalter bleibt eine App wie bisher
offen im LAN. Hintergrund/Entscheidung: [[E-003]] in entscheidungen.md.

Bevorzugt **Passkeys statt beliebigem WebAuthn**: Discoverable Credentials
(`resident_key=required`) + `user_verification=required` -- echte,
phishing-resistente Passkeys mit Konten-Picker statt Login-Formular.

Zusätzlich ein **Passwort-Login als Fallback**: Passkeys funktionieren nur
in einem sicheren Kontext (HTTPS oder `localhost`) -- solange eine App
(noch) nicht per HTTPS erreichbar ist (LAN-Deployment ohne TLS, siehe
Punkt 2 im 3-Punkte-Plan bei astrapi-admin), ist ein Passwort der einzige
nutzbare Weg. PBKDF2-HMAC-SHA256 (stdlib `hashlib`, keine neue
Abhängigkeit), 600.000 Iterationen (OWASP-2023-Empfehlung), einfache
Brute-Force-Bremse (5 Fehlversuche → 30s Sperre, global -- kein
Multi-User-Fall). **Wichtiger Unterschied zu Passkeys:** ein Passwort ist
ein geteiltes Geheimnis, das bei jedem Login über die Leitung geht --
über reines HTTP im Klartext mitlesbar. Passkeys übertragen nie ein
Geheimnis (Challenge-Response mit einem privaten Schlüssel, der das
Gerät nie verlässt). Das Passwort ist bewusst nur eine Übergangslösung
bis HTTPS steht, kein gleichwertiger Ersatz.

Ursprünglich Single-Owner-Modell wie der Rest der astrapi-Familie (keine
"users"-Tabelle, jeder Passkey gleichwertig für denselben Betreiber). Seit
astrapi-hub-Vault-Entscheidung "Multi-User astrapi-sync" additiv um echte,
unterscheidbare Nutzerkonten erweitert -- **vollständig rückwärtskompatibel**:
jede neue Funktion bekommt einen optionalen `user_id`-Parameter (Default
`None`), der intern auf einen impliziten, lazy angelegten "Default-User"
auflöst. Apps, die weiterhin nie ein `user_id` übergeben (z.B. astrapi-admin,
siehe [[E-003]]), verhalten sich exakt wie vor dieser Erweiterung -- nur
technisch als eine einzelne Zeile in `users` statt eines globalen
KV-Store-Handles geführt. Multi-User-fähige Registrierungs-/Einladungsrouten
liegen separat in `ui/multi_user_routes.py`, nur eingebunden bei
`app.yaml: auth.multi_user: true` (Default `False`).

Drei eigenständig verwaltete Tabellen (nicht Teil des generischen
Modul-CRUD-Systems, siehe system/db.py::register_table() -- Sessions/
Credentials/Users sind keine UI-verwalteten Listen):

- users            -- Nutzerkonten (id, username, display_name, eigener
  WebAuthn-User-Handle)
- auth_credentials -- registrierte Passkeys, je einem User zugeordnet
- auth_sessions    -- angemeldete Browser-Sessions, serverseitig per
  SHA-256-Hash abgleichbar (gleiches Muster wie Host-/Geräte-Token bei
  astrapi-sync/astrapi-admin: das Klartext-Token sieht nur der Client,
  in der DB steht nur der Hash), je einem User zugeordnet
"""
import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime, timedelta, timezone

import webauthn
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

SESSION_COOKIE_NAME = "astrapi_session"
CHALLENGE_COOKIE_NAME = "astrapi_webauthn_challenge"
SESSION_TTL_DAYS = 30
_CHALLENGE_TTL_SECONDS = 300

_DDL_USERS = """
    CREATE TABLE IF NOT EXISTS users (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        username        TEXT    NOT NULL UNIQUE,
        display_name    TEXT    NOT NULL DEFAULT '',
        webauthn_handle BLOB    NOT NULL,
        created_at      TEXT    NOT NULL
    )"""

_DDL_CREDENTIALS = """
    CREATE TABLE IF NOT EXISTS auth_credentials (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        credential_id BLOB    NOT NULL UNIQUE,
        public_key    BLOB    NOT NULL,
        sign_count    INTEGER NOT NULL DEFAULT 0,
        label         TEXT    NOT NULL DEFAULT '',
        backed_up     INTEGER NOT NULL DEFAULT 0,
        created_at    TEXT    NOT NULL,
        last_used_at  TEXT    NOT NULL DEFAULT ''
    )"""

_DDL_SESSIONS = """
    CREATE TABLE IF NOT EXISTS auth_sessions (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        session_hash TEXT    NOT NULL UNIQUE,
        created_at   TEXT    NOT NULL,
        expires_at   TEXT    NOT NULL
    )"""


def _ensure_tables() -> None:
    from astrapi_core.system.db import _conn

    con = _conn()
    con.execute(_DDL_USERS)
    con.execute(_DDL_CREDENTIALS)
    con.execute(_DDL_SESSIONS)
    con.commit()
    _migrate_user_id_columns(con)
    _migrate_user_columns(con)


def _migrate_user_id_columns(con) -> None:
    """auth_credentials/auth_sessions kannten urspruenglich kein user_id --
    register_table()'s CREATE TABLE IF NOT EXISTS zieht bei Bestandstabellen
    keine neue Spalte nach, deshalb hier per ALTER TABLE (gleiches Muster wie
    astrapi_sync/_app.py::_migrate_folders_storage_location()). 0 = Sentinel
    "noch nicht migriert" -- users-IDs starten bei 1 (AUTOINCREMENT),
    kollisionsfrei. Laeuft bei JEDEM _ensure_tables()-Aufruf, idempotent."""
    for table in ("auth_credentials", "auth_sessions"):
        cols = [r[1] for r in con.execute(f"PRAGMA table_info({table})").fetchall()]
        if "user_id" not in cols:
            con.execute(f"ALTER TABLE {table} ADD COLUMN user_id INTEGER NOT NULL DEFAULT 0")
            con.commit()

    pending = con.execute(
        "SELECT (SELECT COUNT(*) FROM auth_credentials WHERE user_id=0) "
        "+ (SELECT COUNT(*) FROM auth_sessions WHERE user_id=0) AS n"
    ).fetchone()["n"]
    if not pending:
        return
    default_id = _get_or_create_default_user(con)
    con.execute("UPDATE auth_credentials SET user_id=? WHERE user_id=0", (default_id,))
    con.execute("UPDATE auth_sessions SET user_id=? WHERE user_id=0", (default_id,))
    con.commit()


def _migrate_user_columns(con) -> None:
    """users kannte urspruenglich weder is_admin noch password_hash --
    gleiches ALTER-TABLE-Muster wie _migrate_user_id_columns() oben.

    Genau EIN Admin: ist noch keiner gesetzt, wird der Bootstrap-/
    Default-User (_default_user_id()) dazu -- der Account, der die App
    urspruenglich eingerichtet hat. Idempotent, laeuft bei jedem
    _ensure_tables()-Aufruf.

    Bestehendes GLOBALES Passwort (kv "_auth"/"password_hash", einziger
    Passwort-Weg vor dieser Erweiterung) wird unveraendert als String in
    die password_hash-Spalte des neuen Admin-Nutzers uebernommen, falls
    dort noch leer -- das Hash-Format (_hash_password()) ist
    selbstbeschreibend (Algorithmus+Iterationen+Salt eingebettet), kein
    Rehashing noetig, ein bestehendes Passwort bleibt gueltig."""
    cols = [r[1] for r in con.execute("PRAGMA table_info(users)").fetchall()]
    if "is_admin" not in cols:
        con.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")
        con.commit()
    if "password_hash" not in cols:
        con.execute("ALTER TABLE users ADD COLUMN password_hash TEXT NOT NULL DEFAULT ''")
        con.commit()
    if "enabled" not in cols:
        con.execute("ALTER TABLE users ADD COLUMN enabled INTEGER NOT NULL DEFAULT 1")
        con.commit()

    has_admin = con.execute("SELECT 1 FROM users WHERE is_admin=1 LIMIT 1").fetchone()
    if not has_admin:
        admin_id = _get_or_create_default_user(con)
        con.execute("UPDATE users SET is_admin=1 WHERE id=?", (admin_id,))

        from astrapi_core.system.db import kv_get

        global_hash = kv_get("_auth", "password_hash")
        if global_hash:
            row = con.execute("SELECT password_hash FROM users WHERE id=?", (admin_id,)).fetchone()
            if row and not row["password_hash"]:
                con.execute(
                    "UPDATE users SET password_hash=? WHERE id=?", (global_hash, admin_id)
                )
        con.commit()

    # Frueher: automatische, einmalige Umbenennung des Bootstrap-Nutzers
    # von "_default" zu "_admin" sobald auth.multi_user: true war. Auf
    # Nutzerwunsch (2026-09-13) entfernt -- "_default" bleibt ueberall
    # einheitlich, unabhaengig von Single-Owner/Multi-User. Der Nutzername
    # laesst sich bei Bedarf jetzt ohnehin ueber die Nutzer-Eigenschaften
    # im modules/users-Modul manuell aendern (set_username()).


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


# ── Nutzerkonten ─────────────────────────────────────────────────────────


def _get_or_create_default_user(con) -> int:
    """Kernlogik ohne _ensure_tables()-Aufruf -- wird sowohl aus der
    Migration (Tabellen existieren dort schon per Definition) als auch aus
    der oeffentlichen _default_user_id() (siehe unten) genutzt, ohne dass
    beide sich gegenseitig in eine Rekursion mit _ensure_tables() treiben.

    Sucht sowohl "_default" als auch "_admin" -- Multi-User-Apps benennen
    den Bootstrap-/Default-User bei der Admin-Migration einmalig auf
    "_admin" um (siehe _migrate_user_columns()). Ohne diesen zweiten
    Namen wuerde ein Aufruf NACH der Umbenennung die Zeile nicht mehr
    finden und faelschlich eine zweite "_default"-Zeile anlegen. Bewusst
    kein is_admin=1-Check hier: diese Funktion laeuft in _ensure_tables()
    VOR der is_admin-Spaltenmigration (aus _migrate_user_id_columns()
    heraus), die Spalte existiert an dieser Stelle teils noch nicht."""
    row = con.execute(
        "SELECT id FROM users WHERE username IN ('_default', '_admin')"
    ).fetchone()
    if row:
        return row["id"]

    from astrapi_core.system.db import kv_get

    legacy_handle_b64 = kv_get("_auth", "user_handle")
    handle = base64url_to_bytes(legacy_handle_b64) if legacy_handle_b64 else secrets.token_bytes(32)
    cur = con.execute(
        "INSERT INTO users (username, display_name, webauthn_handle, created_at) VALUES (?,?,?,?)",
        ("_default", "", handle, _now_iso()),
    )
    con.commit()
    return cur.lastrowid


def _default_user_id() -> int:
    """Get-or-create der impliziten "Default-User"-Zeile (username="_default")
    -- Rückwärtskompatibilitäts-Anker für alle Aufrufer, die nie ein eigenes
    user_id angeben (astrapi-admin, Single-Owner-Fall, siehe Modul-Docstring).
    Übernimmt beim allerersten Anlegen den ALTEN globalen WebAuthn-Handle aus
    dem KV-Store (falls vorhanden), damit bereits registrierte Passkeys nach
    der Migration exakt denselben Account-Bezug behalten. Ruft selbst
    _ensure_tables() auf, damit externe Aufrufer (z.B. astrapi-sync-
    Migrationen) unabhängig von der Aufrufreihenfolge sind."""
    _ensure_tables()
    from astrapi_core.system.db import _conn

    return _get_or_create_default_user(_conn())


def _user_handle(user_id: int) -> bytes:
    from astrapi_core.system.db import _conn

    row = _conn().execute("SELECT webauthn_handle FROM users WHERE id=?", (user_id,)).fetchone()
    if row is None:
        raise ValueError(f"Unbekannter user_id: {user_id}")
    return row["webauthn_handle"]


def create_user(username: str, display_name: str = "") -> int:
    """Legt eine neue, eigenständige Nutzerzeile mit eigenem WebAuthn-Handle
    an -- genutzt vom Einladungs-Flow (ui/multi_user_routes.py)."""
    _ensure_tables()
    from astrapi_core.system.db import _conn

    con = _conn()
    cur = con.execute(
        "INSERT INTO users (username, display_name, webauthn_handle, created_at) VALUES (?,?,?,?)",
        (username, display_name, secrets.token_bytes(32), _now_iso()),
    )
    con.commit()
    return cur.lastrowid


def get_user(user_id: int) -> dict | None:
    _ensure_tables()
    from astrapi_core.system.db import _conn

    row = _conn().execute(
        "SELECT id, username, display_name, created_at, is_admin, enabled FROM users WHERE id=?",
        (user_id,),
    ).fetchone()
    return dict(row) if row else None


def list_users() -> list[dict]:
    _ensure_tables()
    from astrapi_core.system.db import _conn

    rows = _conn().execute(
        "SELECT id, username, display_name, created_at, is_admin, enabled FROM users ORDER BY id"
    ).fetchall()
    return [dict(r) for r in rows]


def is_admin(user_id: int) -> bool:
    _ensure_tables()
    from astrapi_core.system.db import _conn

    row = _conn().execute("SELECT is_admin FROM users WHERE id=?", (user_id,)).fetchone()
    return bool(row and row["is_admin"])


def set_username(user_id: int, username: str) -> None:
    """Eindeutigkeit ist Aufgabe der aufrufenden UI (wie schon bei
    create_user()) -- diese Funktion prueft sie nicht selbst."""
    _ensure_tables()
    from astrapi_core.system.db import _conn

    con = _conn()
    con.execute("UPDATE users SET username=? WHERE id=?", (username, user_id))
    con.commit()


def set_display_name(user_id: int, display_name: str) -> None:
    _ensure_tables()
    from astrapi_core.system.db import _conn

    con = _conn()
    con.execute("UPDATE users SET display_name=? WHERE id=?", (display_name, user_id))
    con.commit()


def set_admin(user_id: int, value: bool = True) -> None:
    """Markiert/entfernt einen Nutzer als Admin -- z.B. für einen bewussten
    Rollenwechsel durch den bisherigen Admin. Erzwingt NICHT, dass mindestens
    einer übrig bleibt (anders als delete_user() beim letzten Nutzer) --
    das wäre eine Server-seitige Entscheidung, die die UI treffen sollte,
    bevor sie hier aufruft."""
    _ensure_tables()
    from astrapi_core.system.db import _conn

    con = _conn()
    con.execute("UPDATE users SET is_admin=? WHERE id=?", (1 if value else 0, user_id))
    con.commit()


def set_enabled(user_id: int, value: bool = True) -> None:
    """Deaktiviert/aktiviert einen Nutzer, ohne ihn zu löschen -- Passkeys/
    Passwort bleiben erhalten, greifen aber nicht mehr (siehe
    get_current_user()/verify_user_password()/verify_authentication_full(),
    die alle einen deaktivierten Nutzer wie 'nicht angemeldet' behandeln).
    Erzwingt wie set_admin() NICHT, dass mindestens ein aktiver Admin übrig
    bleibt -- das ist Aufgabe der aufrufenden UI."""
    _ensure_tables()
    from astrapi_core.system.db import _conn

    con = _conn()
    con.execute("UPDATE users SET enabled=? WHERE id=?", (1 if value else 0, user_id))
    con.commit()


def delete_user(user_id: int) -> None:
    """Löscht einen Nutzer inkl. all seiner Passkeys/Sessions (kein FK in
    SQLite hier, daher manuelles Cascade). Blockiert das Löschen des
    letzten verbleibenden Nutzers -- sonst kann sich niemand mehr
    einloggen und die App ist für immer ausgesperrt (is_configured()
    bliebe False, aber /auth/register bootstrapt nur, solange wirklich
    NIEMAND existiert -- ein verwaister Zustand ohne jeden Nutzer ist
    hier nicht vorgesehen)."""
    _ensure_tables()
    from astrapi_core.system.db import _conn

    con = _conn()
    n = con.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
    if n <= 1:
        raise ValueError("Der letzte verbleibende Nutzer kann nicht gelöscht werden.")
    con.execute("DELETE FROM auth_credentials WHERE user_id=?", (user_id,))
    con.execute("DELETE FROM auth_sessions WHERE user_id=?", (user_id,))
    con.execute("DELETE FROM users WHERE id=?", (user_id,))
    con.commit()


def reset_credentials(user_id: int) -> None:
    """Entfernt alle Passkeys eines Nutzers -- z.B. verlorenes Gerät, oder
    eine abgebrochene Erst-Registrierung (Einladungs-Flow), die eine
    credential-lose, unbenutzbare User-Zeile hinterlassen hat (siehe
    modules/users). Macht den Nutzer wieder registrierbar über einen
    frischen Einladungslink, der direkt an diese user_id gebunden ist
    (auth_invites.create_invite_token(..., existing_user_id=user_id))."""
    _ensure_tables()
    from astrapi_core.system.db import _conn

    _conn().execute("DELETE FROM auth_credentials WHERE user_id=?", (user_id,))
    _conn().commit()


# ── Bootstrap-Zustand ────────────────────────────────────────────────────


def has_credentials() -> bool:
    _ensure_tables()
    from astrapi_core.system.db import _conn

    row = _conn().execute("SELECT COUNT(*) AS n FROM auth_credentials").fetchone()
    return bool(row["n"])


def list_credentials(user_id: int | None = None) -> list[dict]:
    """user_id=None: alle Passkeys, unabhängig vom Besitzer (bisheriges
    Verhalten -- kein bestehender Aufrufer nutzte das je pro Nutzer)."""
    _ensure_tables()
    from astrapi_core.system.db import _conn

    if user_id is None:
        rows = _conn().execute(
            "SELECT id, user_id, label, created_at, last_used_at FROM auth_credentials ORDER BY id"
        ).fetchall()
    else:
        rows = _conn().execute(
            "SELECT id, user_id, label, created_at, last_used_at FROM auth_credentials "
            "WHERE user_id=? ORDER BY id",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


# ── Challenge-Cookie ─────────────────────────────────────────────────────
# Der Server muss zwischen "Optionen erzeugen" und "Antwort prüfen" denselben
# Challenge-Wert vorhalten. Statt einer eigenen DB-Tabelle mit Aufräumlauf:
# Fernet-verschlüsselt (astrapi_core.system.secrets, gleiches Muster wie
# secret_fields in db.py) in einem kurzlebigen Cookie zwischengespeichert --
# serverlos, fälschungssicher, läuft von selbst ab.


def _pack_challenge(challenge: bytes, kind: str) -> str:
    from astrapi_core.system.secrets import encrypt

    payload = json.dumps(
        {"c": bytes_to_base64url(challenge), "k": kind, "exp": time.time() + _CHALLENGE_TTL_SECONDS}
    )
    return encrypt(payload)


def _unpack_challenge(cookie_value: str | None, expected_kind: str) -> bytes | None:
    if not cookie_value:
        return None
    from astrapi_core.system.secrets import decrypt

    raw = decrypt(cookie_value, default="")
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    if data.get("k") != expected_kind or data.get("exp", 0) < time.time():
        return None
    try:
        return base64url_to_bytes(data["c"])
    except Exception:
        return None


# ── Registrierung (Passkey anlegen) ─────────────────────────────────────


def build_registration_options(
    rp_id: str,
    rp_name: str,
    user_id: int | None = None,
    username: str | None = None,
    display_name: str | None = None,
) -> tuple[str, str]:
    """Gibt (options_json, challenge_cookie_value) zurück.

    user_id=None: exakt das bisherige Verhalten (impliziter Default-User,
    user_name="admin") -- Rückwärtskompatibilität für astrapi-admin & Co.
    user_id gesetzt (Einladungs-Flow, siehe ui/multi_user_routes.py):
    echter Nutzername/Anzeigename dieser Person."""
    _ensure_tables()
    from astrapi_core.system.db import _conn

    resolved_user_id = user_id if user_id is not None else _default_user_id()

    existing = _conn().execute(
        "SELECT credential_id FROM auth_credentials WHERE user_id=?", (resolved_user_id,)
    ).fetchall()
    exclude = [PublicKeyCredentialDescriptor(id=row["credential_id"]) for row in existing]

    options = webauthn.generate_registration_options(
        rp_id=rp_id,
        rp_name=rp_name,
        user_id=_user_handle(resolved_user_id),
        user_name=username or "admin",
        user_display_name=display_name or username or rp_name,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        exclude_credentials=exclude or None,
    )
    return webauthn.options_to_json(options), _pack_challenge(options.challenge, "registration")


def verify_registration(
    credential: dict,
    challenge_cookie: str | None,
    rp_id: str,
    origin: "str | list[str]",
    label: str,
    user_id: int | None = None,
) -> bool:
    _ensure_tables()
    challenge = _unpack_challenge(challenge_cookie, "registration")
    if challenge is None:
        return False
    try:
        verified = webauthn.verify_registration_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=rp_id,
            expected_origin=origin,
            require_user_verification=True,
        )
    except Exception:
        return False

    from astrapi_core.system.db import _conn

    resolved_user_id = user_id if user_id is not None else _default_user_id()

    _conn().execute(
        "INSERT INTO auth_credentials "
        "(credential_id, public_key, sign_count, label, backed_up, created_at, user_id) VALUES (?,?,?,?,?,?,?)",
        (
            verified.credential_id,
            verified.credential_public_key,
            verified.sign_count,
            label or "Passkey",
            1 if verified.credential_backed_up else 0,
            _now_iso(),
            resolved_user_id,
        ),
    )
    _conn().commit()
    return True


# ── Login (Passkey prüfen, usernameless) ─────────────────────────────────


def build_authentication_options(rp_id: str) -> tuple[str, str]:
    options = webauthn.generate_authentication_options(
        rp_id=rp_id, user_verification=UserVerificationRequirement.REQUIRED
    )
    return webauthn.options_to_json(options), _pack_challenge(options.challenge, "authentication")


def verify_authentication_full(
    credential: dict, challenge_cookie: str | None, rp_id: str, origin: "str | list[str]"
) -> dict | None:
    """Volle Verifikationslogik, liefert bei Erfolg das Nutzerobjekt
    ({"id", "username", "display_name"}) statt nur bool -- das Login ist
    weiterhin "usernameless" (der Browser-Passkey-Picker identifiziert die
    Person implizit über die gewählte Passkey), aber der Server erfährt
    darüber jetzt WELCHER Nutzer sich einloggt (für create_session())."""
    _ensure_tables()
    challenge = _unpack_challenge(challenge_cookie, "authentication")
    if challenge is None:
        return None

    raw_id = credential.get("rawId") or credential.get("id") if isinstance(credential, dict) else None
    if not raw_id:
        return None
    try:
        credential_id = base64url_to_bytes(raw_id)
    except Exception:
        return None

    from astrapi_core.system.db import _conn

    row = _conn().execute(
        "SELECT id, public_key, sign_count, user_id FROM auth_credentials WHERE credential_id=?",
        (credential_id,),
    ).fetchone()
    if row is None:
        return None

    try:
        verified = webauthn.verify_authentication_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=rp_id,
            expected_origin=origin,
            credential_public_key=row["public_key"],
            credential_current_sign_count=row["sign_count"],
            require_user_verification=True,
        )
    except Exception:
        return None

    # Klon-Erkennung nur bei nicht synchronisierten Passkeys sinnvoll --
    # geräteübergreifend synchronisierte Passkeys (iCloud-Schlüsselbund,
    # Google-Passwortmanager) melden laut Spezifikation dauerhaft
    # sign_count=0, das ist dort kein Warnsignal.
    if (
        not verified.credential_backed_up
        and verified.new_sign_count != 0
        and verified.new_sign_count <= row["sign_count"]
    ):
        return None

    _conn().execute(
        "UPDATE auth_credentials SET sign_count=?, backed_up=?, last_used_at=? WHERE id=?",
        (verified.new_sign_count, 1 if verified.credential_backed_up else 0, _now_iso(), row["id"]),
    )
    _conn().commit()
    user = get_user(row["user_id"])
    if user is None or not user.get("enabled", True):
        return None
    return user


def verify_authentication(
    credential: dict, challenge_cookie: str | None, rp_id: str, origin: "str | list[str]"
) -> bool:
    """Dünner Bool-Wrapper um verify_authentication_full() -- bestehende
    Aufrufer, die nur wissen müssen OB der Login gültig war, bleiben
    unverändert."""
    return verify_authentication_full(credential, challenge_cookie, rp_id, origin) is not None


# ── Passwort (Fallback-Login, siehe Modul-Docstring) ─────────────────────

_PBKDF2_ITERATIONS = 600_000
_PASSWORD_LOCKOUT_THRESHOLD = 5
_PASSWORD_LOCKOUT_SECONDS = 30


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${bytes_to_base64url(salt)}${bytes_to_base64url(dk)}"


def _verify_password_hash(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt_b64, hash_b64 = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        salt = base64url_to_bytes(salt_b64)
        expected = base64url_to_bytes(hash_b64)
    except (ValueError, Exception):
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(iterations))
    return hmac.compare_digest(dk, expected)


def has_password() -> bool:
    from astrapi_core.system.db import kv_get

    return bool(kv_get("_auth", "password_hash"))


def is_configured() -> bool:
    """True sobald IRGENDeine Anmeldemethode eingerichtet ist (Passkey
    oder Passwort) -- steuert, ob die Bootstrap-Registrierung noch offen
    ist (siehe ui/auth_routes.py::_may_register(), ui/auth_middleware.py)."""
    return has_credentials() or has_password()


def set_password(password: str) -> None:
    from astrapi_core.system.db import kv_set

    kv_set("_auth", "password_hash", _hash_password(password))


def _failed_attempts() -> tuple[int, float]:
    from astrapi_core.system.db import kv_get

    raw = kv_get("_auth", "password_fail")
    if not raw:
        return 0, 0.0
    try:
        data = json.loads(raw)
        return int(data.get("n", 0)), float(data.get("at", 0))
    except (ValueError, TypeError):
        return 0, 0.0


def _record_failed_attempt(n: int) -> None:
    from astrapi_core.system.db import kv_set

    kv_set("_auth", "password_fail", json.dumps({"n": n + 1, "at": time.time()}))


def _clear_failed_attempts() -> None:
    from astrapi_core.system.db import kv_delete

    kv_delete("_auth", "password_fail")


def verify_password(password: str) -> bool:
    """Einfache, global (kein Multi-User-Fall) geführte Brute-Force-Bremse:
    nach 5 Fehlversuchen 30s Sperre -- kein volles Lockout-System mit
    Admin-Reset, angemessen für ein Single-Owner-Tool."""
    from astrapi_core.system.db import kv_get

    n, at = _failed_attempts()
    if n >= _PASSWORD_LOCKOUT_THRESHOLD and (time.time() - at) < _PASSWORD_LOCKOUT_SECONDS:
        return False

    stored = kv_get("_auth", "password_hash")
    if not stored or not _verify_password_hash(password, stored):
        _record_failed_attempt(n)
        return False

    _clear_failed_attempts()
    return True


# ── Passwort pro Nutzer (Multi-User) ────────────────────────────────────────
# Getrennt von set_password()/verify_password()/has_password() oben, die
# GLOBAL bleiben (ein Passwort, kein user_id-Bezug) -- weiterhin die
# Grundlage fuer Single-Owner-Apps (astrapi-backup/-mirror/-packages/
# -admin). Hier: ein eigenes Passwort je users-Zeile, fuer Apps mit
# auth.multi_user: true (aktuell nur astrapi-sync), siehe
# ui/auth_routes.py::login_password().


def has_user_password(user_id: int) -> bool:
    _ensure_tables()
    from astrapi_core.system.db import _conn

    row = _conn().execute("SELECT password_hash FROM users WHERE id=?", (user_id,)).fetchone()
    return bool(row and row["password_hash"])


def set_user_password(user_id: int, password: str) -> None:
    _ensure_tables()
    from astrapi_core.system.db import _conn

    con = _conn()
    con.execute(
        "UPDATE users SET password_hash=? WHERE id=?", (_hash_password(password), user_id)
    )
    con.commit()


def _user_failed_attempts(username: str) -> tuple[int, float]:
    from astrapi_core.system.db import kv_get

    raw = kv_get("_auth", f"password_fail:{username}")
    if not raw:
        return 0, 0.0
    try:
        data = json.loads(raw)
        return int(data.get("n", 0)), float(data.get("at", 0))
    except (ValueError, TypeError):
        return 0, 0.0


def _record_user_failed_attempt(username: str, n: int) -> None:
    from astrapi_core.system.db import kv_set

    kv_set("_auth", f"password_fail:{username}", json.dumps({"n": n + 1, "at": time.time()}))


def _clear_user_failed_attempts(username: str) -> None:
    from astrapi_core.system.db import kv_delete

    kv_delete("_auth", f"password_fail:{username}")


def verify_user_password(username: str, password: str) -> dict | None:
    """Wie verify_password(), aber pro Nutzername -- eigene Brute-Force-
    Bremse PRO Nutzername (nicht global), sonst koennte ein Nutzer mit
    Tippfehlern versehentlich alle anderen Nutzer mit aussperren. Gibt
    bei Erfolg das Nutzerdict zurueck (fuer create_session(user_id))."""
    _ensure_tables()
    from astrapi_core.system.db import _conn

    n, at = _user_failed_attempts(username)
    if n >= _PASSWORD_LOCKOUT_THRESHOLD and (time.time() - at) < _PASSWORD_LOCKOUT_SECONDS:
        return None

    row = _conn().execute(
        "SELECT id, username, display_name, created_at, is_admin, enabled, password_hash "
        "FROM users WHERE username=?",
        (username,),
    ).fetchone()
    if (
        row is None
        or not row["enabled"]
        or not row["password_hash"]
        or not _verify_password_hash(password, row["password_hash"])
    ):
        _record_user_failed_attempt(username, n)
        return None

    _clear_user_failed_attempts(username)
    user = dict(row)
    del user["password_hash"]
    return user


# ── Sessions ──────────────────────────────────────────────────────────────


def create_session(user_id: int | None = None) -> str:
    """Legt eine neue Session an, gibt das Klartext-Token zurück -- das sieht
    nur hier der Client (landet als Cookie), in der DB nur dessen Hash.
    user_id=None: impliziter Default-User (Rückwärtskompatibilität)."""
    _ensure_tables()
    token = secrets.token_urlsafe(32)
    expires_iso = (datetime.now(timezone.utc) + timedelta(days=SESSION_TTL_DAYS)).isoformat()
    from astrapi_core.system.db import _conn

    resolved_user_id = user_id if user_id is not None else _default_user_id()

    _conn().execute(
        "INSERT INTO auth_sessions (session_hash, created_at, expires_at, user_id) VALUES (?,?,?,?)",
        (_hash(token), _now_iso(), expires_iso, resolved_user_id),
    )
    _conn().commit()
    return token


def is_logged_in(session_token: str | None) -> bool:
    if not session_token:
        return False
    _ensure_tables()
    from astrapi_core.system.db import _conn

    row = _conn().execute(
        "SELECT expires_at FROM auth_sessions WHERE session_hash=?", (_hash(session_token),)
    ).fetchone()
    if row is None:
        return False
    return row["expires_at"] > _now_iso()


def get_current_user(session_token: str | None) -> dict | None:
    """Wie is_logged_in(), liefert aber das Nutzerobjekt statt nur bool --
    für Code, der die Identität braucht (z.B. astrapi-sync's Owner-Scoping).
    None sowohl bei fehlender/abgelaufener Session als auch bei fehlendem
    Token -- ebenso, wenn der Nutzer inzwischen deaktiviert wurde (set_enabled()):
    eine bestehende Session bleibt in der DB gueltig, zaehlt hier aber wie
    "nicht angemeldet", einziger zentrale Durchsetzungspunkt fuer alle
    bereits eingeloggten Zugriffe."""
    if not session_token:
        return None
    _ensure_tables()
    from astrapi_core.system.db import _conn

    row = _conn().execute(
        "SELECT expires_at, user_id FROM auth_sessions WHERE session_hash=?",
        (_hash(session_token),),
    ).fetchone()
    if row is None or row["expires_at"] <= _now_iso():
        return None
    user = get_user(row["user_id"])
    if user is None or not user.get("enabled", True):
        return None
    return user


def destroy_session(session_token: str | None) -> None:
    if not session_token:
        return
    _ensure_tables()
    from astrapi_core.system.db import _conn

    _conn().execute("DELETE FROM auth_sessions WHERE session_hash=?", (_hash(session_token),))
    _conn().commit()
