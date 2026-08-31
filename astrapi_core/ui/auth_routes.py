"""core/ui/auth_routes.py – Login/Registrierung für Passkeys + Passwort-Fallback.

Nur eingebunden, wenn eine App `app.yaml: auth.enabled: true` setzt (siehe
ui/app.py::create()). Registrierung ist nur erreichbar, solange noch keine
Anmeldemethode eingerichtet ist (Bootstrap beim ersten Start) oder wenn
bereits eingeloggt (weiteres Gerät/Passwort ändern) -- Single-Owner-Modell,
keine offene Selbstregistrierung. Hintergrund: [[E-003]] in
entscheidungen.md, Passwort-Fallback siehe Docstring in system/auth.py.
"""
import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse

from astrapi_core.system import auth as authmod
from astrapi_core.ui.render import render
from astrapi_core.ui.settings_registry import get as settings_get

router = APIRouter(prefix="/auth", tags=["auth"], include_in_schema=False)


def _cookie_kw(request: Request) -> dict:
    """`secure` nur wenn die Anfrage selbst schon über HTTPS kam -- ein
    Passkey-Login setzt das ohnehin voraus (sonst gäbe es keinen sicheren
    Kontext für die WebAuthn-API), ein Passwort-Login läuft aber bewusst
    auch über reines HTTP (LAN-Deployment ohne TLS, siehe Modul-Docstring
    in system/auth.py). Ein `Secure`-Cookie würde der Browser dann nie
    zurückschicken -- sofortiger, verwirrender Logout nach dem Login."""
    return {"httponly": True, "secure": request.url.scheme == "https", "samesite": "lax"}


def _set_session_cookie(request: Request, resp: JSONResponse) -> None:
    token = authmod.create_session()
    resp.set_cookie(
        authmod.SESSION_COOKIE_NAME,
        token,
        max_age=authmod.SESSION_TTL_DAYS * 86400,
        **_cookie_kw(request),
    )


def _rp_config() -> tuple[str, str, str]:
    rp_id = settings_get("AUTH_RP_ID", "")
    rp_name = settings_get("AUTH_RP_NAME", "astrapi")
    origin = settings_get("AUTH_ORIGIN", "") or (f"https://{rp_id}" if rp_id else "")
    return rp_id, rp_name, origin


def _session_cookie(request: Request) -> str | None:
    return request.cookies.get(authmod.SESSION_COOKIE_NAME)


def _may_register(request: Request) -> bool:
    """Bootstrap (noch keine Anmeldemethode) ODER bereits eingeloggt
    (weiteres Gerät/Passwort ändern)."""
    return not authmod.is_configured() or authmod.is_logged_in(_session_cookie(request))


@router.get("/login")
def login_page(request: Request):
    if authmod.is_logged_in(_session_cookie(request)):
        return RedirectResponse("/")
    if not authmod.is_configured():
        return RedirectResponse("/auth/register")
    return render(request, "auth/login.html", {"has_passkey": authmod.has_credentials()})


@router.post("/login/options")
def login_options(request: Request):
    rp_id, _, _ = _rp_config()
    options_json, cookie_value = authmod.build_authentication_options(rp_id)
    resp = JSONResponse(json.loads(options_json))
    resp.set_cookie(authmod.CHALLENGE_COOKIE_NAME, cookie_value, max_age=300, **_cookie_kw(request))
    return resp


@router.post("/login/verify")
async def login_verify(request: Request):
    rp_id, _, origin = _rp_config()
    credential = await request.json()
    challenge_cookie = request.cookies.get(authmod.CHALLENGE_COOKIE_NAME)
    if not authmod.verify_authentication(credential, challenge_cookie, rp_id, origin):
        return JSONResponse({"ok": False}, status_code=401)

    resp = JSONResponse({"ok": True, "redirect": "/"})
    resp.delete_cookie(authmod.CHALLENGE_COOKIE_NAME)
    _set_session_cookie(request, resp)
    return resp


@router.post("/login/password")
async def login_password(request: Request):
    body = await request.json()
    password = body.get("password", "")
    if not authmod.verify_password(password):
        return JSONResponse({"ok": False}, status_code=401)

    resp = JSONResponse({"ok": True, "redirect": "/"})
    _set_session_cookie(request, resp)
    return resp


@router.get("/register")
def register_page(request: Request):
    if not _may_register(request):
        return RedirectResponse("/auth/login")
    return render(request, "auth/register.html", {})


@router.post("/register/options")
def register_options(request: Request):
    if not _may_register(request):
        return JSONResponse({"error": "nicht angemeldet"}, status_code=403)
    rp_id, rp_name, _ = _rp_config()
    options_json, cookie_value = authmod.build_registration_options(rp_id, rp_name)
    resp = JSONResponse(json.loads(options_json))
    resp.set_cookie(authmod.CHALLENGE_COOKIE_NAME, cookie_value, max_age=300, **_cookie_kw(request))
    return resp


@router.post("/register/verify")
async def register_verify(request: Request):
    if not _may_register(request):
        return JSONResponse({"ok": False}, status_code=403)
    rp_id, _, origin = _rp_config()
    body = await request.json()
    credential = body.get("credential", body)
    label = body.get("label") or "Passkey"
    challenge_cookie = request.cookies.get(authmod.CHALLENGE_COOKIE_NAME)
    ok = authmod.verify_registration(credential, challenge_cookie, rp_id, origin, label)

    resp = JSONResponse({"ok": ok})
    resp.delete_cookie(authmod.CHALLENGE_COOKIE_NAME)
    if ok and not authmod.is_logged_in(_session_cookie(request)):
        # Bootstrap (erster Passkey): direkt einloggen, kein zweiter Schritt nötig.
        _set_session_cookie(request, resp)
    return resp


@router.post("/register/password")
async def register_password(request: Request):
    if not _may_register(request):
        return JSONResponse({"ok": False}, status_code=403)
    body = await request.json()
    password = body.get("password", "")
    if len(password) < 8:
        return JSONResponse({"ok": False, "error": "Passwort zu kurz (mind. 8 Zeichen)"}, status_code=400)

    authmod.set_password(password)
    resp = JSONResponse({"ok": True})
    if not authmod.is_logged_in(_session_cookie(request)):
        # Bootstrap (erstes Passwort): direkt einloggen, kein zweiter Schritt nötig.
        _set_session_cookie(request, resp)
    return resp


@router.post("/logout")
def logout(request: Request):
    authmod.destroy_session(_session_cookie(request))
    resp = RedirectResponse("/auth/login", status_code=303)
    resp.delete_cookie(authmod.SESSION_COOKIE_NAME)
    return resp
