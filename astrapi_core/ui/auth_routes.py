"""core/ui/auth_routes.py – Login/Registrierung für Passkeys.

Nur eingebunden, wenn eine App `app.yaml: auth.enabled: true` setzt (siehe
ui/app.py::create()). Registrierung ist nur erreichbar, solange noch kein
Passkey existiert (Bootstrap beim ersten Start) oder wenn bereits
eingeloggt (weiteres Gerät hinzufügen) -- Single-Owner-Modell, keine offene
Selbstregistrierung. Hintergrund: [[E-003]] in entscheidungen.md.
"""
import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse

from astrapi_core.system import auth as authmod
from astrapi_core.ui.render import render
from astrapi_core.ui.settings_registry import get as settings_get

router = APIRouter(prefix="/auth", tags=["auth"], include_in_schema=False)

_COOKIE_KW = {"httponly": True, "secure": True, "samesite": "lax"}


def _rp_config() -> tuple[str, str, str]:
    rp_id = settings_get("AUTH_RP_ID", "")
    rp_name = settings_get("AUTH_RP_NAME", "astrapi")
    origin = settings_get("AUTH_ORIGIN", "") or (f"https://{rp_id}" if rp_id else "")
    return rp_id, rp_name, origin


def _session_cookie(request: Request) -> str | None:
    return request.cookies.get(authmod.SESSION_COOKIE_NAME)


def _may_register(request: Request) -> bool:
    """Bootstrap (noch kein Passkey) ODER bereits eingeloggt (weiteres Gerät)."""
    return not authmod.has_credentials() or authmod.is_logged_in(_session_cookie(request))


@router.get("/login")
def login_page(request: Request):
    if authmod.is_logged_in(_session_cookie(request)):
        return RedirectResponse("/")
    if not authmod.has_credentials():
        return RedirectResponse("/auth/register")
    return render(request, "auth/login.html", {})


@router.post("/login/options")
def login_options():
    rp_id, _, _ = _rp_config()
    options_json, cookie_value = authmod.build_authentication_options(rp_id)
    resp = JSONResponse(json.loads(options_json))
    resp.set_cookie(authmod.CHALLENGE_COOKIE_NAME, cookie_value, max_age=300, **_COOKIE_KW)
    return resp


@router.post("/login/verify")
async def login_verify(request: Request):
    rp_id, _, origin = _rp_config()
    credential = await request.json()
    challenge_cookie = request.cookies.get(authmod.CHALLENGE_COOKIE_NAME)
    if not authmod.verify_authentication(credential, challenge_cookie, rp_id, origin):
        return JSONResponse({"ok": False}, status_code=401)

    token = authmod.create_session()
    resp = JSONResponse({"ok": True, "redirect": "/"})
    resp.delete_cookie(authmod.CHALLENGE_COOKIE_NAME)
    resp.set_cookie(
        authmod.SESSION_COOKIE_NAME, token, max_age=authmod.SESSION_TTL_DAYS * 86400, **_COOKIE_KW
    )
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
    resp.set_cookie(authmod.CHALLENGE_COOKIE_NAME, cookie_value, max_age=300, **_COOKIE_KW)
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
        token = authmod.create_session()
        resp.set_cookie(
            authmod.SESSION_COOKIE_NAME, token, max_age=authmod.SESSION_TTL_DAYS * 86400, **_COOKIE_KW
        )
    return resp


@router.post("/logout")
def logout(request: Request):
    authmod.destroy_session(_session_cookie(request))
    resp = RedirectResponse("/auth/login", status_code=303)
    resp.delete_cookie(authmod.SESSION_COOKIE_NAME)
    return resp
