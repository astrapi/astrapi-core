# core/ui/multi_user_routes.py – Nutzerverwaltung/Einladung für echte
# Mehrbenutzer-Apps.
"""Nur eingebunden, wenn eine App `app.yaml: auth.multi_user: true` setzt
(siehe ui/app.py::create()) -- astrapi-admin (Single-Owner) bindet das
nicht ein, bleibt unberührt.

Einladung folgt demselben Muster wie das Geräte-Pairing in astrapi-sync
(astrapi_sync/modules/devices/pairing_store.py): eingeloggter Nutzer
erzeugt einen kurzlebigen Token/Link, die eingeladene Person registriert
darüber ihre EIGENE Passkey unter einer NEUEN, unabhängigen Nutzeridentität
-- kein Passwort-Fallback für eingeladene Personen (nur der ursprüngliche
Bootstrap-/Default-User behält den Passwort-Notweg, siehe system/auth.py-
Docstring "Übergangslösung bis HTTPS steht").

`/auth` liegt komplett in `RequireLoginMiddleware`s Ausnahmeliste (siehe
auth_middleware.py) -- Routen hier, die einen Login voraussetzen
(`/auth/users`, `/auth/users/invite`), prüfen das deshalb selbst.
"""
import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse

from astrapi_core.system import auth as authmod
from astrapi_core.system import auth_invites
from astrapi_core.ui.auth_routes import _cookie_kw, _rp_config, _session_cookie
from astrapi_core.ui.render import render

router = APIRouter(prefix="/auth", tags=["auth"], include_in_schema=False)


@router.get("/users")
def users_page(request: Request):
    current = authmod.get_current_user(_session_cookie(request))
    if current is None:
        return RedirectResponse("/auth/login?next=/auth/users")
    if not current.get("is_admin"):
        return RedirectResponse("/")
    return render(request, "auth/users.html", {"users": authmod.list_users(), "current_user": current})


@router.post("/users/invite")
def create_invite(request: Request):
    current = authmod.get_current_user(_session_cookie(request))
    if current is None:
        return JSONResponse({"error": "nicht angemeldet"}, status_code=403)
    if not current.get("is_admin"):
        return JSONResponse({"error": "nur der Admin darf Nutzer einladen"}, status_code=403)
    token = auth_invites.create_invite_token(current["id"])
    return JSONResponse({"url": f"/auth/invite/{token}", "ttl_seconds": auth_invites.ttl_seconds()})


@router.get("/invite/{token}")
def invite_page(token: str, request: Request):
    info = auth_invites.peek_invite_token(token)
    if info is None:
        return render(request, "auth/invite.html", {"invalid": True}, status_code=410)
    inviter = authmod.get_user(info["invited_by_user_id"])
    # "user_id" schon im Token vorhanden = Passkey-Reset für einen
    # bestehenden Nutzer (astrapi_core/modules/users), kein neuer Nutzer --
    # der Name steht schon fest, die Seite fragt ihn nicht erneut ab.
    known_user = authmod.get_user(info["user_id"]) if "user_id" in info else None
    return render(
        request,
        "auth/invite.html",
        {"invalid": False, "inviter": inviter, "token": token, "known_user": known_user},
    )


@router.post("/invite/{token}/options")
async def invite_options(token: str, request: Request):
    info = auth_invites.peek_invite_token(token)
    if info is None:
        return JSONResponse({"error": "Einladung abgelaufen oder ungültig"}, status_code=410)

    if "user_id" in info:
        # Passkey-Reset (astrapi_core/modules/users): kein neuer Nutzer,
        # die Zeile existiert schon -- nur eine neue Passkey-Zeremonie.
        user = authmod.get_user(info["user_id"])
        if user is None:
            return JSONResponse({"error": "Nutzer wurde inzwischen gelöscht"}, status_code=410)
        user_id, username, display_name = user["id"], user["username"], user["display_name"]
    else:
        body = await request.json()
        username = (body.get("username") or "").strip()
        if not username:
            return JSONResponse({"error": "Name fehlt"}, status_code=400)
        display_name = (body.get("display_name") or username).strip()

        # Wird HIER schon angelegt (nicht erst bei /verify) -- der Token
        # selbst trägt keinen Platz für eigene Metadaten über die WebAuthn-
        # Challenge hinaus, attach_user() verknuepft die neue User-Zeile mit
        # dem Token, damit /verify weiss, wen sie gerade fertig
        # registriert. Bricht die eigentliche Passkey-Zeremonie danach ab,
        # bleibt eine leere, credential-lose User-Zeile zurück -- lässt
        # sich über astrapi_core/modules/users (Löschen oder Passkey
        # zurücksetzen) reparieren.
        user_id = authmod.create_user(username, display_name)
        auth_invites.attach_user(token, user_id)

    rp_id, rp_name, _ = _rp_config()
    options_json, cookie_value = authmod.build_registration_options(
        rp_id, rp_name, user_id, username, display_name
    )
    resp = JSONResponse(json.loads(options_json))
    resp.set_cookie(authmod.CHALLENGE_COOKIE_NAME, cookie_value, max_age=300, **_cookie_kw(request))
    return resp


@router.post("/invite/{token}/password")
async def invite_password(token: str, request: Request):
    """Alternative zu /invite/{token}/options+/verify (Passkey) -- die
    eingeladene Person setzt statt einer Passkey ein eigenes Passwort.
    Gleiche Token-Semantik wie invite_options()/invite_verify(): neuer
    Nutzer (kein user_id im Token) wird hier per username angelegt,
    bestehender Nutzer (Passkey-Reset aus astrapi_core/modules/users)
    bekommt einfach ein Passwort gesetzt. Token wird erst bei Erfolg
    eingelöst (redeem_invite_token), analog zum Passkey-Zweig."""
    info = auth_invites.peek_invite_token(token)
    if info is None:
        return JSONResponse({"error": "Einladung abgelaufen oder ungültig"}, status_code=410)

    body = await request.json()
    password = body.get("password", "")
    if len(password) < 8:
        return JSONResponse({"ok": False, "error": "Passwort zu kurz (mind. 8 Zeichen)"}, status_code=400)

    if "user_id" in info:
        user_id = info["user_id"]
        if authmod.get_user(user_id) is None:
            return JSONResponse({"error": "Nutzer wurde inzwischen gelöscht"}, status_code=410)
    else:
        username = (body.get("username") or "").strip()
        if not username:
            return JSONResponse({"error": "Name fehlt"}, status_code=400)
        display_name = (body.get("display_name") or username).strip()
        user_id = authmod.create_user(username, display_name)
        auth_invites.attach_user(token, user_id)

    redeemed = auth_invites.redeem_invite_token(token)
    if redeemed is None:
        return JSONResponse({"ok": False, "error": "Einladung abgelaufen oder ungültig"}, status_code=410)

    authmod.set_user_password(user_id, password)
    resp = JSONResponse({"ok": True, "redirect": "/"})
    session_token = authmod.create_session(user_id)
    resp.set_cookie(
        authmod.SESSION_COOKIE_NAME,
        session_token,
        max_age=authmod.SESSION_TTL_DAYS * 86400,
        **_cookie_kw(request),
    )
    return resp


@router.post("/invite/{token}/verify")
async def invite_verify(token: str, request: Request):
    info = auth_invites.redeem_invite_token(token)
    if info is None or "user_id" not in info:
        return JSONResponse({"ok": False, "error": "Einladung abgelaufen oder ungültig"}, status_code=410)
    user_id = info["user_id"]

    rp_id, _, origin = _rp_config()
    body = await request.json()
    credential = body.get("credential", body)
    label = body.get("label") or "Passkey"
    challenge_cookie = request.cookies.get(authmod.CHALLENGE_COOKIE_NAME)
    ok = authmod.verify_registration(credential, challenge_cookie, rp_id, origin, label, user_id)

    resp = JSONResponse({"ok": ok, "redirect": "/"})
    resp.delete_cookie(authmod.CHALLENGE_COOKIE_NAME)
    if ok:
        session_token = authmod.create_session(user_id)
        resp.set_cookie(
            authmod.SESSION_COOKIE_NAME,
            session_token,
            max_age=authmod.SESSION_TTL_DAYS * 86400,
            **_cookie_kw(request),
        )
    return resp
