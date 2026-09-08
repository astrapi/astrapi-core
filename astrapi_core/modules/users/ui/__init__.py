"""core/modules/users/ui/__init__.py – Routen der Nutzerverwaltung."""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from astrapi_core.system import auth as authmod
from astrapi_core.system import auth_invites
from astrapi_core.ui.auth_routes import _session_cookie
from astrapi_core.ui.render import render

KEY = "users"
router = APIRouter()


def _current_user(request: Request) -> dict:
    user = authmod.get_current_user(_session_cookie(request))
    if user is None:
        # Sollte nicht vorkommen -- RequireLoginMiddleware schützt /ui/*
        # bereits vor jedem Zugriff ohne Session. Letzte Absicherung.
        raise HTTPException(403, "nicht angemeldet")
    return user


def _ctx(request: Request) -> dict:
    current = _current_user(request)
    counts: dict[int, int] = {}
    for cred in authmod.list_credentials():
        counts[cred["user_id"]] = counts.get(cred["user_id"], 0) + 1
    users = authmod.list_users()
    for u in users:
        u["credential_count"] = counts.get(u["id"], 0)
    return {
        "module": KEY,
        "has_create": False,
        "container_id": "mod-users",
        "users": users,
        "current_user": current,
        "can_delete": len(users) > 1,
    }


@router.get(f"/ui/{KEY}/content", response_class=HTMLResponse)
def users_content(request: Request):
    return render(request, "content.html", _ctx(request))


def _content_string(request: Request) -> str:
    from astrapi_core.ui.render import render_string

    return render_string(request, "content.html", _ctx(request))


from astrapi_core.ui.page_factory import register_content_renderer  # noqa: E402

register_content_renderer(KEY, _content_string)


@router.post(f"/ui/{KEY}/invite")
def invite_new_user(request: Request):
    current = _current_user(request)
    token = auth_invites.create_invite_token(current["id"])
    return JSONResponse({"url": f"/auth/invite/{token}", "ttl_seconds": auth_invites.ttl_seconds()})


@router.post(f"/ui/{KEY}/{{user_id}}/delete", response_class=HTMLResponse)
def remove_user(user_id: int, request: Request):
    current = _current_user(request)
    if user_id == current["id"]:
        raise HTTPException(400, "Der eigene Account kann hier nicht gelöscht werden.")
    try:
        authmod.delete_user(user_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return render(request, "content.html", _ctx(request))


@router.post(f"/ui/{KEY}/{{user_id}}/reset-passkey")
def reset_passkey(user_id: int, request: Request):
    current = _current_user(request)
    if authmod.get_user(user_id) is None:
        raise HTTPException(404, "Nutzer nicht gefunden")
    authmod.reset_credentials(user_id)
    token = auth_invites.create_invite_token(current["id"], existing_user_id=user_id)
    return JSONResponse({"url": f"/auth/invite/{token}", "ttl_seconds": auth_invites.ttl_seconds()})
