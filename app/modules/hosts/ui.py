"""app/modules/hosts/ui.py – Flask-Blueprint für Hosts UI-Routen."""

from pathlib import Path

from core.ui.crud_blueprint import make_crud_blueprint
from .storage import store, KEY

_DIR = Path(__file__).parent
bp = make_crud_blueprint(store, KEY, schema_path=str(_DIR / "schema.yaml"))

# Modulspezifische Extrarouten hier ergänzen:
# @bp.route(f"/ui/{KEY}/<item_id>/ping")
# def ping_host(item_id: str): ...
