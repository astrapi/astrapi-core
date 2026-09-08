"""ui/multi_user_routes.py -- Nutzerverwaltung/Einladung, nur eingebunden
bei app.yaml: auth.multi_user: true (astrapi-admin bindet das nicht ein,
siehe test_auth_routes.py fürs Single-Owner-Verhalten)."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from astrapi_core.system import auth as authmod
from astrapi_core.system import auth_invites, db, secrets
from astrapi_core.ui import settings_registry
from astrapi_core.ui.multi_user_routes import router as multi_user_router


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path):
    db._db_path = tmp_path / "test.db"
    db._local.conn = None
    secrets._key_path_prod = None
    secrets._key_path_dev = None
    secrets.configure(key_path=tmp_path / ".secret.key")
    auth_invites._pending.clear()
    # _rp_config() (ui/app.py::create() setzt das normalerweise aus
    # app.yaml) -- hier direkt gesetzt, da die Tests nur den Router isoliert
    # mounten, nicht die volle App-Factory durchlaufen.
    settings_registry.set("AUTH_RP_ID", "example.org")
    yield


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(multi_user_router)
    return TestClient(app)


def _login_as(client, user_id: int) -> None:
    token = authmod.create_session(user_id)
    client.cookies.set(authmod.SESSION_COOKIE_NAME, token)


def _fake_verified_registration(**overrides):
    base = dict(
        credential_id=b"cred-invited",
        credential_public_key=b"pubkey-invited",
        sign_count=0,
        credential_backed_up=False,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


# ── /auth/users ──────────────────────────────────────────────────────────


def test_users_page_ohne_login_leitet_um(client):
    r = client.get("/auth/users", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert "/auth/login" in r.headers["location"]


def test_users_page_mit_login_zeigt_liste(client):
    """render() braucht globalen Template-Kontext (app_name etc.), den die
    volle App-Factory (ui/app.py::create()) setzt -- hier isoliert getestet,
    deshalb render() gemockt (gleiches Muster wie
    test_policies_export_import.py in astrapi-admin)."""
    alice = authmod.create_user("alice", "Alice")
    _login_as(client, alice)
    with patch("astrapi_core.ui.multi_user_routes.render") as mock_render:
        mock_render.return_value = "ok"
        client.get("/auth/users")
    ctx = mock_render.call_args[0][2]
    assert any(u["username"] == "alice" for u in ctx["users"])
    assert ctx["current_user"]["id"] == alice


def test_invite_ohne_login_verboten(client):
    r = client.post("/auth/users/invite")
    assert r.status_code == 403


def test_invite_mit_login_liefert_link(client):
    alice = authmod.create_user("alice")
    _login_as(client, alice)
    r = client.post("/auth/users/invite")
    assert r.status_code == 200
    body = r.json()
    assert body["url"].startswith("/auth/invite/")


# ── /auth/invite/{token} ─────────────────────────────────────────────────


def test_invite_page_gueltiger_token(client):
    alice = authmod.create_user("alice", "Alice")
    token = auth_invites.create_invite_token(alice)
    with patch("astrapi_core.ui.multi_user_routes.render") as mock_render:
        mock_render.return_value = "ok"
        client.get(f"/auth/invite/{token}")
    ctx = mock_render.call_args[0][2]
    assert ctx["invalid"] is False
    assert ctx["inviter"]["username"] == "alice"


def test_invite_page_unbekannter_token(client):
    with patch("astrapi_core.ui.multi_user_routes.render") as mock_render:
        mock_render.return_value = "ok"
        client.get("/auth/invite/nie-erzeugt")
    ctx = mock_render.call_args[0][2]
    assert ctx["invalid"] is True
    assert mock_render.call_args.kwargs.get("status_code") == 410


def test_invite_options_unbekannter_token(client):
    r = client.post("/auth/invite/nie-erzeugt/options", json={"username": "bob"})
    assert r.status_code == 410


def test_invite_options_ohne_username(client):
    alice = authmod.create_user("alice")
    token = auth_invites.create_invite_token(alice)
    r = client.post(f"/auth/invite/{token}/options", json={})
    assert r.status_code == 400


def test_invite_options_legt_neuen_nutzer_an(client):
    alice = authmod.create_user("alice")
    token = auth_invites.create_invite_token(alice)
    r = client.post(f"/auth/invite/{token}/options", json={"username": "bob", "display_name": "Bob"})
    assert r.status_code == 200
    usernames = {u["username"] for u in authmod.list_users()}
    assert "bob" in usernames


def test_invite_verify_unbekannter_token(client):
    r = client.post("/auth/invite/nie-erzeugt/verify", json={"id": "x"})
    assert r.status_code == 410


def test_kompletter_einladungs_flow_registriert_eigenstaendigen_nutzer(client):
    """End-to-End: Alice laedt ein, Bob registriert seine eigene Passkey --
    Bob landet als EIGENER, unabhaengiger Account eingeloggt, nicht als
    weiteres Geraet von Alice."""
    alice = authmod.create_user("alice", "Alice")
    token = auth_invites.create_invite_token(alice)

    opt_res = client.post(f"/auth/invite/{token}/options", json={"username": "bob", "display_name": "Bob"})
    assert opt_res.status_code == 200
    bob_id = next(u["id"] for u in authmod.list_users() if u["username"] == "bob")

    with patch(
        "astrapi_core.system.auth.webauthn.verify_registration_response",
        return_value=_fake_verified_registration(),
    ):
        verify_res = client.post(f"/auth/invite/{token}/verify", json={"id": "x"})

    assert verify_res.status_code == 200
    assert verify_res.json()["ok"] is True
    assert authmod.SESSION_COOKIE_NAME in verify_res.cookies

    session_token = verify_res.cookies[authmod.SESSION_COOKIE_NAME]
    logged_in_user = authmod.get_current_user(session_token)
    assert logged_in_user["id"] == bob_id
    assert logged_in_user["username"] == "bob"
    assert logged_in_user["id"] != alice


def test_einladungs_token_ist_nach_verify_verbraucht(client):
    alice = authmod.create_user("alice")
    token = auth_invites.create_invite_token(alice)
    client.post(f"/auth/invite/{token}/options", json={"username": "bob"})

    with patch(
        "astrapi_core.system.auth.webauthn.verify_registration_response",
        return_value=_fake_verified_registration(),
    ):
        client.post(f"/auth/invite/{token}/verify", json={"id": "x"})

    # Zweiter Versuch mit demselben Token -- muss fehlschlagen (Einmalnutzung).
    r = client.post(f"/auth/invite/{token}/verify", json={"id": "x"})
    assert r.status_code == 410
