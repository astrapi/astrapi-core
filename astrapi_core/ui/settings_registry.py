"""
core/ui/settings_registry.py  –  Einstellungs-Registry (SQLite-backed)

Alle Einstellungen werden in der zentralen SQLite-Datenbank gespeichert
(kvstore-Tabelle, collection="_settings", Werte als JSON).
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

_COLLECTION = "_settings"


class SettingsRegistry:
    """Kapselt den gesamten Zustand der Einstellungs-Registry.

    Alle öffentlichen Methoden sind thread-safe.
    Die Klasse kann mit reset() in den Ausgangszustand zurückversetzt werden
    (nützlich für Test-Isolation).
    """

    def __init__(self):
        self._data_dir: Path | None = None
        self._lock = threading.Lock()

    def reset(self) -> None:
        with self._lock:
            self._data_dir = None

    def init(self, app_root: Path) -> None:
        self._data_dir = app_root / "data"
        self._data_dir.mkdir(exist_ok=True)

    # ── Interne Helfer ─────────────────────────────────────────────

    def _load(self) -> dict:
        try:
            from astrapi_core.system.db import kv_list

            return {k: json.loads(v) for k, v in kv_list(_COLLECTION).items()}
        except Exception:
            return {}

    def _save_one(self, key: str, value: Any) -> None:
        try:
            from astrapi_core.system.db import kv_set

            kv_set(_COLLECTION, key, json.dumps(value))
        except Exception:
            pass

    def _save_many(self, items: dict) -> None:
        try:
            from astrapi_core.system.db import kv_set_many

            kv_set_many(_COLLECTION, {k: json.dumps(v) for k, v in items.items()})
        except Exception:
            pass

    def _delete_one(self, key: str) -> None:
        try:
            from astrapi_core.system.db import kv_delete

            kv_delete(_COLLECTION, key)
        except Exception:
            pass

    # ── Öffentliche API ────────────────────────────────────────────

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            data = self._load()
            return data.get(key, default)

    def get_module(self, module_key: str, key: str, default: Any = None) -> Any:
        return self.get(f"module.{module_key}.{key}", default)

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._save_one(key, value)

    def set_module(self, module_key: str, key: str, value: Any) -> None:
        self.set(f"module.{module_key}.{key}", value)

    def set_many(self, values: dict) -> None:
        with self._lock:
            self._save_many(values)

    def all_settings(self) -> dict:
        with self._lock:
            return self._load()

    def seed_defaults(
        self,
        global_defaults: dict,
        modules: list,
        failed_module_keys: "set[str] | None" = None,
    ) -> None:
        """Füllt fehlende Werte mit Defaults auf und bereinigt verwaiste Modul-Keys.

        failed_module_keys: Modulnamen die beim Laden fehlgeschlagen sind.
            Ihre Settings-Keys werden NICHT als verwaist behandelt, damit ein
            temporärer Ladefehler keine gespeicherten Einstellungen löscht.
        """
        protected = failed_module_keys or set()
        with self._lock:
            current = self._load()
            to_add: dict = {}

            for k, v in global_defaults.items():
                if k not in current:
                    to_add[k] = v

            for mod in modules:
                for k, v in mod.settings_defaults.items():
                    full_key = f"module.{mod.key}.{k}"
                    if full_key not in current:
                        to_add[full_key] = v

            if to_add:
                self._save_many(to_add)
                current.update(to_add)

            # Verwaiste Modul-Keys entfernen – fehlgeschlagene Module ausnehmen
            known = {mod.key for mod in modules}
            orphaned = [
                k
                for k in current
                if k.startswith("module.")
                and k.split(".")[1] not in known
                and k.split(".")[1] not in protected
            ]
            for k in orphaned:
                self._delete_one(k)


# Modul-level Singleton
_registry = SettingsRegistry()


def __getattr__(name: str):
    return getattr(_registry, name)


def get_page_size() -> int:
    """Gibt die konfigurierte Pagination-Seitengröße zurück (Default: 15)."""
    try:
        return int(_registry.get("PAGINATION_PAGE_SIZE", 15))
    except (TypeError, ValueError):
        return 15


def get_activity_log_retention_days() -> int:
    """Gibt die konfigurierte Aufbewahrungsdauer des Activity-Logs in Tagen zurück
    (Default: 90, 0 = deaktiviert / unbegrenzt)."""
    try:
        return int(_registry.get("ACTIVITY_LOG_RETENTION_DAYS", 90))
    except (TypeError, ValueError):
        return 90
