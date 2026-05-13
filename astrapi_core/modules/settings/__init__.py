"""core/modules/settings/__init__.py – Framework-Einstellungen Modul."""

from pathlib import Path

from astrapi_core.ui.controls import ContentCustom
from astrapi_core.ui.module_loader import load_modul

_KEY = Path(__file__).parent.name

from .ui import router as ui_router

module = load_modul(
    Path(__file__).parent,
    _KEY,
    None,
    ui_router,
    ui_content=ContentCustom(template="partials/lists/settings.html"),
)
