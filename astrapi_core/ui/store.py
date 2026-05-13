"""
core/ui/store.py  –  ModuleStore-Protokoll + SqliteTableStore

ModuleStore ist die abstrakte Schnittstelle, über die make_crud_blueprint mit
beliebigen Storage-Backends kommuniziert.  SqliteTableStore ist die
backupctl-Implementierung, die auf core.system.db (generische CRUD-API mit
auto-increment Integer-IDs) delegiert.

Verwendung:
    from astrapi_core.ui.store import SqliteTableStore
    store = SqliteTableStore("remotes")

    store.list()                  # {str(id): item_dict}
    store.get("1")                # item_dict oder None
    store.create(None, data)      # auto-increment, gibt neue str-ID zurück
    store.update("1", data)       # aktualisiert Eintrag
    store.delete("1")             # True wenn gelöscht
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

# ── Protokoll (abstrakte Schnittstelle) ────────────────────────────────────────


@runtime_checkable
class ModuleStore(Protocol):
    """Abstrakte Schnittstelle für CRUD-Stores, die mit make_crud_blueprint
    kompatibel sind.

    list()         gibt {str(id): item_dict} zurück
    get(item_id)   gibt item_dict oder None zurück
    create(item_id, data)  legt neuen Eintrag an; item_id=None → auto-increment
                           gibt die (ggf. neu erzeugte) ID als str zurück
    update(item_id, data)  aktualisiert bestehenden Eintrag
    delete(item_id)        löscht Eintrag, gibt True zurück wenn erfolgreich
    """

    def list(self) -> dict[str, dict]: ...
    def get(self, item_id: str) -> dict | None: ...
    def create(self, item_id: str | None, data: dict) -> str: ...
    def update(self, item_id: str, data: dict) -> None: ...
    def delete(self, item_id: str) -> bool: ...


# ── SqliteTableStore – backupctl-Implementierung ───────────────────────────────


class SqliteTableStore:
    """ModuleStore-Implementierung für generische SQLite-Tabellen (backupctl).

    Delegiert an core.system.db: load_config, get_item, save_item, delete_item.
    IDs sind auto-increment Integer (SQLite ROWID), werden als str zurückgegeben.

    Args:
        key: Tabellenname (= Modul-Key, z.B. "remotes", "borg")
    """

    def __init__(self, key: str) -> None:
        self.key = key

    def list(self) -> dict[str, dict]:
        """Gibt {str(id): item_dict} zurück – identisch zu core.system.db.load_config."""
        from astrapi_core.system.db import load_config

        return load_config(self.key)

    def get(self, item_id: str) -> dict | None:
        """Gibt ein Item per ID zurück oder None."""
        from astrapi_core.system.db import get_item

        return get_item(self.key, item_id)

    def create(self, item_id: str | None, data: dict) -> str:
        """Legt einen neuen Eintrag an.

        item_id wird ignoriert – auto-increment via SQLite.
        Gibt die neue ID als str zurück.
        """
        from astrapi_core.system.db import create_item

        new_id = create_item(self.key, data)
        return str(new_id)

    def update(self, item_id: str, data: dict) -> None:
        """Aktualisiert einen bestehenden Eintrag vollständig."""
        from astrapi_core.system.db import get_item, save_item

        existing = get_item(self.key, item_id)
        if existing is None:
            raise KeyError(f"'{item_id}' nicht gefunden in '{self.key}'")
        existing.update(data)
        save_item(self.key, item_id, existing)

    def upsert(self, item_id: str, data: dict) -> dict:
        """Aktualisiert vorhandene Felder oder legt neu an wenn nicht vorhanden."""
        from astrapi_core.system.db import get_item, save_item

        existing = get_item(self.key, item_id) or {}
        existing.update(data)
        save_item(self.key, item_id, existing)
        return existing

    def exists(self, item_id: str) -> bool:
        """Gibt True zurück wenn der Eintrag existiert."""
        return self.get(item_id) is not None

    def toggle(self, item_id: str, field: str = "enabled", default: bool = True) -> bool:
        """Schaltet ein Boolean-Feld um. Gibt den neuen Wert zurück."""
        from astrapi_core.system.db import get_item, patch_item

        existing = get_item(self.key, item_id)
        if existing is None:
            raise KeyError(f"'{item_id}' nicht gefunden in '{self.key}'")
        new_val = not bool(existing.get(field, default))
        patch_item(self.key, item_id, **{field: int(new_val)})
        return new_val

    def delete(self, item_id: str) -> bool:
        """Löscht einen Eintrag. Gibt True zurück wenn erfolgreich."""
        from astrapi_core.system.db import delete_item

        return delete_item(self.key, item_id)

    def __repr__(self) -> str:
        return f"SqliteTableStore(key={self.key!r})"
