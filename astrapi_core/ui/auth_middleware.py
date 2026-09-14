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
_ALWAYS_EXEMPT = (
    "/auth", "/static", "/health", "/api/docs", "/api/redoc", "/api/openapi.json",
    "/manifest.json",
)


class RequireLoginMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        exempt_prefixes: "list[str] | None" = None,
        exempt_get_paths: "list[str] | None" = None,
    ):
        super().__init__(app)
        self._exempt = tuple(_ALWAYS_EXEMPT) + tuple(exempt_prefixes or [])
        # exempt_get_paths: exakter Pfad, NUR fuer GET -- anders als
        # exempt_prefixes (Praefix, jede Methode) fuer Faelle, wo unter
        # demselben Pfad auch schreibende Routen haengen (z.B. die
        # generische JSON-CRUD-API: GET /api/debian listet nur, POST
        # /api/debian legt ein neues Repo an). Ein Praefix-Exempt dafuer
        # wuerde versehentlich auch das schreibende POST/PUT/DELETE ohne
        # Login freigeben -- siehe [[T-332-MIRROR]] (astrapi-admin konnte
        # nach Aktivierung von auth.enabled keine Mirror-Repos mehr lesen,
        # /api/debian war schlicht nirgends exemptiert).
        # rstrip("/") bei der Ablage UND beim Vergleich (unten): FastAPI haengt
        # an eine mit "/" endende Routendefinition (z.B. crud_router.py's
        # @router.get("/") fuer /api/debian) einen automatischen 301 auf die
        # Trailing-Slash-Variante, BEVOR unsere Route ueberhaupt laeuft --
        # ohne Normalisierung waere ".../api/debian" exemptiert, die
        # tatsaechlich aufgerufene ".../api/debian/" (nach dem Redirect) aber
        # nicht mehr, und der zweite Request liefe doch wieder gegen das
        # Login-Gate.
        self._exempt_get = frozenset(p.rstrip("/") for p in (exempt_get_paths or []))

    async def dispatch(self, request, call_next):
        path = request.url.path
        if any(path == p or path.startswith(p.rstrip("/") + "/") for p in self._exempt):
            return await call_next(request)
        if request.method == "GET" and path.rstrip("/") in self._exempt_get:
            return await call_next(request)

        if not authmod.is_configured():
            return RedirectResponse("/auth/register")

        token = request.cookies.get(authmod.SESSION_COOKIE_NAME)
        if not authmod.is_logged_in(token):
            return RedirectResponse(f"/auth/login?next={path}")

        return await call_next(request)
