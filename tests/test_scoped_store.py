"""ui/scoped_store.py::OwnerScopedStore + system/current_user.py (T-325-CORE) --
generalisierte Fassung von astrapi_sync/modules/_owner_store.py::OwnerScopedStore
(T-312-SYNC), parametrisiert statt sync-fest verdrahtet."""
import pytest

from astrapi_core.system import current_user, db
from astrapi_core.ui.scoped_store import OwnerScopedStore


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path):
    db._db_path = tmp_path / "test.db"
    db._local.conn = None
    yield


class _FakeInner:
    """Minimaler ModuleStore-Ersatz -- kein echtes SQLite noetig, um die
    Scoping-/Limit-Logik von OwnerScopedStore isoliert zu testen."""

    def __init__(self):
        self._rows: dict[str, dict] = {}
        self._next_id = 1

    def list(self) -> dict[str, dict]:
        return dict(self._rows)

    def get(self, item_id: str) -> dict | None:
        return self._rows.get(item_id)

    def create(self, item_id, data: dict) -> str:
        item_id = item_id or str(self._next_id)
        self._next_id += 1
        self._rows[item_id] = dict(data)
        return item_id

    def update(self, item_id: str, data: dict) -> None:
        self._rows[item_id].update(data)

    def delete(self, item_id: str) -> bool:
        return self._rows.pop(item_id, None) is not None


@pytest.fixture()
def inner():
    return _FakeInner()


def test_list_nur_eigener_scope(inner):
    store = OwnerScopedStore(inner, scope_fn=lambda: 1)
    inner.create(None, {"name": "a", "owner_user_id": 1})
    inner.create(None, {"name": "b", "owner_user_id": 2})
    assert [v["name"] for v in store.list().values()] == ["a"]


def test_create_stempelt_scope(inner):
    store = OwnerScopedStore(inner, scope_fn=lambda: 7)
    item_id = store.create(None, {"name": "x"})
    assert inner.get(item_id)["owner_user_id"] == 7


def test_get_fremder_scope_none(inner):
    store_a = OwnerScopedStore(inner, scope_fn=lambda: 1)
    store_b = OwnerScopedStore(inner, scope_fn=lambda: 2)
    item_id = store_a.create(None, {"name": "a"})
    assert store_b.get(item_id) is None
    assert store_a.get(item_id) is not None


def test_update_delete_fremder_scope_verweigert(inner):
    store_a = OwnerScopedStore(inner, scope_fn=lambda: 1)
    store_b = OwnerScopedStore(inner, scope_fn=lambda: 2)
    item_id = store_a.create(None, {"name": "a"})
    with pytest.raises(KeyError):
        store_b.update(item_id, {"name": "hacked"})
    assert store_b.delete(item_id) is False
    assert inner.get(item_id)["name"] == "a"


def test_max_items_limit(inner):
    store = OwnerScopedStore(inner, scope_fn=lambda: 1, max_items=2)
    store.create(None, {"name": "a"})
    store.create(None, {"name": "b"})
    with pytest.raises(ValueError):
        store.create(None, {"name": "c"})
    assert len(store.list()) == 2


def test_max_items_zaehlt_nur_eigenen_scope(inner):
    """Das Limit ist pro Scope, nicht global -- ein anderer Nutzer/eine
    andere Single-Owner-App-Instanz darf trotzdem bis zum eigenen Limit."""
    store_a = OwnerScopedStore(inner, scope_fn=lambda: 1, max_items=1)
    store_b = OwnerScopedStore(inner, scope_fn=lambda: 2, max_items=1)
    store_a.create(None, {"name": "a"})
    store_b.create(None, {"name": "b"})  # darf trotzdem, eigener Scope noch leer
    with pytest.raises(ValueError):
        store_a.create(None, {"name": "a2"})


def test_current_user_id_fallback_ohne_middleware():
    """Ohne aktive CurrentUserMiddleware (z.B. auth.enabled=false) liefert
    current_user_id() den impliziten Default-User -- dieselbe Semantik wie
    astrapi_sync/api/user_context.py::current_user_id()."""
    from astrapi_core.system.auth import _default_user_id

    current_user.set_current_user(None)
    assert current_user.current_user_id() == _default_user_id()


def test_current_user_id_mit_gesetztem_nutzer():
    current_user.set_current_user({"id": 42})
    try:
        assert current_user.current_user_id() == 42
    finally:
        current_user.set_current_user(None)
