# astrapi_core/system/current_user.py
"""Aktueller Web-Nutzer als ContextVar, request-weit abrufbar (T-325-CORE).

Promotion des bisher rein astrapi-sync-eigenen Musters
(astrapi_sync/api/user_context.py + dortige Middleware, aus T-312-SYNC)
nach core, damit auch generische Core-Module (z.B. modules/categories)
den eingeloggten Nutzer kennen koennen, ohne dass jede Multi-User-App
das selbst nachbauen muss. astrapi_sync/api/user_context.py bleibt
bewusst unveraendert bestehen (kein Umbau des gerade erst released
T-312-SYNC-Stands als Teil dieses Tickets).

contextvars.ContextVar statt threading.local(): Starlette kopiert den
Kontext korrekt in den Worker-Thread, der einen Request behandelt --
threading.local() wuerde bei Thread-Pool-Wiederverwendung zwischen
Requests leaken (ein Thread koennte den User eines VORHERIGEN Requests
sehen)."""

from __future__ import annotations

import contextvars

_current_user: contextvars.ContextVar["dict | None"] = contextvars.ContextVar(
    "current_user", default=None
)


def set_current_user(user: "dict | None") -> None:
    _current_user.set(user)


def get_current_user() -> "dict | None":
    return _current_user.get()


def current_user_id() -> int:
    """Eingeloggter Nutzer, sonst der implizite Default-User (Single-Owner-
    Apps, Alt-Daten, auth.enabled=false). Dieselbe Semantik fuer Multi-User-
    UND Single-Owner-Apps -- bei Single-Owner liefert _default_user_id()
    immer denselben Wert, ein Scoping-Filter darauf wird dadurch faktisch
    zu 'alle Zeilen', ganz ohne eigenen Sonderfall im aufrufenden Code."""
    user = _current_user.get()
    if user is not None:
        return user["id"]
    from astrapi_core.system.auth import _default_user_id

    return _default_user_id()


class CurrentUserMiddleware:
    """Setzt den eingeloggten Web-Nutzer (aus der Session-Cookie) pro Request
    in diesem Modul, analog zu astrapi_sync's _SetCurrentUserMiddleware."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        from starlette.requests import Request

        from astrapi_core.system import auth as authmod

        request = Request(scope, receive=receive)
        token = request.cookies.get(authmod.SESSION_COOKIE_NAME)
        set_current_user(authmod.get_current_user(token))
        await self.app(scope, receive, send)
