"""
app/routes/modals.py  –  UI-Modal-Routen (HTMX-Ziele)

Diese Datei implementiert die Standard-CRUD-Modals nach dem backupctl-Muster.
Aktivieren in routes/__init__.py:
  from .modals import bp as modals_bp
  app.register_blueprint(modals_bp)

Passe die Routen und Templates an dein Datenmodell an.
"""

from flask import Blueprint, render_template, request

bp = Blueprint("modals", __name__)


# ── Erstellen-Modal ───────────────────────────────────────────────────────────
@bp.route("/ui/<module>/create")
def ui_create(module: str):
    container_id = request.args.get("container_id")
    loading_id   = request.args.get("loading_id")
    # Schema für das Formular laden (projektspezifisch anpassen):
    # from app.ui.schema_loader import load_schema
    # schema = load_schema(module)
    return render_template(
        "partials/create_edit/create_edit_modal.html",
        schema=None, values=None, item=None,
        module=module,
        submit_url=f"/api/{module}/create?container_id={container_id}&loading_id={loading_id}",
        container_id=container_id,
        loading_id=loading_id,
    )


# ── Bearbeiten-Modal ──────────────────────────────────────────────────────────
@bp.route("/ui/<module>/<item>/edit")
def ui_edit(module: str, item: str):
    container_id = request.args.get("container_id")
    loading_id   = request.args.get("loading_id")
    # Daten laden (projektspezifisch anpassen):
    # values = get_item(module, item) or {}
    values = {}
    return render_template(
        "partials/create_edit/create_edit_modal.html",
        schema=None, values=values, item=item,
        module=module,
        submit_url=f"/api/{module}/{item}/edit?container_id={container_id}&loading_id={loading_id}",
        container_id=container_id,
        loading_id=loading_id,
    )


# ── Toggle-Modal ──────────────────────────────────────────────────────────────
@bp.route("/ui/<module>/<item>/toggle")
def ui_toggle(module: str, item: str):
    container_id = request.args.get("container_id")
    loading_id   = request.args.get("loading_id")
    enabled      = request.args.get("enabled")
    description  = request.args.get("description", item)
    verb         = "deaktivieren" if enabled == "True" else "aktivieren"
    return render_template(
        "partials/confirm_modal.html",
        description=description, verb=verb,
        confirm_url=f"/api/{module}/{item}/toggle",
        method="post",
        container_id=container_id,
        loading_id=loading_id,
    )


# ── Löschen-Modal ─────────────────────────────────────────────────────────────
@bp.route("/ui/<module>/<item>/delete")
def ui_delete(module: str, item: str):
    container_id = request.args.get("container_id")
    loading_id   = request.args.get("loading_id")
    description  = request.args.get("description", item)
    return render_template(
        "partials/confirm_modal.html",
        description=description, verb="löschen",
        confirm_url=f"/api/{module}/{item}/delete",
        method="delete",
        container_id=container_id,
        loading_id=loading_id,
    )
