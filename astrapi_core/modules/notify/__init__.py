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
                "Neuer Kanal",
                hx_get=f"/ui/{_KEY}/backend-select",
                hx_target="body",
                style="primary",
            ),
            Header.action_button(
                "Neuer Job",
                hx_get=f"/ui/{_KEY}/jobs/create",
                hx_target="body",
                style="primary",
            ),
        ]
    ),
    ui_content=ContentCustom(template="notify/partials/content.html"),
)
