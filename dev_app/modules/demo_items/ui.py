"""dev_app/modules/demo_items/ui.py – Flask-Blueprint"""

from pathlib import Path

from astrapi.core.ui.crud_blueprint import make_crud_blueprint
from .storage import store, KEY

_DIR = Path(__file__).parent
bp = make_crud_blueprint(
    store, KEY,
    schema_path=str(_DIR / "schema.yaml"),
    label="Demo Item",
    description_field="description",
)
