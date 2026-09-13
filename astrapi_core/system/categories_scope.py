# astrapi_core/system/categories_scope.py
"""Scope-Modus fuer die Kategorien-Verwaltung (app.yaml: categories.scope).

Anders als current_user (ContextVar, pro Request) hier ein simples
Modul-Global -- ein Prozess bedient immer genau eine App, der Modus steht
beim Start fest (ui/app.py::create() liest ihn einmal aus app.yaml) und
aendert sich danach nicht mehr.

'owner' (Default): jeder Nutzer hat eigene, private Kategorien (max. 16) --
echte Mandantentrennung, urspruenglich fuer astrapi-sync gebaut.
'shared': eine gemeinsame Liste (max. 16) fuer alle Nutzer -- fuer Apps mit
geteilten Daten (mehrere Personen verwalten dieselben Hosts/Jobs/Repos),
wo pro-Nutzer-Kategorien sonst dazu fuehren wuerden, dass ein
Akzentstreifen/Filter nur fuer die Person sichtbar ist, die ihn gesetzt
hat."""

from __future__ import annotations

_mode = "owner"


def set_categories_scope_mode(mode: str) -> None:
    global _mode
    _mode = mode if mode in ("owner", "shared") else "owner"


def categories_scope_id() -> object:
    """Scope-Wert fuer OwnerScopedStore(modules/categories) -- None bei
    scope='shared' (kein Filter, siehe scoped_store.py), sonst der
    eingeloggte Nutzer wie ueberall sonst."""
    if _mode == "shared":
        return None
    from astrapi_core.system.current_user import current_user_id

    return current_user_id()
