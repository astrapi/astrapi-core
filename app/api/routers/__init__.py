"""
app/api/routers/__init__.py

Exportiert alle FastAPI-Router für den Import in fastapi_app.py.

Neue Router:
  1. Datei anlegen: app/api/routers/mein_router.py
  2. Hier ergänzen:
       from .mein_router import router as mein_router
       __all__ = [..., "mein_router"]
"""

from .items import router as items_router

__all__ = ["items_router"]
