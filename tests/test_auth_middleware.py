"""ui/auth_middleware.py: Login-Gate -- Denylist-Default (alles gesperrt
ausser expliziter Ausnahmeliste), damit eine neu hinzugefuegte Route
automatisch geschuetzt ist. authmod selbst wird gemockt (keine echte
DB/WebAuthn-Verifikation hier, siehe test_auth.py dafuer)."""
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from astrapi_core.ui.auth_middleware import RequireLoginMiddleware


def _make_app(exempt_prefixes=None, exempt_get_paths=None):
    app = FastAPI()
    app.add_middleware(
        RequireLoginMiddleware, exempt_prefixes=exempt_prefixes, exempt_get_paths=exempt_get_paths
    )

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

    # Trailing-Slash-Routendefinition wie im echten crud_router.py
    # (@router.get("/") unter dem /api/debian-Prefix) -- FastAPI leitet
    # ".../api/debian" automatisch auf ".../api/debian/" um, siehe Test
    # test_exempt_get_paths_trailing_slash_variante_ebenfalls_frei.
    @app.get("/api/debian/")
    def list_debian():
        return {"debian": {}}

    @app.post("/api/debian/")
    def create_debian():
        return {"created": True}

    @app.get("/")
    def root():
        return {"root": True}

    @app.get("/api/debian/1/logs")
    def debian_logs():
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


def test_exempt_get_paths_laesst_get_auf_exaktem_pfad_durch():
    """Regressionstest T-332-MIRROR: astrapi-admin konnte nach Aktivierung
    von auth.enabled keine Mirror-Repos mehr lesen, weil /api/debian
    (GET, listet) nirgends exemptiert war."""
    client = _make_app(exempt_get_paths=["/api/debian"])
    with patch("astrapi_core.ui.auth_middleware.authmod.is_configured", return_value=True), patch(
        "astrapi_core.ui.auth_middleware.authmod.is_logged_in", return_value=False
    ):
        r = client.get("/api/debian")
    assert r.status_code == 200


def test_exempt_get_paths_blockt_post_auf_demselben_pfad():
    """Der Kern des Sicherheitsunterschieds zu exempt_prefixes: GET /api/debian
    (Liste) und POST /api/debian (neues Repo anlegen) liegen auf demselben
    Pfad, nur exempt_get_paths darf ausschliesslich GET freigeben -- sonst
    koennte ein unauthentifizierter LAN-Client ein Mirror-Repo auf eine
    fremde URL umbiegen, die dann fleetweit an pacman/apt ausgeliefert wird."""
    client = _make_app(exempt_get_paths=["/api/debian"])
    with patch("astrapi_core.ui.auth_middleware.authmod.is_configured", return_value=True), patch(
        "astrapi_core.ui.auth_middleware.authmod.is_logged_in", return_value=False
    ):
        r = client.post("/api/debian", follow_redirects=False)
    assert r.status_code == 307


def test_exempt_get_paths_trailing_slash_variante_ebenfalls_frei():
    """FastAPI haengt an eine mit '/' endende Routendefinition (z.B.
    crud_router.py's @router.get("/") fuer /api/debian) einen 301 auf die
    Trailing-Slash-Variante -- ohne Normalisierung waere nur die konfigurierte
    Schreibweise frei, die tatsaechlich aufgerufene (nach dem Redirect,
    httpx' follow_redirects=True in mirror_client.py) aber wieder gesperrt."""
    client = _make_app(exempt_get_paths=["/api/debian"])
    with patch("astrapi_core.ui.auth_middleware.authmod.is_configured", return_value=True), patch(
        "astrapi_core.ui.auth_middleware.authmod.is_logged_in", return_value=False
    ):
        r = client.get("/api/debian", follow_redirects=True)
    assert r.status_code == 200
    assert r.json() == {"debian": {}}


def test_exempt_get_paths_ist_exakter_pfad_kein_praefix():
    """Anders als exempt_prefixes: ein Unterpfad (/api/debian/1/logs) ist
    NICHT automatisch mitexemptiert -- sonst waeren ploetzlich beliebige
    GET-Unterrouten offen, nicht nur die eine gemeinte Liste."""
    client = _make_app(exempt_get_paths=["/api/debian"])
    with patch("astrapi_core.ui.auth_middleware.authmod.is_configured", return_value=True), patch(
        "astrapi_core.ui.auth_middleware.authmod.is_logged_in", return_value=False
    ):
        r = client.get("/api/debian/1/logs", follow_redirects=False)
    assert r.status_code == 307


def test_exempt_get_paths_root_laesst_nur_die_wurzel_frei():
    """T-333-MIRROR: die reine Datei-Uebersicht unter '/' (mirror/packages)
    zeigt nichts, was unter /archlinux bzw. /debian nicht schon oeffentlich
    waere -- '/' hier bewusst ueber exempt_get_paths statt exempt_prefixes,
    siehe die naechste Testfunktion fuer den Grund."""
    client = _make_app(exempt_get_paths=["/"])
    with patch("astrapi_core.ui.auth_middleware.authmod.is_configured", return_value=True), patch(
        "astrapi_core.ui.auth_middleware.authmod.is_logged_in", return_value=False
    ):
        assert client.get("/").status_code == 200


def test_exempt_prefixes_mit_wurzel_wuerde_faelschlich_alles_freigeben():
    """Dokumentiert, WARUM '/' nicht in exempt_prefixes gehoert: dessen
    Praefix-Match haengt "/" ans (leere) rstrip("/")-Ergebnis von '/' an,
    "".startswith("/") -- jeder Pfad beginnt mit "/", also waere ausnahmslos
    alles (auch /protected) frei. exempt_get_paths' exakter Vergleich hat
    dieses Problem nicht (siehe Test oben)."""
    client = _make_app(exempt_prefixes=["/"])
    with patch("astrapi_core.ui.auth_middleware.authmod.is_configured", return_value=True), patch(
        "astrapi_core.ui.auth_middleware.authmod.is_logged_in", return_value=False
    ):
        r = client.get("/protected")
    assert r.status_code == 200  # zeigt genau die Falle, die exempt_get_paths vermeidet


def test_exempt_get_paths_root_blockt_andere_pfade_weiterhin():
    client = _make_app(exempt_get_paths=["/"])
    with patch("astrapi_core.ui.auth_middleware.authmod.is_configured", return_value=True), patch(
        "astrapi_core.ui.auth_middleware.authmod.is_logged_in", return_value=False
    ):
        r = client.get("/protected", follow_redirects=False)
    assert r.status_code == 307


def test_ohne_exempt_prefixes_ist_nicht_gelistete_route_trotzdem_gesperrt():
    """Denylist-Default: eine App, die 'exempt_prefixes' vergisst, sperrt
    versehentlich zu viel statt zu wenig -- die sicherere Richtung."""
    client = _make_app(exempt_prefixes=None)
    with patch("astrapi_core.ui.auth_middleware.authmod.is_configured", return_value=True), patch(
        "astrapi_core.ui.auth_middleware.authmod.is_logged_in", return_value=False
    ):
        r = client.get("/api/agent/policy", follow_redirects=False)
    assert r.status_code == 307
