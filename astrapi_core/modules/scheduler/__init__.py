"""core/modules/scheduler – Cron-Scheduler-Modul für AstrapiFlaskUi.

Projekte konfigurieren den Scheduler vor dem App-Start:

    from astrapi_core.modules.scheduler.engine import configure, init

    configure(job_fn=my_job, get_setting=..., set_setting=..., job_name="Sync")
    init()
"""

from pathlib import Path

from astrapi_core.ui.controls import ContentTable, Header
from astrapi_core.ui.module_loader import load_modul

_KEY = Path(__file__).parent.name

from .ui import _scheduler_table
from .ui import router as ui_router

module = load_modul(
    Path(__file__).parent,
    _KEY,
    None,
    ui_router,
    ui_header=Header(
        [
            Header.action_button(
                "Neuer Job",
                hx_get=f"/ui/{_KEY}/job/new",
                hx_target="body",
                style="primary",
            ),
        ]
    ),
    ui_content=_scheduler_table,
)
