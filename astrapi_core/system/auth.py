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

Single-Owner-Modell wie der Rest der astrapi-Familie: keine "users"-Tabelle
mit Rollen. Jeder registrierte Passkey ist gleichwertig für denselben
Betreiber (mehrere Geräte möglich) -- ein fester, einmalig erzeugter
WebAuthn-"User-Handle" statt echter Benutzerkonten.

Zwei eigenständig verwaltete Tabellen (nicht Teil des generischen
Modul-CRUD-Systems, siehe system/db.py::register_table() -- Sessions/
Credentials sind keine UI-verwalteten Listen):

- auth_credentials -- registrierte Passkeys
- auth_sessions    -- angemeldete Browser-Sessions, serverseitig per
  SHA-256-Hash abgleichbar (gleiches Muster wie Host-/Geräte-Token bei
  astrapi-sync/astrapi-admin: das Klartext-Token sieht nur der Client,
  in der DB steht nur der Hash)
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
    con.execute(_DDL_CREDENTIALS)
    con.execute(_DDL_SESSIONS)
    con.commit()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


# ── User-Handle (ein fester "Betreiber", kein Multi-User) ──────────────────


def _user_handle() -> bytes:
    from astrapi_core.system.db import kv_get, kv_set

    raw = kv_get("_auth", "user_handle")
    if raw:
        return base64url_to_bytes(raw)
    handle = secrets.token_bytes(32)
    kv_set("_auth", "user_handle", bytes_to_base64url(handle))
    return handle


# ── Bootstrap-Zustand ────────────────────────────────────────────────────


def has_credentials() -> bool:
    _ensure_tables()
    from astrapi_core.system.db import _conn

    row = _conn().execute("SELECT COUNT(*) AS n FROM auth_credentials").fetchone()
    return bool(row["n"])


def list_credentials() -> list[dict]:
    _ensure_tables()
    from astrapi_core.system.db import _conn

    rows = _conn().execute(
        "SELECT id, label, created_at, last_used_at FROM auth_credentials ORDER BY id"
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


def build_registration_options(rp_id: str, rp_name: str) -> tuple[str, str]:
    """Gibt (options_json, challenge_cookie_value) zurück."""
    _ensure_tables()
    from astrapi_core.system.db import _conn

    existing = _conn().execute("SELECT credential_id FROM auth_credentials").fetchall()
    exclude = [PublicKeyCredentialDescriptor(id=row["credential_id"]) for row in existing]

    options = webauthn.generate_registration_options(
        rp_id=rp_id,
        rp_name=rp_name,
        user_id=_user_handle(),
        user_name="admin",
        user_display_name=rp_name,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        exclude_credentials=exclude or None,
    )
    return webauthn.options_to_json(options), _pack_challenge(options.challenge, "registration")


def verify_registration(
    credential: dict, challenge_cookie: str | None, rp_id: str, origin: "str | list[str]", label: str
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

    _conn().execute(
        "INSERT INTO auth_credentials "
        "(credential_id, public_key, sign_count, label, backed_up, created_at) VALUES (?,?,?,?,?,?)",
        (
            verified.credential_id,
            verified.credential_public_key,
            verified.sign_count,
            label or "Passkey",
            1 if verified.credential_backed_up else 0,
            _now_iso(),
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


def verify_authentication(
    credential: dict, challenge_cookie: str | None, rp_id: str, origin: "str | list[str]"
) -> bool:
    _ensure_tables()
    challenge = _unpack_challenge(challenge_cookie, "authentication")
    if challenge is None:
        return False

    raw_id = credential.get("rawId") or credential.get("id") if isinstance(credential, dict) else None
    if not raw_id:
        return False
    try:
        credential_id = base64url_to_bytes(raw_id)
    except Exception:
        return False

    from astrapi_core.system.db import _conn

    row = _conn().execute(
        "SELECT id, public_key, sign_count FROM auth_credentials WHERE credential_id=?",
        (credential_id,),
    ).fetchone()
    if row is None:
        return False

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
        return False

    # Klon-Erkennung nur bei nicht synchronisierten Passkeys sinnvoll --
    # geräteübergreifend synchronisierte Passkeys (iCloud-Schlüsselbund,
    # Google-Passwortmanager) melden laut Spezifikation dauerhaft
    # sign_count=0, das ist dort kein Warnsignal.
    if (
        not verified.credential_backed_up
        and verified.new_sign_count != 0
        and verified.new_sign_count <= row["sign_count"]
    ):
        return False

    _conn().execute(
        "UPDATE auth_credentials SET sign_count=?, backed_up=?, last_used_at=? WHERE id=?",
        (verified.new_sign_count, 1 if verified.credential_backed_up else 0, _now_iso(), row["id"]),
    )
    _conn().commit()
    return True


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


# ── Sessions ──────────────────────────────────────────────────────────────


def create_session() -> str:
    """Legt eine neue Session an, gibt das Klartext-Token zurück -- das sieht
    nur hier der Client (landet als Cookie), in der DB nur dessen Hash."""
    _ensure_tables()
    token = secrets.token_urlsafe(32)
    expires_iso = (datetime.now(timezone.utc) + timedelta(days=SESSION_TTL_DAYS)).isoformat()
    from astrapi_core.system.db import _conn

    _conn().execute(
        "INSERT INTO auth_sessions (session_hash, created_at, expires_at) VALUES (?,?,?)",
        (_hash(token), _now_iso(), expires_iso),
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


def destroy_session(session_token: str | None) -> None:
    if not session_token:
        return
    _ensure_tables()
    from astrapi_core.system.db import _conn

    _conn().execute("DELETE FROM auth_sessions WHERE session_hash=?", (_hash(session_token),))
    _conn().commit()
