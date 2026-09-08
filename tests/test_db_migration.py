"""system/db.py: Kleinstfix für T-308-CORE -- fehlende Spalten (DDL wurde
im Code erweitert, eine bereits existierende SQLite-Datei kennt die neue
Spalte noch nicht) werden per ALTER TABLE automatisch ergänzt statt mit
sqlite3.OperationalError zu scheitern."""
import sqlite3

import pytest

from astrapi_core.system import db


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path):
    db._db_path = tmp_path / "test.db"
    db._local.conn = None
    db._TABLE_CONFIG = {}
    yield


def _register_old_schema():
    """Simuliert eine Tabelle, die vor Hinzufügen der Spalte "extra" angelegt wurde."""
    db.register_table(
        "widgets",
        "CREATE TABLE IF NOT EXISTS widgets ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT)",
    )
    db._ensure_table("widgets")


def _columns(table: str) -> set:
    con = db._conn()
    return {row[1] for row in con.execute(f'PRAGMA table_info("{table}")').fetchall()}


def test_create_item_ergaenzt_fehlende_spalte():
    _register_old_schema()
    item_id = db.create_item("widgets", {"name": "foo", "extra": "bar"})
    assert "extra" in _columns("widgets")
    assert db.get_item("widgets", item_id)["extra"] == "bar"


def test_save_item_update_ergaenzt_fehlende_spalte():
    _register_old_schema()
    item_id = db.create_item("widgets", {"name": "foo"})
    db.save_item("widgets", item_id, {"name": "foo", "extra": "bar"})
    assert "extra" in _columns("widgets")
    assert db.get_item("widgets", item_id)["extra"] == "bar"


def test_patch_item_ergaenzt_fehlende_spalte():
    _register_old_schema()
    item_id = db.create_item("widgets", {"name": "foo"})
    db.patch_item("widgets", item_id, extra="bar")
    assert "extra" in _columns("widgets")
    assert db.get_item("widgets", item_id)["extra"] == "bar"


def test_anderer_operational_error_wird_durchgereicht():
    _register_old_schema()
    with pytest.raises(sqlite3.OperationalError):
        db.create_item("nie_registrierte_tabelle", {"name": "foo"})
