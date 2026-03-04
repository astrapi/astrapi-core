"""
app/api/routers/items.py  –  Items REST-API

Beispiel-Router nach dem backupctl-Muster.
Endpunkte werden unter /api/items/... eingebunden (siehe fastapi_app.py).

Passe die Datenstruktur und den Storage-Layer an dein Projekt an.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter()


# ── Datenmodell ───────────────────────────────────────────────────────────────

class Item(BaseModel):
    name: str
    description: Optional[str] = None
    host: Optional[str] = None
    enabled: bool = True


class ItemUpdate(BaseModel):
    description: Optional[str] = None
    host: Optional[str] = None
    enabled: Optional[bool] = None


# ── In-Memory Storage (ersetzen durch echten Storage-Layer) ──────────────────
_items: dict[str, dict] = {
    "beispiel-01": {
        "name": "beispiel-01",
        "description": "Beispiel-Eintrag A",
        "host": "server-01.example.com",
        "enabled": True,
    },
    "beispiel-02": {
        "name": "beispiel-02",
        "description": "Beispiel-Eintrag B",
        "host": "server-02.example.com",
        "enabled": False,
    },
}


# ── Endpunkte ─────────────────────────────────────────────────────────────────

@router.get("/")
def list_items():
    """Alle Items zurückgeben."""
    return {"items": list(_items.values()), "total": len(_items)}


@router.get("/{item_id}")
def get_item(item_id: str):
    """Einzelnes Item zurückgeben."""
    item = _items.get(item_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"Item '{item_id}' nicht gefunden")
    return item


@router.post("/create")
def create_item(item: Item):
    """Neues Item erstellen."""
    if item.name in _items:
        raise HTTPException(status_code=409, detail=f"Item '{item.name}' existiert bereits")
    _items[item.name] = item.model_dump()
    return {"created": item.name, "item": _items[item.name]}


@router.put("/{item_id}/edit")
def edit_item(item_id: str, update: ItemUpdate):
    """Item bearbeiten."""
    if item_id not in _items:
        raise HTTPException(status_code=404, detail=f"Item '{item_id}' nicht gefunden")
    for field, value in update.model_dump(exclude_none=True).items():
        _items[item_id][field] = value
    return {"updated": item_id, "item": _items[item_id]}


@router.post("/{item_id}/toggle")
def toggle_item(item_id: str):
    """Item aktivieren/deaktivieren."""
    if item_id not in _items:
        raise HTTPException(status_code=404, detail=f"Item '{item_id}' nicht gefunden")
    _items[item_id]["enabled"] = not _items[item_id]["enabled"]
    return {"toggled": item_id, "enabled": _items[item_id]["enabled"]}


@router.delete("/{item_id}/delete")
def delete_item(item_id: str):
    """Item löschen."""
    if item_id not in _items:
        raise HTTPException(status_code=404, detail=f"Item '{item_id}' nicht gefunden")
    del _items[item_id]
    return {"deleted": item_id}
