"""modules/users/ui/__init__.py -- Admin-Verwaltung der Nutzerliste selbst
(anlegen/löschen/Passkey zurücksetzen/einladen), zu unterscheiden von der
Registrierungs-/Einladungs-Zeremonie unter /auth/* (siehe
test_multi_user_routes.py)."""
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from astrapi_core.modules.users.ui import router as users_router
from astrapi_core.system import auth as authmod
from astrapi_core.system import auth_invites, db, secrets


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path):
    db._db_path = tmp_path / "test.db"
    db._local.conn = None
    secrets._key_path_prod = None
    secrets._key_path_dev = None
    secrets.configure(key_path=tmp_path / ".secret.key")
    auth_invites._pending.clear()
    yield


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(users_router)
    return TestClient(app)


def _login_as(client, user_id: int) -> None:
    token = authmod.create_session(user_id)
    client.cookies.set(authmod.SESSION_COOKIE_NAME, token)


# ── GET /ui/users/create ─────────────────────────────────────────────────


def test_create_dialog_ohne_login_verboten(client):
    r = client.get("/ui/users/create")
    assert r.status_code == 403


def test_create_dialog_als_nicht_admin_verboten(client):
    bob = authmod.create_user("bob", "Bob")
    _login_as(client, bob)
    r = client.get("/ui/users/create")
    assert r.status_code == 403


def test_create_dialog_als_admin_ok(client):
    alice = authmod.create_user("alice", "Alice")
    authmod.set_admin(alice)
    _login_as(client, alice)
    with patch("astrapi_core.modules.users.ui.render") as mock_render:
        mock_render.return_value = "ok"
        r = client.get("/ui/users/create")
    assert r.status_code == 200
    assert mock_render.call_args[0][1] == "users/dialogs/create/modal.html"


# ── POST /ui/users (Nutzer direkt anlegen) ───────────────────────────────


def test_create_neuer_nutzer_ohne_username_400(client):
    alice = authmod.create_user("alice")
    authmod.set_admin(alice)
    _login_as(client, alice)
    r = client.post("/ui/users", json={})
    assert r.status_code == 400


def test_create_neuer_nutzer_doppelter_username_409(client):
    alice = authmod.create_user("alice")
    authmod.set_admin(alice)
    authmod.create_user("bob")
    _login_as(client, alice)
    r = client.post("/ui/users", json={"username": "bob"})
    assert r.status_code == 409


def test_create_neuer_nutzer_als_nicht_admin_verboten(client):
    bob = authmod.create_user("bob")
    _login_as(client, bob)
    r = client.post("/ui/users", json={"username": "eve"})
    assert r.status_code == 403
    assert "eve" not in {u["username"] for u in authmod.list_users()}


def test_create_neuer_nutzer_erfolgreich_legt_nutzer_ohne_zugangsdaten_an(client):
    """Kernpunkt der Umstellung: der Admin vergibt hier direkt einen
    Benutzernamen -- anders als vorher gibt es dabei keine Passkey-/
    Passwort-Zeremonie, der neue Nutzer kann sich noch nicht anmelden
    (dafür ist danach der separate "einladen"-Link/QR-Code da)."""
    alice = authmod.create_user("alice")
    authmod.set_admin(alice)
    _login_as(client, alice)
    with patch("astrapi_core.modules.users.ui.render") as mock_render:
        mock_render.return_value = "ok"
        r = client.post("/ui/users", json={"username": "carol", "display_name": "Carol"})
    assert r.status_code == 200
    carol = next(u for u in authmod.list_users() if u["username"] == "carol")
    assert carol["display_name"] == "Carol"
    assert authmod.has_user_password(carol["id"]) is False
    assert authmod.list_credentials() == [] or all(
        c["user_id"] != carol["id"] for c in authmod.list_credentials()
    )


def test_create_neuer_nutzer_ohne_display_name_nutzt_username(client):
    alice = authmod.create_user("alice")
    authmod.set_admin(alice)
    _login_as(client, alice)
    with patch("astrapi_core.modules.users.ui.render") as mock_render:
        mock_render.return_value = "ok"
        client.post("/ui/users", json={"username": "dave"})
    dave = next(u for u in authmod.list_users() if u["username"] == "dave")
    assert dave["display_name"] == "dave"


# ── GET /ui/users/{id}/invite (Link + QR für bestehenden Nutzer) ─────────


def test_invite_dialog_unbekannter_nutzer_404(client):
    alice = authmod.create_user("alice")
    authmod.set_admin(alice)
    _login_as(client, alice)
    r = client.get("/ui/users/9999/invite")
    assert r.status_code == 404


def test_invite_dialog_als_nicht_admin_verboten(client):
    bob = authmod.create_user("bob")
    carol = authmod.create_user("carol")
    _login_as(client, bob)
    r = client.get(f"/ui/users/{carol}/invite")
    assert r.status_code == 403


def test_invite_dialog_erzeugt_token_fuer_bestehenden_nutzer(client):
    alice = authmod.create_user("alice")
    authmod.set_admin(alice)
    carol = authmod.create_user("carol", "Carol")
    _login_as(client, alice)
    with patch("astrapi_core.modules.users.ui.render") as mock_render:
        mock_render.return_value = "ok"
        r = client.get(f"/ui/users/{carol}/invite")
    assert r.status_code == 200
    ctx = mock_render.call_args[0][2]
    assert ctx["user"]["id"] == carol
    assert "<svg" in ctx["qr_svg"]
    assert "/auth/invite/" in ctx["invite_url"]

    token = ctx["invite_url"].rsplit("/", 1)[-1]
    info = auth_invites.peek_invite_token(token)
    assert info is not None
    assert info["user_id"] == carol
    assert info["invited_by_user_id"] == alice


def test_invite_dialog_setzt_bestehende_credentials_nicht_zurueck(client):
    """Unterschied zu "Passkey zurücksetzen": einladen erzeugt nur einen
    weiteren Link, löscht aber keine bereits registrierten Passkeys."""
    alice = authmod.create_user("alice")
    authmod.set_admin(alice)
    carol = authmod.create_user("carol")
    authmod.set_user_password(carol, "irgendein-passwort")
    _login_as(client, alice)
    with patch("astrapi_core.modules.users.ui.render") as mock_render:
        mock_render.return_value = "ok"
        client.get(f"/ui/users/{carol}/invite")
    assert authmod.has_user_password(carol) is True
