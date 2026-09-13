"""modules/categories (T-325-CORE) -- generischer Kategorien-Baustein.

Prueft die echte Modul-Verdrahtung (DDL/register_table, OwnerScopedStore
mit max_items=16, categories_for_select()) direkt am Store, nicht über
die volle HTTP-Route -- create_apply() im Erfolgsfall braucht eine
konfigurierte Jinja2Templates-Instanz (astrapi_core.ui.app.create()),
die hier den Rahmen sprengen würde. Der reine Scoping-/Limit-Mechanismus
selbst ist bereits generisch in test_scoped_store.py abgedeckt; hier
geht es nur darum, dass modules/categories ihn auch tatsächlich richtig
verdrahtet (richtiges Feld, richtiges Limit, richtige Tabelle)."""
import pytest

from astrapi_core.system import current_user, db


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path):
    db._db_path = tmp_path / "test.db"
    db._local.conn = None
    yield


@pytest.fixture()
def store():
    # Import erst NACH der DB-Isolierung oben -- register_table() in
    # modules/categories/__init__.py laeuft beim ersten Import, die
    # eigentliche CREATE TABLE braucht aber schon die isolierte DB.
    import astrapi_core.modules.categories.ui.crud as crud
    from astrapi_core.system.db import create_all_registered_tables

    create_all_registered_tables()
    yield crud.store
    current_user.set_current_user(None)


def test_16_kategorien_gehen_durch_17_nicht(store):
    current_user.set_current_user({"id": 1})
    for i in range(16):
        store.create(None, {"name": f"Kat {i}"})
    with pytest.raises(ValueError):
        store.create(None, {"name": "Kat 17"})
    assert len(store.list()) == 16


def test_limit_ist_pro_nutzer_nicht_global(store):
    current_user.set_current_user({"id": 1})
    for i in range(16):
        store.create(None, {"name": f"A{i}"})
    current_user.set_current_user({"id": 2})
    # Nutzer 2 hat noch ein leeres Kontingent, unabhaengig von Nutzer 1
    store.create(None, {"name": "B1"})
    assert len(store.list()) == 1


def test_kategorien_sind_scoped(store):
    from astrapi_core.modules.categories.ui.crud import categories_for_select

    current_user.set_current_user({"id": 1})
    store.create(None, {"name": "Nur für Nutzer 1"})
    current_user.set_current_user({"id": 2})
    assert categories_for_select() == []
    current_user.set_current_user({"id": 1})
    assert [c["label"] for c in categories_for_select()] == ["Nur für Nutzer 1"]
