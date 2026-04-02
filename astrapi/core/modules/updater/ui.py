# core/modules/updater/ui.py
from flask import Blueprint, render_template
from . import engine

KEY = "updater"
bp  = Blueprint(f"{KEY}_ui", __name__)


def _ctx() -> dict:
    status = engine.get_status()
    return {
        "packages":     status["packages"] or engine.get_packages_with_versions(),
        "status":       status["status"],
        "last_checked": status["last_checked"],
        "output":       status["output"],
        "error":        status["error"],
        "log_id":       status["log_id"],
    }


@bp.route(f"/ui/{KEY}/content")
def updater_content():
    return render_template(f"{KEY}/partials/tab.html", **_ctx())


@bp.route(f"/ui/{KEY}/panel")
def updater_panel():
    """Nur das Update-Panel – wird per HTMX-Polling aktualisiert."""
    return render_template(f"{KEY}/partials/panel.html", **_ctx())


@bp.route(f"/ui/{KEY}/check", methods=["POST"])
def updater_check():
    """Führt den Versionscheck synchron durch und rendert das aktualisierte Panel."""
    engine.check_updates()
    return render_template(f"{KEY}/partials/panel.html", **_ctx())


@bp.route(f"/ui/{KEY}/update", methods=["POST"])
def updater_update():
    """Startet das Update (async) und gibt das Panel mit Polling zurück."""
    engine.run_update()
    return render_template(f"{KEY}/partials/panel.html", **_ctx())
