# astrapi_core/ui/scoped_store.py
"""Generischer, scope-filternder Store-Wrapper (T-325-CORE).

Generalisierte Fassung von astrapi_sync/modules/_owner_store.py::
OwnerScopedStore (aus T-312-SYNC) -- gleiche Methoden, gleiches Prinzip
(list()/get() filtern auf einen Scope-Wert, create() stempelt ihn,
update()/delete()/toggle() pruefen den Scope VOR der eigentlichen
Operation, nicht nur die Anzeige), aber mit austauschbarer Scope-Quelle
statt hart auf astrapi_sync's current_user_id() verdrahtet -- damit auch
Single-Owner-Apps (wo current_user_id() immer denselben impliziten
Nutzer liefert) denselben Code-Pfad nutzen koennen, ganz ohne
NULL-Sonderfall.

astrapi_sync/modules/_owner_store.py bleibt bewusst bestehen (kein
Umbau des gerade erst released T-312-SYNC-Stands als Teil dieses
Tickets) -- eine spaetere Vereinheitlichung ist optionale Aufraeumarbeit."""

from __future__ import annotations

from typing import Callable

from astrapi_core.system.current_user import current_user_id


class OwnerScopedStore:
    """Args:
    inner:       zu umhuellender Store (z.B. SqliteTableStore)
    scope_field: Feldname, unter dem der Scope-Wert im Item liegt
    scope_fn:    () -> aktueller Scope-Wert (Default: current_user_id())
    max_items:   optionales Limit -- create() wirft ValueError, sobald
                 list() (bereits scope-gefiltert) dieses Limit erreicht
                 hat, statt den inneren Store aufzurufen.
    """

    def __init__(
        self,
        inner,
        scope_field: str = "owner_user_id",
        scope_fn: Callable[[], object] = current_user_id,
        max_items: int | None = None,
    ) -> None:
        self._inner = inner
        self._scope_field = scope_field
        self._scope_fn = scope_fn
        self._max_items = max_items

    def list(self) -> dict[str, dict]:
        scope = self._scope_fn()
        return {
            k: v for k, v in self._inner.list().items() if v.get(self._scope_field) == scope
        }

    def get(self, item_id: str) -> dict | None:
        item = self._inner.get(item_id)
        if item is None or item.get(self._scope_field) != self._scope_fn():
            return None
        return item

    def create(self, item_id: str | None, data: dict) -> str:
        if self._max_items is not None and len(self.list()) >= self._max_items:
            raise ValueError(f"Maximal {self._max_items} Einträge erreicht")
        return self._inner.create(item_id, {**data, self._scope_field: self._scope_fn()})

    def update(self, item_id: str, data: dict) -> None:
        if self.get(item_id) is None:
            raise KeyError(item_id)
        self._inner.update(item_id, data)

    def delete(self, item_id: str) -> bool:
        if self.get(item_id) is None:
            return False
        return self._inner.delete(item_id)

    def toggle(self, item_id: str, field: str = "enabled", default: bool = True) -> bool:
        if self.get(item_id) is None:
            raise KeyError(item_id)
        return self._inner.toggle(item_id, field=field, default=default)
