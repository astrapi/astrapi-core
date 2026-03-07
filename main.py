"""
astrapi-flask-ui V3 – Einstiegspunkt (FastAPI + Flask)

FastAPI  → /api/...       JSON-Endpunkte, OpenAPI, Swagger
Flask    → /              UI, HTMX-Partials, Modals

Start:
    python main.py              # Port 5000 (Standard)
    python main.py 8080         # Port 8080
    python main.py --port 8080  # alternativ
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
from app.api.fastapi_app import create as create_api


def create_app() -> FastAPI:
    api = create_api()
    ui  = create_ui(app_root=APP_ROOT)

    core_static = PROJECT_ROOT / "core" / "ui" / "static"
    api.mount("/static", StaticFiles(directory=str(core_static)), name="static")
    api.mount("/", WSGIMiddleware(ui))

    return api


app = create_app()


def _parse_port() -> int:
    """Liest den Port aus den Kommandozeilenargumenten.

    Unterstützte Formate:
        python main.py 8080
        python main.py --port 8080
    """
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--port" and i + 1 < len(args):
            return int(args[i + 1])
        if arg.isdigit():
            return int(arg)
    return 5000  # Standard


if __name__ == "__main__":
    import uvicorn
    port = _parse_port()
    print(f"Starting on http://0.0.0.0:{port}")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
