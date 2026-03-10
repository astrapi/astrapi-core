"""app/modules/hosts/api.py – FastAPI-Router"""

from pydantic import BaseModel
from typing import Optional

from core.ui.crud_router import make_crud_router
from .storage import store, KEY


class ItemIn(BaseModel):
    description: Optional[str] = ""
    ip:          Optional[str] = ""
    port:        Optional[int] = 22
    tags:        Optional[str] = ""
    enabled:     bool          = True


router = make_crud_router(store, KEY, ItemIn)

# Modulspezifische Extrarouten hier ergänzen:
# @router.post("/{item_id}/ping", ...)
# def ping_host(item_id: str): ...
