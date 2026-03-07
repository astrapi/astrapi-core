"""app/modules/backup/api.py – FastAPI-Router"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from .storage import store, KEY

_LABEL    = KEY.capitalize()
_SINGULAR = KEY

router = APIRouter()


class ItemIn(BaseModel):
    name:        Optional[str] = ""
    source:      Optional[str] = ""
    destination: Optional[str] = ""
    schedule:    Optional[str] = ""
    enabled:     bool          = True


@router.get("/",           summary=f"List {_LABEL}")
def list_items():
    items = store.list()
    return {KEY: items, "total": len(items)}

@router.get("/{item_id}",  summary=f"Get {_SINGULAR}")
def get_item(item_id: str):
    item = store.get(item_id)
    if item is None:
        raise HTTPException(404, f"{_SINGULAR} '{item_id}' nicht gefunden")
    return item

@router.post("/",          summary=f"Create {_SINGULAR}", status_code=201)
def create_item(item_id: str, item: ItemIn):
    try:
        return {"created": item_id, _SINGULAR: store.create(item_id, item.model_dump())}
    except KeyError as e:
        raise HTTPException(409, str(e))

@router.put("/{item_id}",  summary=f"Update {_SINGULAR}")
def edit_item(item_id: str, item: ItemIn):
    try:
        return {"updated": item_id, _SINGULAR: store.update(item_id, item.model_dump())}
    except KeyError as e:
        raise HTTPException(404, str(e))

@router.patch("/{item_id}/toggle", summary=f"Toggle {_SINGULAR}")
def toggle_item(item_id: str):
    try:
        return {"item_id": item_id, "enabled": store.toggle(item_id)}
    except KeyError as e:
        raise HTTPException(404, str(e))

@router.delete("/{item_id}", summary=f"Delete {_SINGULAR}", status_code=204)
def delete_item(item_id: str):
    try:
        store.delete(item_id)
    except KeyError as e:
        raise HTTPException(404, str(e))