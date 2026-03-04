"""
astrapi-flask-ui V2 – Einstiegspunkt

Kombinierter Flask+FastAPI Modus:
  - FastAPI bedient  /api/...      (JSON-Endpunkte, OpenAPI)
  - Flask bedient    /             (UI, HTMX-Partials, Modals)
  - Static-Files aus core/static/  via FastAPI StaticFiles

Standalone Flask (ohne FastAPI):
  Einfach main_flask.py verwenden.
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
APP_ROOT     = PROJECT_ROOT / "app"

# core/ im sys.path registrieren damit "from core.ui import ..." funktioniert
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from a2wsgi import WSGIMiddleware

from core.ui import create as create_ui
from app.api.fastapi_app import create as create_api


def create_app() -> FastAPI:
    # ── FastAPI-App (JSON-API) ────────────────────────────────────────────────
    api = create_api()

    # ── Flask-App (UI + HTMX-Partials) ───────────────────────────────────────
    ui = create_ui(app_root=APP_ROOT, extra_init=_register_flask_routes)

    # ── Static-Files (core/static/) ──────────────────────────────────────────
    core_static = PROJECT_ROOT / "core" / "static"
    api.mount("/static", StaticFiles(directory=str(core_static)), name="static")

    # ── Flask als WSGI unter / einbinden ─────────────────────────────────────
    api.mount("/", WSGIMiddleware(ui))

    return api


def _register_flask_routes(flask_app):
    """Projektspezifische Flask-Routen (Modals, UI-Dialoge) registrieren."""
    from app.routes.modals import bp as modals_bp
    flask_app.register_blueprint(modals_bp)


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=5000, reload=True)

