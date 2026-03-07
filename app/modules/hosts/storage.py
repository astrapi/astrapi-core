"""app/modules/hosts/storage.py – Storage-Instanz für das Hosts-Modul."""
from pathlib import Path
from core.ui.storage import YamlStorage

KEY   = Path(__file__).parent.name   # → "hosts"
store = YamlStorage(KEY)
