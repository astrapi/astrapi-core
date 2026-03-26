"""dev_app/modules/demo_log/ui.py – Read-only Beispiel-Log-Liste"""

from flask import Blueprint, render_template

KEY = "demo_log"
bp  = Blueprint(f"{KEY}_ui", __name__)

_ENTRIES = [
    {"ts": "2026-03-26 10:00:00", "level": "INFO",  "message": "Dienst gestartet"},
    {"ts": "2026-03-26 10:01:15", "level": "INFO",  "message": "Konfiguration geladen (3 Einträge)"},
    {"ts": "2026-03-26 10:05:42", "level": "WARN",  "message": "Verbindung zu Host-02 verzögert"},
    {"ts": "2026-03-26 10:08:01", "level": "ERROR", "message": "Timeout beim Abruf von Host-03"},
    {"ts": "2026-03-26 10:08:45", "level": "INFO",  "message": "Wiederverbindung zu Host-03 erfolgreich"},
    {"ts": "2026-03-26 10:15:00", "level": "INFO",  "message": "Geplanter Job abgeschlossen"},
]


@bp.route(f"/ui/{KEY}/content")
def content():
    return render_template(f"{KEY}/partials/list.html", entries=_ENTRIES)
