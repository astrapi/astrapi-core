"""app/modules/backup/api.py – FastAPI-Router"""

from pydantic import BaseModel
from typing import Optional

from core.ui.crud_router import make_crud_router
from .storage import store, KEY


class ItemIn(BaseModel):
    name:        Optional[str] = ""
    source:      Optional[str] = ""
    destination: Optional[str] = ""
    schedule:    Optional[str] = ""
    enabled:     bool          = True


router = make_crud_router(store, KEY, ItemIn)

# Modulspezifische Extrarouten hier ergänzen:
# @router.post("/{item_id}/run", ...)
# def run_backup(item_id: str): ...