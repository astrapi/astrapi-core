"""
core/ui/storage.py  –  SQLite-backed Key-Value Store für alle Module.

Daten werden in der zentralen SQLite-Datenbank in der Tabelle `kvstore`
gespeichert (Werte als JSON).

Verwendung in einem Modul:
    from astrapi_core.ui.storage import SqliteStorage
    store = SqliteStorage("hosts")

    store.list()                          # dict aller Einträge
    store.get("web-01")                   # einzelner Eintrag oder None
    store.create("web-01", {...})         # neu anlegen
    store.update("web-01", {...})         # vorhandenen Eintrag aktualisieren
    store.delete("web-01")               # löschen
    store.toggle("web-01")               # enabled-Flag umschalten
"""

from __future__ import annotations

import json
import threading
from typing import Callable


class StorageNotInitialized(RuntimeError):
    pass


class SqliteStorage:
    """SQLite-backed Storage für eine Collection.

    Args:
        collection: Name der Collection
        seed_data:  Optionale Startdaten wenn die Collection leer ist
    """

    def __init__(self, collection: str, seed_data: dict | None = None):
        self.collection = collection
        self._seed = seed_data or {}
        self._lock = threading.Lock()

    # ── Lesen ─────────────────────────────────────────────────────

    def _load_all(self) -> dict:
        """Gibt alle Einträge der Collection als dict zurück."""
        from astrapi_core.system.db import kv_list

        raw = kv_list(self.collection)
        return {k: json.loads(v) for k, v in raw.items()}

    def list(
        self,
        filter_fn: "Callable[[str, dict], bool] | None" = None,
        offset: int = 0,
        limit: int | None = None,
    ) -> dict:
        with self._lock:
            data = self._load_all()
            if not data and self._seed:
                from astrapi_core.system.db import kv_set_many

                kv_set_many(self.collection, {k: json.dumps(v) for k, v in self._seed.items()})
                data = dict(self._seed)

        if filter_fn is not None:
            data = {k: v for k, v in data.items() if filter_fn(k, v)}
        if offset:
            data = dict(list(data.items())[offset:])
        if limit is not None:
            data = dict(list(data.items())[:limit])
        return data

    def get(self, key: str) -> dict | None:
        from astrapi_core.system.db import kv_get

        raw = kv_get(self.collection, key)
        return json.loads(raw) if raw is not None else None

    def exists(self, key: str) -> bool:
        from astrapi_core.system.db import kv_get

        return kv_get(self.collection, key) is not None

    # ── Schreiben ─────────────────────────────────────────────────

    def create(self, key: str | None, values: dict) -> str:
        """Legt einen neuen Eintrag an. key=None wird nicht unterstützt (kein auto-increment).
        Gibt den verwendeten Schlüssel zurück.
        """
        if key is None:
            raise ValueError(
                f"SqliteStorage '{self.collection}' unterstützt kein auto-increment "
                "(item_id=None). Bitte einen expliziten Schlüssel übergeben."
            )
        with self._lock:
            from astrapi_core.system.db import kv_get, kv_set

            if kv_get(self.collection, key) is not None:
                raise KeyError(f"'{key}' existiert bereits in '{self.collection}'")
            kv_set(self.collection, key, json.dumps(values))
        return key

    def update(self, key: str, values: dict) -> None:
        with self._lock:
            from astrapi_core.system.db import kv_get, kv_set

            raw = kv_get(self.collection, key)
            if raw is None:
                raise KeyError(f"'{key}' nicht gefunden in '{self.collection}'")
            existing = json.loads(raw)
            existing.update(values)
            kv_set(self.collection, key, json.dumps(existing))

    def upsert(self, key: str, values: dict) -> dict:
        with self._lock:
            from astrapi_core.system.db import kv_get, kv_set

            raw = kv_get(self.collection, key)
            if raw is not None:
                existing = json.loads(raw)
                existing.update(values)
            else:
                existing = values
            kv_set(self.collection, key, json.dumps(existing))
        return existing

    def delete(self, key: str) -> bool:
        with self._lock:
            from astrapi_core.system.db import kv_delete, kv_get

            if kv_get(self.collection, key) is None:
                raise KeyError(f"'{key}' nicht gefunden in '{self.collection}'")
            kv_delete(self.collection, key)
        return True

    def toggle(self, key: str, field: str = "enabled", default: bool = True) -> bool:
        with self._lock:
            from astrapi_core.system.db import kv_get, kv_set

            raw = kv_get(self.collection, key)
            if raw is None:
                raise KeyError(f"'{key}' nicht gefunden in '{self.collection}'")
            data = json.loads(raw)
            current = bool(data.get(field, default))
            data[field] = not current
            kv_set(self.collection, key, json.dumps(data))
        return data[field]

    def __repr__(self) -> str:
        return f"SqliteStorage(collection={self.collection!r})"
