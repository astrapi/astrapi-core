from pathlib import Path

from astrapi_core.system.db import register_table
from astrapi_core.ui.module_loader import load_modul

_KEY = Path(__file__).parent.name

_DDL = """
    CREATE TABLE IF NOT EXISTS categories (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        name          TEXT    NOT NULL DEFAULT '',
        color         TEXT    NOT NULL DEFAULT '',
        owner_user_id INTEGER NOT NULL DEFAULT 0
    )"""

register_table(_KEY, _DDL)

from astrapi_core.modules.categories.ui.crud import api_router as router  # noqa: E402
from astrapi_core.modules.categories.ui.crud import categories_for_select  # noqa: E402
from astrapi_core.modules.categories.ui.crud import router as ui_router  # noqa: E402
from astrapi_core.ui.controls import Col, ContentTable, Header  # noqa: E402
from astrapi_core.ui.field_resolver import register_options_fetcher as _reg  # noqa: E402


def _categories_options_fetcher(endpoint: str) -> list:
    return categories_for_select()


# T-325-CORE: fuer eine kuenftige category_id-Zuweisung an eigene Items
# (T-324-SYNC/T-326-ADMIN/...), analog zur bestehenden host_groups/folders-
# for-select-Registrierung.
_reg("/api/categories/for-select", _categories_options_fetcher)

module = load_modul(
    Path(__file__).parent,
    _KEY,
    router,
    ui_router,
    ui_header=Header(
        [
            Header.action_button(
                "Neu", hx_get=f"/ui/{_KEY}/create", hx_target="body", style="primary", icon="plus"
            ),
        ]
    ),
    ui_content=ContentTable(
        has_run_buttons=False,
        has_status=False,
        has_toggle=False,
        columns=[
            Col.color("color", "Farbe"),
        ],
    ),
)
