"""core/modules/system/__init__.py – System-Informationen + Updater."""

from pathlib import Path

from astrapi_core.ui.controls import ContentCustom, Header
from astrapi_core.ui.module_loader import load_modul

_KEY = Path(__file__).parent.name

from .ui import router as ui_router

module = load_modul(
    Path(__file__).parent,
    _KEY,
    None,
    ui_router,
    ui_header=Header(
        [
            Header.action_button(
                "Aktualisieren",
                hx_get=f"/ui/{_KEY}/metrics",
                hx_target="#system-metrics",
                hx_swap="outerHTML",
                style="ghost",
            )
        ]
    ),
    ui_content=ContentCustom(template="system/partials/content.html"),
)
