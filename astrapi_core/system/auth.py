"""core/system/auth.py – WebAuthn/Passkey-Login für die UI.

Opt-in pro App (`app.yaml: auth.enabled`, siehe ui/app.py::create() und
ui/auth_middleware.py) -- ohne diesen Schalter bleibt eine App wie bisher
offen im LAN. Hintergrund/Entscheidung: [[E-003]] in entscheidungen.md.

Bewusst **Passkeys statt Passwort oder beliebigem WebAuthn**: Discoverable
Credentials (`resident_key=required`) + `user_verification=required` --
echte, phishing-resistente Passkeys mit Konten-Picker statt Login-Formular,
kein Passwort-Hash/-Reset-Flow.

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
