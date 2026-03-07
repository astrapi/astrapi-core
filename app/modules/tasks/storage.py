"""app/modules/tasks/storage.py – Storage-Instanz für das Tasks-Modul."""
from pathlib import Path
from core.ui.storage import YamlStorage

KEY   = Path(__file__).parent.name   # → "tasks"
store = YamlStorage(KEY)
