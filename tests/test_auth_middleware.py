"""ui/auth_middleware.py: Login-Gate -- Denylist-Default (alles gesperrt
ausser expliziter Ausnahmeliste), damit eine neu hinzugefuegte Route
automatisch geschuetzt ist. authmod selbst wird gemockt (keine echte
DB/WebAuthn-Verifikation hier, siehe test_auth.py dafuer)."""
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from astrapi_core.ui.auth_middleware import RequireLoginMiddleware


def _make_app(exempt_prefixes=None):
    app = FastAPI()
    app.add_middleware(RequireLoginMiddleware, exempt_prefixes=exempt_prefixes)

    @app.get("/protected")
    def protected():
        return {"ok": True}

    @app.get("/api/agent/policy")
    def agent_policy():
        return {"ok": True}

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/static/css/app.css")
    def static_css():
        return {"ok": True}

    @app.get("/manifest.json")
    def manifest():
        return {"ok": True}

    return TestClient(app)


def test_ohne_konfigurierte_anmeldemethode_leitet_zu_register_um():
    client = _make_app()
    with patch("astrapi_core.ui.auth_middleware.authmod.is_configured", return_value=False):
        r = client.get("/protected", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == "/auth/register"


def test_ohne_gueltige_session_leitet_zu_login_um():
    client = _make_app()
    with patch("astrapi_core.ui.auth_middleware.authmod.is_configured", return_value=True), patch(
        "astrapi_core.ui.auth_middleware.authmod.is_logged_in", return_value=False
    ):
        r = client.get("/protected", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"].startswith("/auth/login")


def test_mit_gueltiger_session_kommt_durch():
    client = _make_app()
    with patch("astrapi_core.ui.auth_middleware.authmod.is_configured", return_value=True), patch(
        "astrapi_core.ui.auth_middleware.authmod.is_logged_in", return_value=True
    ):
        r = client.get("/protected")
    assert r.status_code == 200


def test_app_eigene_ausnahme_bleibt_ohne_session_erreichbar():
    client = _make_app(exempt_prefixes=["/api/agent"])
    with patch("astrapi_core.ui.auth_middleware.authmod.is_configured", return_value=True), patch(
        "astrapi_core.ui.auth_middleware.authmod.is_logged_in", return_value=False
    ):
        r = client.get("/api/agent/policy")
    assert r.status_code == 200


def test_health_und_static_sind_immer_ausgenommen():
    client = _make_app()
    with patch("astrapi_core.ui.auth_middleware.authmod.is_configured", return_value=True), patch(
        "astrapi_core.ui.auth_middleware.authmod.is_logged_in", return_value=False
    ):
        assert client.get("/health").status_code == 200
        assert client.get("/static/css/app.css").status_code == 200


def test_manifest_json_ist_immer_ausgenommen():
    """Der Browser ruft /manifest.json ab, bevor irgendeine Session
    existiert (Installierbarkeits-Check) -- hinter dem Login-Gate wuerde
    daraus eine HTML-Redirect-Seite statt JSON, PWA-Installation bricht."""
    client = _make_app()
    with patch("astrapi_core.ui.auth_middleware.authmod.is_configured", return_value=True), patch(
        "astrapi_core.ui.auth_middleware.authmod.is_logged_in", return_value=False
    ):
        assert client.get("/manifest.json").status_code == 200


def test_ohne_exempt_prefixes_ist_nicht_gelistete_route_trotzdem_gesperrt():
    """Denylist-Default: eine App, die 'exempt_prefixes' vergisst, sperrt
    versehentlich zu viel statt zu wenig -- die sicherere Richtung."""
    client = _make_app(exempt_prefixes=None)
    with patch("astrapi_core.ui.auth_middleware.authmod.is_configured", return_value=True), patch(
        "astrapi_core.ui.auth_middleware.authmod.is_logged_in", return_value=False
    ):
        r = client.get("/api/agent/policy", follow_redirects=False)
    assert r.status_code == 307
