"""
app/api/fastapi_app.py  –  FastAPI-App Factory

Erstellt die FastAPI-Instanz und registriert alle API-Router.
Wird von main.py via  create_api()  aufgerufen.

Neue Router hinzufügen:
  1. Datei anlegen:  app/api/routers/mein_router.py
  2. Hier importieren und einbinden:
       from .routers.mein_router import router as mein_router
       app.include_router(mein_router, prefix="/mein-resource")
"""

from fastapi import FastAPI
from .routers import items_router


def create() -> FastAPI:
    """Erstellt die FastAPI-Instanz mit allen Routen."""

    app = FastAPI(
        title="AstrapiFlaskUi API",
        version="2.0.0",
        # Swagger UI unter /api/docs – eigener Pfad damit / für Flask frei bleibt
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    # ── Router einbinden ──────────────────────────────────────────────────────
    app.include_router(items_router, prefix="/api/items", tags=["items"])

    # ── Health-Check ──────────────────────────────────────────────────────────
    @app.get("/api/health", tags=["system"], include_in_schema=True)
    def health():
        return {"status": "ok"}

    return app
