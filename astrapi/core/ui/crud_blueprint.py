"""
core/ui/crud_blueprint.py – Generischer HTMX-CRUD-Router (FastAPI)

Erzeugt einen APIRouter mit Standard-CRUD-Endpunkten:
  GET  /ui/<key>/content              → Listenpartial (list_wrapper.html)
  GET  /ui/<key>/create               → Anlegen-Modal
  GET  /ui/<key>/<item_id>/edit       → Bearbeiten-Modal
  GET  /ui/<key>/<item_id>/delete     → Löschen-Bestätigung
  GET  /ui/<key>/<item_id>/toggle     → Toggle-Bestätigung
  POST /ui/<key>/                     → Anlegen durchführen
  POST /ui/<key>/<item_id>/update     → Bearbeiten durchführen

Verwendung:
    from astrapi.core.ui.crud_blueprint import make_crud_router
    from astrapi.core.ui.store import SqliteTableStore
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

from astrapi.core.ui.schema_loader import load_schema


def make_crud_router(
    store,
    key: str,
    schema_path: str,
    label: str | None = None,
    description_field: str = "description",
    has_run_buttons: bool = False,
    has_toggle: bool = True,
    resolve_fields_fn: Callable[[list], list] | None = None,
    extra_page_actions_template: str | None = None,
    prefill_template: str | None = None,
    running_fn: Callable[[], dict] | None = None,
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
    from astrapi.core.ui.render import render

    _label  = label or key.capitalize()
    _c_id   = f"tab-{key}"
    _l_id   = f"{key}-loading"
    schema  = load_schema(schema_path)

    router = APIRouter()

    def _ctx(**extra):
        ctx = dict(
            cfg=store.list(),
            module=key,
            container_id=_c_id,
            loading_id=_l_id,
            content_template=f"{key}/partials/list.html",
            running=running_fn() if running_fn else {},
            has_run_buttons=has_run_buttons,
        )
        if extra_page_actions_template:
            ctx["extra_page_actions_template"] = extra_page_actions_template
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
            else:
                data[name] = form.get(name, "")
        return data

    @router.get(f"/ui/{key}/content", response_class=HTMLResponse)
    def content(request: Request):
        return render(request, "partials/list_wrapper.html", _ctx())

    @router.get(f"/ui/{key}/create", response_class=HTMLResponse)
    def create_modal(request: Request):
        return render(request, "partials/create_edit/create_edit_modal.html", dict(
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
        ))

    @router.get(f"/ui/{key}/{{item_id}}/edit", response_class=HTMLResponse)
    def edit_modal(item_id: str, request: Request):
        item = store.get(item_id)
        if item is None:
            return HTMLResponse(f"{_label} nicht gefunden", status_code=404)
        return render(request, "partials/create_edit/create_edit_modal.html", dict(
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
        ))

    @router.get(f"/ui/{key}/{{item_id}}/delete", response_class=HTMLResponse)
    def delete_modal(item_id: str, request: Request):
        item = store.get(item_id) or {}
        return render(request, "partials/confirm_modal.html", dict(
            description=item.get(description_field, item_id),
            verb="löschen",
            confirm_url=f"/api/{key}/{item_id}/delete",
            method="delete",
            reload_url=f"/ui/{key}/content",
            container_id=request.query_params.get("container_id", _c_id),
            loading_id=request.query_params.get("loading_id", _l_id),
        ))

    if has_toggle:
        @router.get(f"/ui/{key}/{{item_id}}/toggle", response_class=HTMLResponse)
        def toggle_modal(item_id: str, request: Request):
            item    = store.get(item_id) or {}
            enabled = request.query_params.get("enabled", "True")
            verb    = "deaktivieren" if enabled == "True" else "aktivieren"
            return render(request, "partials/confirm_modal.html", dict(
                description=item.get(description_field, item_id),
                verb=verb,
                confirm_url=f"/api/{key}/{item_id}/toggle",
                method="patch",
                reload_url=f"/ui/{key}/content",
                container_id=request.query_params.get("container_id", _c_id),
                loading_id=request.query_params.get("loading_id", _l_id),
            ))

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
        try:
            store.create(item_id, _form_data(form))
        except KeyError:
            return HTMLResponse("Bereits vorhanden", status_code=409)
        return render(request, "partials/list_wrapper.html", _ctx())

    @router.post(f"/ui/{key}/{{item_id}}/update", response_class=HTMLResponse)
    async def edit_apply(item_id: str, request: Request):
        form = await request.form()
        try:
            store.update(item_id, _form_data(form))
        except KeyError:
            return HTMLResponse("Nicht gefunden", status_code=404)
        return render(request, "partials/list_wrapper.html", _ctx())

    return router


# Rückwärtskompatibilität: alter Name zeigt auf neuen
make_crud_blueprint = make_crud_router
