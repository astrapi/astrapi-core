"""app/modules/tasks/ui.py – Flask-Blueprint für Tasks UI-Routen."""

from pathlib import Path
from flask import Blueprint, render_template, request
from core.ui.schema_loader import load_schema
from .storage import store, KEY

_DIR   = Path(__file__).parent
SCHEMA = load_schema(str(_DIR / "schema.yaml"))

_C_ID  = f"tab-{KEY}"
_L_ID  = f"{KEY}-loading"
_LABEL = KEY.capitalize()

bp = Blueprint(f"{KEY}_ui", __name__)


def _ctx(**extra):
    return dict(
        key=KEY,
        label=_LABEL,
        items=store.list(),
        container_id=_C_ID,
        loading_id=_L_ID,
        **extra,
    )


@bp.route(f"/ui/{KEY}/content")
def content():
    return render_template(f"{KEY}/partials/list.html", **_ctx())


@bp.route(f"/ui/{KEY}/create")
def create_modal():
    return render_template(
        "partials/create_edit/create_edit_modal.html",
        schema=SCHEMA["fields"],
        id_field=SCHEMA["id_field"],
        item=None,
        item_id=None,
        submit_url=f"/api/{KEY}/",
        method="post",
        title=f"Neuer {_LABEL}",
        container_id=request.args.get("container_id", _C_ID),
        loading_id=request.args.get("loading_id", _L_ID),
    )


@bp.route(f"/ui/{KEY}/<item_id>/edit")
def edit_modal(item_id: str):
    item = store.get(item_id)
    if item is None:
        return f"{_LABEL} nicht gefunden", 404
    return render_template(
        "partials/create_edit/create_edit_modal.html",
        schema=SCHEMA["fields"],
        id_field=SCHEMA["id_field"],
        item=item,
        item_id=item_id,
        submit_url=f"/api/{KEY}/{item_id}",
        method="put",
        title=f"{_LABEL} bearbeiten – {item_id}",
        container_id=request.args.get("container_id", _C_ID),
        loading_id=request.args.get("loading_id", _L_ID),
    )


@bp.route(f"/ui/{KEY}/<item_id>/delete")
def delete_modal(item_id: str):
    item = store.get(item_id) or {}
    return render_template(
        "partials/confirm_modal.html",
        description=item.get("description", item_id),
        verb="löschen",
        confirm_url=f"/api/{KEY}/{item_id}",
        method="delete",
        container_id=request.args.get("container_id", _C_ID),
        loading_id=request.args.get("loading_id", _L_ID),
    )


@bp.route(f"/ui/{KEY}/<item_id>/toggle")
def toggle_modal(item_id: str):
    item    = store.get(item_id) or {}
    enabled = request.args.get("enabled", "True")
    verb    = "deaktivieren" if enabled == "True" else "aktivieren"
    return render_template(
        "partials/confirm_modal.html",
        description=item.get("description", item_id),
        verb=verb,
        confirm_url=f"/api/{KEY}/{item_id}/toggle",
        method="patch",
        container_id=request.args.get("container_id", _C_ID),
        loading_id=request.args.get("loading_id", _L_ID),
    )
