# astrapi_core/modules/categories/ui/crud.py
"""Kein make_htmx_crud_router() hier (anders als z.B. host_groups) -- das
spricht direkt gegen astrapi_core.system.db und wuerde den OwnerScopedStore
darunter komplett umgehen (jeder eingeloggte Nutzer koennte ueber die rohe
JSON-API fremde Kategorien lesen/aendern/loeschen). api_router bleibt
deshalb bewusst auf die eine, bereits scope-gefilterte /for-select-Route
beschraenkt -- Kategorien werden ausschliesslich ueber die generische,
store-gebundene Web-UI (make_crud_router) verwaltet."""

from pathlib import Path

from fastapi import APIRouter

from astrapi_core.system.categories_scope import categories_scope_id
from astrapi_core.ui.crud_blueprint import make_crud_router
from astrapi_core.ui.scoped_store import OwnerScopedStore
from astrapi_core.ui.store import SqliteTableStore

KEY = "categories"
_DIR = Path(__file__).parent.parent
# scope_fn=categories_scope_id statt des OwnerScopedStore-Defaults
# (current_user_id direkt) -- liefert bei app.yaml: categories.scope=shared
# None zurueck, wodurch der Store ungefiltert alle Zeilen zeigt (siehe
# scoped_store.py) statt jedem Nutzer nur seine eigenen Kategorien.
store = OwnerScopedStore(SqliteTableStore(KEY), scope_fn=categories_scope_id, max_items=16)


def categories_for_select() -> list[dict]:
    return [{"value": cid, "label": c.get("name") or cid} for cid, c in store.list().items()]


def _resolve_labels(item_id: str, item: dict) -> dict:
    """list_wrapper_inner.html rendert die NAME-Spalte immer fest aus
    item_data.description (oder .job/.host/item_name), nie aus einem
    modul-eigenen Feld -- categories hat aber ein eigenes 'name'-Feld,
    kein 'description' (gleiche Fehlerklasse wie host_groups/policies,
    siehe [[T-285-ADMIN]]/[[T-288-ADMIN]])."""
    return {**item, "description": item.get("name") or item_id}


api_router = APIRouter()


@api_router.get("/for-select")
def for_select():
    return {"options": categories_for_select()}


router = make_crud_router(
    store,
    KEY,
    schema_path=str(_DIR / "config" / "schema.yaml"),
    label="Kategorie",
    description_field="name",
    has_run_buttons=False,
    has_status=False,
    has_toggle=False,
    list_item_transform=_resolve_labels,
)
