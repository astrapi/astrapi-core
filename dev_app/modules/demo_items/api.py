"""dev_app/modules/demo_items/api.py – FastAPI-Router"""

from pydantic import BaseModel
from typing import Optional

from astrapi.core.ui.crud_router import make_crud_router
from .storage import store, KEY


class ItemIn(BaseModel):
    description: Optional[str] = ""
    category:    Optional[str] = ""
    count:       Optional[int] = 0
    note:        Optional[str] = ""
    enabled:     bool          = True


router = make_crud_router(store, KEY, ItemIn)
