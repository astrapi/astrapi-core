"""
app/api/fastapi_app.py  –  FastAPI-Factory V3

Registriert automatisch alle Modul-Router aus app/modules/.
"""
from pathlib import Path
from fastapi import FastAPI

APP_ROOT = Path(__file__).resolve().parents[1]


def create() -> FastAPI:
    app = FastAPI(
        title="AstrapiControl API",
        version="3.0.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    # ── Modul-Router automatisch registrieren ─────────────────────────────────
    from core.ui.module_registry import load_modules, register_fastapi_modules
    modules = load_modules(APP_ROOT)
    register_fastapi_modules(app, modules)

    # ── Health-Check ──────────────────────────────────────────────────────────
    @app.get("/api/health", tags=["system"])
    def health():
        return {"status": "ok"}

    return app
