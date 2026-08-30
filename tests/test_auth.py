"""system/auth.py: Passkey-Registrierung/-Login (WebAuthn-Verifikation
gemockt -- kein echter Authenticator in Tests verfügbar) + Sessions.
Fokus auf die sicherheitsrelevante Logik: Challenge-Cookie-Bindung (kein
Ceremony-Confusion zwischen registration/authentication), unbekannte
Credential-IDs, Klon-Erkennung über sign_count."""
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from astrapi_core.system import auth as authmod
from astrapi_core.system import db, secrets


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path):
    db._db_path = tmp_path / "test.db"
    db._local.conn = None
    secrets._key_path_prod = None
    secrets._key_path_dev = None
    secrets.configure(key_path=tmp_path / ".secret.key")
    yield


def _fake_verified_registration(**overrides):
    base = dict(
        credential_id=b"cred-1",
        credential_public_key=b"pubkey-1",
        sign_count=0,
        credential_backed_up=False,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _fake_verified_authentication(**overrides):
    base = dict(new_sign_count=1, credential_backed_up=False)
    base.update(overrides)
    return SimpleNamespace(**base)


# ── Bootstrap-Zustand ────────────────────────────────────────────────────


def test_has_credentials_ist_am_anfang_leer():
    assert authmod.has_credentials() is False


# ── Challenge-Cookie ─────────────────────────────────────────────────────


def test_challenge_cookie_roundtrip():
    cookie = authmod._pack_challenge(b"abc123", "registration")
    assert authmod._unpack_challenge(cookie, "registration") == b"abc123"


def test_challenge_cookie_falscher_ceremony_typ_wird_abgelehnt():
    """Verhindert, dass ein fuer 'registration' ausgestellter Challenge-Cookie
    fuer eine 'authentication'-Verifikation wiederverwendet wird."""
    cookie = authmod._pack_challenge(b"abc123", "registration")
    assert authmod._unpack_challenge(cookie, "authentication") is None


def test_challenge_cookie_abgelaufen_wird_abgelehnt():
    with patch("astrapi_core.system.auth.time.time", return_value=1_000_000_000):
        cookie = authmod._pack_challenge(b"abc", "registration")
    with patch("astrapi_core.system.auth.time.time", return_value=1_000_000_000 + 3600):
        assert authmod._unpack_challenge(cookie, "registration") is None


def test_challenge_cookie_kaputter_wert_wird_abgelehnt():
    assert authmod._unpack_challenge("kein-gueltiges-fernet-token", "registration") is None
    assert authmod._unpack_challenge(None, "registration") is None


# ── Registrierungs-Optionen ──────────────────────────────────────────────


def test_registration_options_fordern_echten_passkey():
    options_json, _ = authmod.build_registration_options("example.org", "Test")
    data = json.loads(options_json)
    sel = data["authenticatorSelection"]
    assert sel["residentKey"] == "required"
    assert sel["userVerification"] == "required"


# ── Registrierung verifizieren ───────────────────────────────────────────


def test_verify_registration_ohne_challenge_cookie_schlaegt_fehl_ohne_webauthn_aufruf():
    with patch("astrapi_core.system.auth.webauthn.verify_registration_response") as mock_verify:
        ok = authmod.verify_registration({}, None, "example.org", "https://example.org", "Laptop")
    assert ok is False
    mock_verify.assert_not_called()
    assert authmod.has_credentials() is False


def test_verify_registration_erfolg_speichert_credential():
    _, cookie = authmod.build_registration_options("example.org", "Test")
    with patch(
        "astrapi_core.system.auth.webauthn.verify_registration_response",
        return_value=_fake_verified_registration(),
    ):
        ok = authmod.verify_registration({"id": "x"}, cookie, "example.org", "https://example.org", "Laptop")
    assert ok is True
    assert authmod.has_credentials() is True
    assert authmod.list_credentials()[0]["label"] == "Laptop"


def test_verify_registration_webauthn_fehler_speichert_nichts():
    _, cookie = authmod.build_registration_options("example.org", "Test")
    with patch(
        "astrapi_core.system.auth.webauthn.verify_registration_response",
        side_effect=Exception("ungueltige Signatur"),
    ):
        ok = authmod.verify_registration({"id": "x"}, cookie, "example.org", "https://example.org", "Laptop")
    assert ok is False
    assert authmod.has_credentials() is False


# ── Login verifizieren ───────────────────────────────────────────────────


def _register_one_credential(credential_id=b"cred-1", sign_count=0, backed_up=False):
    _, cookie = authmod.build_registration_options("example.org", "Test")
    with patch(
        "astrapi_core.system.auth.webauthn.verify_registration_response",
        return_value=_fake_verified_registration(
            credential_id=credential_id, sign_count=sign_count, credential_backed_up=backed_up
        ),
    ):
        assert authmod.verify_registration({"id": "x"}, cookie, "example.org", "https://example.org", "L")


def test_verify_authentication_unbekannte_credential_id_ruft_webauthn_nicht_auf():
    _, cookie = authmod.build_authentication_options("example.org")
    credential = {"rawId": authmod.bytes_to_base64url(b"nie-registriert")}
    with patch("astrapi_core.system.auth.webauthn.verify_authentication_response") as mock_verify:
        ok = authmod.verify_authentication(credential, cookie, "example.org", "https://example.org")
    assert ok is False
    mock_verify.assert_not_called()


def test_verify_authentication_erfolg_aktualisiert_sign_count():
    _register_one_credential(sign_count=0)
    _, cookie = authmod.build_authentication_options("example.org")
    credential = {"rawId": authmod.bytes_to_base64url(b"cred-1")}
    with patch(
        "astrapi_core.system.auth.webauthn.verify_authentication_response",
        return_value=_fake_verified_authentication(new_sign_count=5),
    ):
        ok = authmod.verify_authentication(credential, cookie, "example.org", "https://example.org")
    assert ok is True

    from astrapi_core.system.db import _conn

    row = _conn().execute("SELECT sign_count FROM auth_credentials").fetchone()
    assert row["sign_count"] == 5


def test_verify_authentication_erkennt_klon_bei_nicht_synchronisiertem_passkey():
    """sign_count faellt/bleibt gleich bei einem NICHT geraeteuebergreifend
    synchronisierten Credential -- klassisches Klon-Signal, muss abgelehnt
    werden (und darf den gespeicherten Stand nicht ueberschreiben)."""
    _register_one_credential(sign_count=10, backed_up=False)
    _, cookie = authmod.build_authentication_options("example.org")
    credential = {"rawId": authmod.bytes_to_base64url(b"cred-1")}
    with patch(
        "astrapi_core.system.auth.webauthn.verify_authentication_response",
        return_value=_fake_verified_authentication(new_sign_count=3, credential_backed_up=False),
    ):
        ok = authmod.verify_authentication(credential, cookie, "example.org", "https://example.org")
    assert ok is False

    from astrapi_core.system.db import _conn

    row = _conn().execute("SELECT sign_count FROM auth_credentials").fetchone()
    assert row["sign_count"] == 10


def test_verify_authentication_ignoriert_sign_count_bei_synchronisiertem_passkey():
    """Synchronisierte (backed_up) Passkeys duerfen laut Spezifikation
    dauerhaft denselben/niedrigeren sign_count melden -- kein Klon-Signal."""
    _register_one_credential(sign_count=10, backed_up=True)
    _, cookie = authmod.build_authentication_options("example.org")
    credential = {"rawId": authmod.bytes_to_base64url(b"cred-1")}
    with patch(
        "astrapi_core.system.auth.webauthn.verify_authentication_response",
        return_value=_fake_verified_authentication(new_sign_count=0, credential_backed_up=True),
    ):
        ok = authmod.verify_authentication(credential, cookie, "example.org", "https://example.org")
    assert ok is True


# ── Sessions ──────────────────────────────────────────────────────────────


def test_create_session_und_is_logged_in():
    token = authmod.create_session()
    assert authmod.is_logged_in(token) is True


def test_is_logged_in_mit_unbekanntem_token():
    assert authmod.is_logged_in("erfundenes-token") is False


def test_is_logged_in_mit_leerem_token():
    assert authmod.is_logged_in(None) is False
    assert authmod.is_logged_in("") is False


def test_destroy_session_entzieht_zugriff():
    token = authmod.create_session()
    authmod.destroy_session(token)
    assert authmod.is_logged_in(token) is False
