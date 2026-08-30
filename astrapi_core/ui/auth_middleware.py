"""core/ui/auth_middleware.py – Login-Gate für die UI.

Nur eingebunden, wenn eine App `app.yaml: auth.enabled: true` setzt (siehe
ui/app.py::create()). Blockiert **alles außer** einer expliziten
Ausnahmeliste (Allowlist umgekehrt: Denylist-Default) -- ein neu
hinzugefügtes Modul/eine neue Route ist damit automatisch geschützt, ohne
dass jemand aktiv daran denken muss. Hintergrund: [[E-003]].
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import RedirectResponse

from astrapi_core.system import auth as authmod

# Immer ausgenommen, unabhängig von der App: die Login/Registrierungs-
# Ceremonie selbst (sonst kein Weg zum Einloggen), statische Assets (die
# Login-Seite muss ihr CSS/JS laden können), Health-Check (Watchdog/Monitoring
# dürfen nicht am Login scheitern), API-Doku (bereits heute ohne Auth in der
# ganzen Familie).
_ALWAYS_EXEMPT = ("/auth", "/static", "/health", "/api/docs", "/api/redoc", "/api/openapi.json")


class RequireLoginMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, exempt_prefixes: "list[str] | None" = None):
        super().__init__(app)
        self._exempt = tuple(_ALWAYS_EXEMPT) + tuple(exempt_prefixes or [])

    async def dispatch(self, request, call_next):
        path = request.url.path
        if any(path == p or path.startswith(p.rstrip("/") + "/") for p in self._exempt):
            return await call_next(request)

        if not authmod.has_credentials():
            return RedirectResponse("/auth/register")

        token = request.cookies.get(authmod.SESSION_COOKIE_NAME)
        if not authmod.is_logged_in(token):
            return RedirectResponse(f"/auth/login?next={path}")

        return await call_next(request)
