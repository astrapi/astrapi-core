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


# ── Passwort-Fallback ─────────────────────────────────────────────────────


def test_has_password_ist_am_anfang_leer():
    assert authmod.has_password() is False


def test_is_configured_ist_am_anfang_falsch():
    assert authmod.is_configured() is False


def test_set_password_und_verify_password_erfolgreich():
    authmod.set_password("ein-sicheres-passwort")
    assert authmod.has_password() is True
    assert authmod.is_configured() is True
    assert authmod.verify_password("ein-sicheres-passwort") is True


def test_verify_password_falsches_passwort_schlaegt_fehl():
    authmod.set_password("richtig-123")
    assert authmod.verify_password("falsch-456") is False


def test_verify_password_ohne_gesetztes_passwort_schlaegt_fehl():
    assert authmod.verify_password("irgendwas") is False


def test_verify_password_sperrt_nach_fuenf_fehlversuchen():
    authmod.set_password("richtig-123")
    for _ in range(5):
        assert authmod.verify_password("falsch") is False
    # Sechster Versuch, korrektes Passwort -- trotzdem gesperrt, da die
    # Sperre den Passwortvergleich selbst gar nicht erst durchführt.
    assert authmod.verify_password("richtig-123") is False


def test_verify_password_sperre_laeuft_nach_zeit_ab():
    authmod.set_password("richtig-123")
    with patch("astrapi_core.system.auth.time.time", return_value=1_000_000_000):
        for _ in range(5):
            authmod.verify_password("falsch")
    with patch("astrapi_core.system.auth.time.time", return_value=1_000_000_000 + 31):
        assert authmod.verify_password("richtig-123") is True


def test_verify_password_erfolg_setzt_fehlversuche_zurueck():
    authmod.set_password("richtig-123")
    authmod.verify_password("falsch")
    authmod.verify_password("falsch")
    assert authmod.verify_password("richtig-123") is True
    # Zaehler zurueckgesetzt -- vier weitere Fehlversuche noch unterhalb
    # der Schwelle, kein Lockout.
    for _ in range(4):
        assert authmod.verify_password("falsch") is False
    assert authmod.verify_password("richtig-123") is True


# ── Multi-User (astrapi-hub-Vault: Multi-User astrapi-sync) ─────────────


def test_default_user_id_ist_idempotent():
    """Wiederholte Aufrufe liefern dieselbe Zeile, keine Duplikate."""
    first = authmod._default_user_id()
    second = authmod._default_user_id()
    assert first == second
    assert len(authmod.list_users()) == 1


def test_default_user_id_uebernimmt_alten_globalen_webauthn_handle():
    """Rueckwaertskompatibilitaet: existierte schon ein globaler Handle
    (Alt-Installation vor der Multi-User-Erweiterung), muss der Default-User
    GENAU diesen uebernehmen -- sonst wuerden bereits registrierte Passkeys
    (z.B. astrapi-admin) nach der Migration einen neuen, nicht mehr
    passenden Handle sehen."""
    from astrapi_core.system.db import kv_set

    legacy = authmod.bytes_to_base64url(b"alter-handle-32-bytes-lang-genug")
    kv_set("_auth", "user_handle", legacy)

    default_id = authmod._default_user_id()

    assert authmod._user_handle(default_id) == b"alter-handle-32-bytes-lang-genug"


def test_create_user_und_get_user():
    uid = authmod.create_user("alice", "Alice")
    user = authmod.get_user(uid)
    assert user["username"] == "alice"
    assert user["display_name"] == "Alice"


def test_get_user_unbekannte_id_ist_none():
    assert authmod.get_user(999) is None


def test_list_users_enthaelt_default_und_eingeladene_nutzer():
    authmod._default_user_id()
    authmod.create_user("bob", "Bob")
    usernames = {u["username"] for u in authmod.list_users()}
    assert usernames == {"_default", "bob"}


def test_zwei_nutzer_bekommen_unterschiedliche_webauthn_handles():
    """Jede Person braucht einen eigenen WebAuthn-User-Handle, sonst
    kollidieren die Passkey-Manager mehrerer Personen auf demselben rp_id."""
    a = authmod.create_user("alice")
    b = authmod.create_user("bob")
    assert authmod._user_handle(a) != authmod._user_handle(b)


def test_registration_und_login_fuer_zwei_unabhaengige_nutzer():
    """Kernszenario der Mandantentrennung: zwei Personen registrieren
    unabhaengig voneinander eine Passkey, der Login identifiziert danach
    korrekt WER sich eingeloggt hat (get_current_user())."""
    alice_id = authmod.create_user("alice", "Alice")
    bob_id = authmod.create_user("bob", "Bob")

    _, reg_cookie_a = authmod.build_registration_options("example.org", "Test", alice_id, "alice", "Alice")
    with patch(
        "astrapi_core.system.auth.webauthn.verify_registration_response",
        return_value=_fake_verified_registration(credential_id=b"cred-alice"),
    ):
        assert authmod.verify_registration({"id": "x"}, reg_cookie_a, "example.org", "https://example.org", "L", alice_id)

    _, reg_cookie_b = authmod.build_registration_options("example.org", "Test", bob_id, "bob", "Bob")
    with patch(
        "astrapi_core.system.auth.webauthn.verify_registration_response",
        return_value=_fake_verified_registration(credential_id=b"cred-bob"),
    ):
        assert authmod.verify_registration({"id": "x"}, reg_cookie_b, "example.org", "https://example.org", "L", bob_id)

    _, auth_cookie = authmod.build_authentication_options("example.org")
    credential = {"rawId": authmod.bytes_to_base64url(b"cred-bob")}
    with patch(
        "astrapi_core.system.auth.webauthn.verify_authentication_response",
        return_value=_fake_verified_authentication(new_sign_count=1),
    ):
        user = authmod.verify_authentication_full(credential, auth_cookie, "example.org", "https://example.org")

    assert user["username"] == "bob"
    assert user["id"] == bob_id


def test_verify_authentication_bool_wrapper_bleibt_kompatibel():
    """verify_authentication() (bool) muss weiterhin exakt dasselbe Ergebnis
    liefern wie verify_authentication_full() is not None -- bestehende
    Aufrufer (z.B. auth_routes.py vor dieser Erweiterung) duerfen sich
    nicht aendern."""
    _register_one_credential(sign_count=0)
    _, cookie = authmod.build_authentication_options("example.org")
    credential = {"rawId": authmod.bytes_to_base64url(b"cred-1")}
    with patch(
        "astrapi_core.system.auth.webauthn.verify_authentication_response",
        return_value=_fake_verified_authentication(new_sign_count=5),
    ):
        assert authmod.verify_authentication(credential, cookie, "example.org", "https://example.org") is True


def test_create_session_ordnet_user_id_zu():
    alice_id = authmod.create_user("alice")
    token = authmod.create_session(alice_id)
    user = authmod.get_current_user(token)
    assert user["id"] == alice_id
    assert user["username"] == "alice"


def test_create_session_ohne_user_id_nutzt_default_user():
    """Rueckwaertskompatibilitaet: kein user_id angegeben (z.B. astrapi-admin)
    -> impliziter Default-User, exakt das Verhalten vor dieser Erweiterung."""
    token = authmod.create_session()
    user = authmod.get_current_user(token)
    assert user["username"] == "_default"


def test_get_current_user_ohne_token_ist_none():
    assert authmod.get_current_user(None) is None
    assert authmod.get_current_user("") is None


def test_get_current_user_mit_abgelaufener_session_ist_none():
    token = authmod.create_session()
    authmod.destroy_session(token)
    assert authmod.get_current_user(token) is None


def test_migration_bestandskredentiale_ohne_user_id_werden_default_user_zugeordnet():
    """Simuliert eine Alt-DB (Schema vor der Multi-User-Erweiterung): eine
    Passkey wurde registriert, BEVOR die user_id-Spalte existierte. Nach
    einer erneuten Migration (_ensure_tables()) muss sie automatisch dem
    Default-User zugeordnet sein -- kein manueller Schritt fuer
    Bestandsinstallationen (astrapi-admin!) noetig."""
    from astrapi_core.system.db import _conn

    con = _conn()
    con.execute("DROP TABLE IF EXISTS auth_credentials")
    con.execute("""
        CREATE TABLE auth_credentials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            credential_id BLOB NOT NULL UNIQUE,
            public_key BLOB NOT NULL,
            sign_count INTEGER NOT NULL DEFAULT 0,
            label TEXT NOT NULL DEFAULT '',
            backed_up INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            last_used_at TEXT NOT NULL DEFAULT ''
        )
    """)
    con.execute(
        "INSERT INTO auth_credentials (credential_id, public_key, label, created_at) VALUES (?,?,?,?)",
        (b"alt-cred", b"alt-key", "Alter Laptop", "2026-01-01T00:00:00"),
    )
    con.commit()

    authmod._ensure_tables()

    row = con.execute("SELECT user_id FROM auth_credentials WHERE credential_id=?", (b"alt-cred",)).fetchone()
    assert row["user_id"] == authmod._default_user_id()
