"""ui/auth_routes.py: Passwort-Endpunkte + das Cookie-Verhalten, das den
Passwort-Fallback über reines HTTP erst nutzbar macht (kein `Secure`-Flag,
wenn die Anfrage selbst nicht über HTTPS kam -- siehe _cookie_kw())."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from astrapi_core.system import auth as authmod
from astrapi_core.system import db, secrets
from astrapi_core.ui.auth_routes import router as auth_router


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path):
    db._db_path = tmp_path / "test.db"
    db._local.conn = None
    secrets._key_path_prod = None
    secrets._key_path_dev = None
    secrets.configure(key_path=tmp_path / ".secret.key")
    yield


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(auth_router)
    return TestClient(app)


def test_register_password_bootstrap_setzt_passwort_und_loggt_ein(client):
    r = client.post("/auth/register/password", json={"password": "acht-zeichen"})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert authmod.has_password() is True
    assert authmod.SESSION_COOKIE_NAME in r.cookies


def test_register_password_zu_kurz_wird_abgelehnt(client):
    r = client.post("/auth/register/password", json={"password": "kurz"})
    assert r.status_code == 400
    assert authmod.has_password() is False


def test_register_password_ohne_bootstrap_und_ohne_session_verboten(client):
    authmod.set_password("schon-gesetzt")
    r = client.post("/auth/register/password", json={"password": "neues-passwort"})
    assert r.status_code == 403


def test_login_password_erfolgreich(client):
    authmod.set_password("richtig-123")
    r = client.post("/auth/login/password", json={"password": "richtig-123"})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert authmod.SESSION_COOKIE_NAME in r.cookies


def test_login_password_falsch(client):
    authmod.set_password("richtig-123")
    r = client.post("/auth/login/password", json={"password": "falsch"})
    assert r.status_code == 401


def test_session_cookie_ist_ueber_http_nicht_secure(client):
    """Kernpunkt des Passwort-Fallbacks: ein 'Secure'-Cookie würde der
    Browser über reines HTTP nie zurückschicken -- sofortiger Logout nach
    dem Login. TestClient spricht per Default http://testserver."""
    r = client.post("/auth/register/password", json={"password": "acht-zeichen"})
    set_cookie_header = r.headers.get("set-cookie", "")
    assert "Secure" not in set_cookie_header
    assert "HttpOnly" in set_cookie_header
