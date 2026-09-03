# core/system/manifest.py
"""Web App Manifest fuer Installierbarkeit unter Android/Chrome (PWA,
"Zum Startbildschirm hinzufuegen"). Wird von ui/app.py::create() automatisch
fuer JEDE App registriert -- Name/Icon kommen aus app.yaml (siehe
system/version.py::get_app_icon_svg()), kein manifest.json pro App noetig.

Immer unauthentifiziert erreichbar (siehe ui/auth_middleware._ALWAYS_EXEMPT)
-- der Browser ruft das ab, bevor irgendeine Session/Login existiert; hinter
dem Login-Gate wuerde daraus eine HTML-Redirect-Seite statt JSON und die
Installierbarkeit bricht.
"""
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .version import DEFAULT_ICON_SVG


def register_manifest(app: FastAPI, display_name: str, icon_svg: str | None = None) -> None:
    """Registriert GET /manifest.json. SVG-Icons sind fuer moderne Chrome/
    Android-Versionen ausreichend (sizes: "any") -- keine PNG-Generierung
    pro App noetig, konsistent mit dem sonstigen SVG-Icon-System."""
    body = {
        "name": display_name,
        "short_name": display_name,
        "start_url": "/",
        "display": "standalone",
        "background_color": "#242424",
        "theme_color": "#242424",
        "icons": [
            {
                "src": icon_svg or DEFAULT_ICON_SVG,
                "sizes": "any",
                "type": "image/svg+xml",
                "purpose": "any",
            }
        ],
    }

    @app.get("/manifest.json", include_in_schema=False)
    def manifest():
        return JSONResponse(body)
