"""
astrapi-flask-ui V3 – Einstiegspunkt (FastAPI + Flask)

FastAPI  → /api/...       JSON-Endpunkte, OpenAPI, Swagger
Flask    → /              UI, HTMX-Partials, Modals

Start:
    python main.py              # Port 5000 (Standard)
    python main.py --port 8080  # anderer Port
    python main.py --no-reload  # ohne File-Watcher
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
APP_ROOT     = PROJECT_ROOT / "app"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from a2wsgi import WSGIMiddleware

from core.ui import create as create_ui
from core.ui.module_registry import load_modules
from app.api.fastapi_app import create as create_api


def create_app() -> FastAPI:
    modules = load_modules(APP_ROOT)
    api = create_api(modules=modules)
    ui  = create_ui(app_root=APP_ROOT, modules=modules)

    core_static = PROJECT_ROOT / "core" / "ui" / "static"
    api.mount("/static", StaticFiles(directory=str(core_static)), name="static")
    api.mount("/", WSGIMiddleware(ui))

    return api


app = create_app()


if __name__ == "__main__":
    import argparse
    import uvicorn
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--no-reload", dest="reload", action="store_false", default=True)
    args = parser.parse_args()
    uvicorn.run("main:app", host=args.host, port=args.port, reload=args.reload)
