from pathlib import Path

from astrapi_core.ui.controls import Col, ContentTable, Header
from astrapi_core.ui.module_loader import load_modul

_KEY = Path(__file__).parent.name

from .engine import registered_modules
from .ui import router as ui_router

module = load_modul(
    Path(__file__).parent,
    _KEY,
    None,
    ui_router,
    ui_header=Header(
        [
            Header.filter_select(
                "log_type",
                [
                    {"value": "job", "label": "Jobs"},
                    {"value": "scheduler", "label": "Scheduler"},
                    {"value": "error", "label": "Errors"},
                    {"value": "warning", "label": "Warnings"},
                    {"value": "system", "label": "System"},
                ],
                all_label="Alle Typen",
            ),
            Header.filter_select(
                "module",
                options_fn=lambda: [
                    {"value": m, "label": m.replace("_", " ").title()} for m in registered_modules()
                ],
                all_label="Alle Module",
            ),
            Header.filter_select(
                "status",
                [
                    {"value": "ok", "label": "OK"},
                    {"value": "error", "label": "Fehler"},
                    {"value": "warning", "label": "Warnung"},
                    {"value": "running", "label": "Läuft"},
                    {"value": "skipped", "label": "Übersprungen"},
                ],
                all_label="Alle Status",
            ),
            Header.filter_select(
                "date_range",
                [
                    {"value": "24h", "label": "Letzte 24h"},
                    {"value": "7d", "label": "7 Tage"},
                    {"value": "30d", "label": "30 Tage", "default": True},
                    {"value": "", "label": "Alle"},
                ],
                all_label=None,
            ),
            Header.action_button(
                "Log leeren",
                hx_get="/ui/activity_log/clear-confirm",
                hx_target="body",
                style="danger",
            ),
        ]
    ),
    ui_content=ContentTable(
        has_create=False,
        has_run_buttons=False,
        has_status=False,
        has_edit=False,
        has_delete=False,
        has_toggle=False,
        columns=[
            Col.text("created_at", "Zeitpunkt"),
            Col.badge_enum(
                "log_type",
                "Typ",
                {
                    "job": {"label": "job", "cls": "badge-grey"},
                    "scheduler": {"label": "sched", "cls": "badge-grey"},
                    "error": {"label": "err", "cls": "badge-status-err"},
                    "warning": {"label": "warn", "cls": "badge-status-warn"},
                    "system": {"label": "sys", "cls": "badge-grey"},
                },
            ),
            Col.mono("module", "Modul"),
            Col.text("item_label", "Job"),
            Col.status("status", "Status"),
            Col.mono("duration_fmt", "Dauer"),
        ],
    ),
)
