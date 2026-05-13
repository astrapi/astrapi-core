"""
core/ui/crud_blueprint.py – Generischer HTMX-CRUD-Router (FastAPI)

Erzeugt einen APIRouter mit Standard-CRUD-Endpunkten:
  GET  /ui/<key>/content              → content.html (generisch oder modul-spezifisch)
  GET  /ui/<key>/create               → Anlegen-Modal
  GET  /ui/<key>/<item_id>/edit       → Bearbeiten-Modal
  GET  /ui/<key>/<item_id>/delete     → Löschen-Bestätigung
  GET  /ui/<key>/<item_id>/toggle     → Toggle-Bestätigung
  POST /ui/<key>/                     → Anlegen durchführen
  POST /ui/<key>/<item_id>/update     → Bearbeiten durchführen

Verwendung:
    from astrapi_core.ui.crud_blueprint import make_crud_router
    from astrapi_core.ui.store import SqliteTableStore
    from pathlib import Path

    KEY   = "remotes"
    store = SqliteTableStore(KEY)
    _DIR  = Path(__file__).parent
    router = make_crud_router(store, KEY, schema_path=str(_DIR / "schema.yaml"))

    # Modulspezifische Extrarouten einfach hinzufügen:
    # @router.get(f"/ui/{KEY}/<item_id>/run")
    # def run_item(item_id: str, request: Request): ...
"""

from __future__ import annotations

from typing import Callable

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from astrapi_core.ui.schema_loader import load_schema

# Registry: module_key → filter-Definitionen (für run.py zugänglich)
_module_filters: dict[str, list[dict]] = {}


def resolve_filters_for_request(module: str, request: Request, items: dict) -> tuple[dict, dict]:
    """Wendet die registrierten Filter eines Moduls auf items an.

    Liest Werte aus Query-Parametern (Priorität) oder Cookies (Fallback).
    Gibt (gefilterte items, extra_ctx) zurück; extra_ctx enthält filter_defs.
    """
    import re

    filters = _module_filters.get(module, [])
    if not filters:
        return items, {}
    resolved = []
    for f in filters:
        val = request.query_params.get(f["param"], "")
        if not val:
            cookie_name = re.sub(r"[^a-zA-Z0-9]", "_", f"mf_{module}__{f['param']}")
            val = request.cookies.get(cookie_name, "")
        if val:
            items = {k: v for k, v in items.items() if str(v.get(f["param"], "")) == val}
        resolved.append(
            {
                "param": f["param"],
                "label": f["label"],
                "all_label": f.get("all_label", "Alle"),
                "active": val,
                "options": f["options_fn"](),
            }
        )
    return items, {"filter_defs": resolved}


def make_crud_router(
    store,
    key: str,
    schema_path: str,
    label: str | None = None,
    description_field: str = "description",
    has_run_buttons: bool = False,
    has_status: bool = True,
    has_toggle: bool = True,
    resolve_fields_fn: Callable[[list], list] | None = None,
    extra_page_actions_template: str | None = None,
    extra_actions_template: str | None = None,
    prefill_template: str | None = None,
    running_fn: Callable[[], dict] | None = None,
    filters: list[dict] | None = None,
    create_defaults: dict | None = None,
    extra_buttons: list[dict] | None = None,
) -> APIRouter:
    """Erstellt einen generischen CRUD-APIRouter.

    Args:
        store:             ModuleStore-Instanz des Moduls (SqliteTableStore oder
                           SqliteStorage/YamlStorage)
        key:               Ressourcenname (z.B. "hosts", "remotes")
        schema_path:       Absoluter Pfad zur schema.yaml
        label:             Anzeigename (Standard: key.capitalize())
        description_field: Feld des Items für die Modal-Beschreibung
        has_run_buttons:   Ob die Liste Run-Buttons anzeigen soll
        has_toggle:        Ob Toggle-Aktion verfügbar sein soll
        resolve_fields_fn: Optionale Funktion zum Anreichern der Schema-Felder
        extra_page_actions_template: Optionales Template für zusätzliche Page-Actions
        running_fn:        Optionale Funktion () -> dict mit laufenden Jobs

    Returns:
        FastAPI APIRouter mit allen Standard-UI-Routen
    """
    from astrapi_core.ui.render import render

    _label = label or key.capitalize()
    _c_id = f"mod-{key}"
    _l_id = f"{key}-loading"
    schema = load_schema(schema_path)
    _module_filters[key] = filters or []

    router = APIRouter()

    def _ctx(**extra):
        ctx = dict(
            cfg=store.list(),
            module=key,
            container_id=_c_id,
            loading_id=_l_id,
            content_template=f"{key}/partials/card_body.html",
            running=running_fn() if running_fn else {},
            has_run_buttons=has_run_buttons,
            has_status=has_status,
        )
        if extra_page_actions_template:
            ctx["extra_page_actions_template"] = extra_page_actions_template
        if extra_actions_template:
            ctx["extra_actions_template"] = extra_actions_template
        if extra_buttons:
            ctx["extra_buttons"] = extra_buttons
        ctx.update(extra)
        return ctx

    def _resolved_fields() -> list:
        fields = schema["fields"]
        if resolve_fields_fn is not None:
            return resolve_fields_fn(fields)
        return fields

    def _form_data(form) -> dict:
        data = {}
        for field in schema["fields"]:
            if field.get("type") in ("section", "info") or not field.get("name"):
                continue
            name = field["name"]
            if field.get("type") == "boolean":
                data[name] = name in form
            elif field.get("type") in ("multiselect", "list"):
                data[name] = list(form.getlist(name))
            elif field.get("type") == "password":
                val = form.get(name, "")
                if val:
                    data[name] = val
                # Leer → nicht überschreiben, vorhandener verschlüsselter Wert bleibt
            else:
                data[name] = form.get(name, "")
        return data

    def _paginate(request: Request, items: dict) -> tuple[dict, dict]:
        from astrapi_core.ui.settings_registry import get_page_size

        page_size = get_page_size()
        total = len(items)
        try:
            page = max(1, int(request.query_params.get("page", 1)))
        except ValueError:
            page = 1
        total_pages = max(1, (total + page_size - 1) // page_size)
        page = min(page, total_pages)

        items_list = list(items.items())
        paged = dict(items_list[(page - 1) * page_size : page * page_size])

        def _url(p: int) -> str:
            params = {k: v for k, v in request.query_params.items() if k != "page"}
            params["page"] = str(p)
            qs = "&".join(f"{k}={v}" for k, v in params.items())
            return f"/ui/{key}/content?{qs}"

        def _page_range(cur: int, tot: int) -> list:
            if tot <= 7:
                return list(range(1, tot + 1))
            pages: list = [1]
            if cur > 3:
                pages.append("…")
            for p in range(max(2, cur - 1), min(tot, cur + 2)):
                pages.append(p)
            if cur < tot - 2:
                pages.append("…")
            if tot > 1:
                pages.append(tot)
            return pages

        pagination = {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
            "has_prev": page > 1,
            "has_next": page < total_pages,
            "prev_url": _url(page - 1),
            "next_url": _url(page + 1),
            "pages": [
                {"num": p, "url": _url(p) if p != "…" else "#", "active": p == page}
                for p in _page_range(page, total_pages)
            ],
            "start": (page - 1) * page_size + 1,
            "end": min(page * page_size, total),
        }
        return paged, pagination

    def _content_ctx(request: Request) -> dict:
        items, extra = resolve_filters_for_request(key, request, store.list())
        paged_items, pagination = _paginate(request, items)
        return _ctx(cfg=paged_items, pagination=pagination, **extra)

    @router.get(f"/ui/{key}/content", response_class=HTMLResponse)
    def content(request: Request):
        return render(request, "content.html", _content_ctx(request))

    # Shell-Handler kann Content serverseitig rendern (kein zweiter HTTP-Request)
    def _content_string(request: Request) -> str:
        from astrapi_core.ui.render import render_string

        return render_string(request, "content.html", _content_ctx(request))

    from astrapi_core.ui.page_factory import register_content_renderer

    register_content_renderer(key, _content_string)

    @router.get(f"/ui/{key}/create", response_class=HTMLResponse)
    def create_modal(request: Request):
        return render(
            request,
            "partials/create_edit/create_edit_modal.html",
            dict(
                schema=_resolved_fields(),
                id_field=schema["id_field"],
                modal_width=schema["modal_width"],
                item=None,
                item_id=None,
                submit_url=f"/ui/{key}/",
                method="post",
                title=f"Neuer {_label}",
                reload_url=f"/ui/{key}/content",
                container_id=request.query_params.get("container_id", _c_id),
                loading_id=request.query_params.get("loading_id", _l_id),
                prefill_template=prefill_template,
            ),
        )

    @router.get(f"/ui/{key}/{{item_id}}/edit", response_class=HTMLResponse)
    def edit_modal(item_id: str, request: Request):
        item = store.get(item_id)
        if item is None:
            return HTMLResponse(f"{_label} nicht gefunden", status_code=404)
        return render(
            request,
            "partials/create_edit/create_edit_modal.html",
            dict(
                schema=_resolved_fields(),
                id_field=schema["id_field"],
                modal_width=schema["modal_width"],
                item=item,
                item_id=item_id,
                submit_url=f"/ui/{key}/{item_id}/update",
                method="post",
                title=f"{_label} bearbeiten",
                reload_url=f"/ui/{key}/content",
                container_id=request.query_params.get("container_id", _c_id),
                loading_id=request.query_params.get("loading_id", _l_id),
            ),
        )

    @router.get(f"/ui/{key}/{{item_id}}/delete", response_class=HTMLResponse)
    def delete_modal(item_id: str, request: Request):
        item = store.get(item_id) or {}
        return render(
            request,
            "partials/confirm_modal.html",
            dict(
                description=item.get(description_field, item_id),
                verb="löschen",
                confirm_url=f"/api/{key}/{item_id}",
                method="delete",
                reload_url=f"/ui/{key}/content",
                container_id=request.query_params.get("container_id", _c_id),
                loading_id=request.query_params.get("loading_id", _l_id),
            ),
        )

    if has_toggle:

        @router.get(f"/ui/{key}/{{item_id}}/toggle", response_class=HTMLResponse)
        def toggle_modal(item_id: str, request: Request):
            item = store.get(item_id) or {}
            enabled = request.query_params.get("enabled", "True")
            verb = "deaktivieren" if enabled == "True" else "aktivieren"
            return render(
                request,
                "partials/confirm_modal.html",
                dict(
                    description=item.get(description_field, item_id),
                    verb=verb,
                    confirm_url=f"/api/{key}/{item_id}/toggle",
                    method="patch",
                    reload_url=f"/ui/{key}/content",
                    container_id=request.query_params.get("container_id", _c_id),
                    loading_id=request.query_params.get("loading_id", _l_id),
                ),
            )

    @router.post(f"/ui/{key}/", response_class=HTMLResponse)
    async def create_apply(request: Request):
        id_field = schema["id_field"]
        form = await request.form()
        if id_field is not None:
            item_id = form.get(id_field["name"], "").strip()
            if not item_id:
                return HTMLResponse("ID fehlt", status_code=400)
        else:
            item_id = None
        data = _form_data(form)
        if create_defaults:
            for k, v in create_defaults.items():
                if k not in data:
                    data[k] = v
        try:
            store.create(item_id, data)
        except KeyError:
            return HTMLResponse("Bereits vorhanden", status_code=409)
        return render(request, "content.html", _ctx())

    @router.post(f"/ui/{key}/{{item_id}}/update", response_class=HTMLResponse)
    async def edit_apply(item_id: str, request: Request):
        form = await request.form()
        try:
            store.update(item_id, _form_data(form))
        except KeyError:
            return HTMLResponse("Nicht gefunden", status_code=404)
        return render(request, "content.html", _ctx())

    return router


# Rückwärtskompatibilität: alter Name zeigt auf neuen
make_crud_blueprint = make_crud_router
