"""core/modules/users/ui/__init__.py – Routen der Nutzerverwaltung."""
import qrcode
import qrcode.image.svg
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

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


def _require_admin(request: Request) -> dict:
    """Wie _current_user(), zusätzlich mit Admin-Pflicht -- für alle
    Aktionen, die andere Nutzer verändern (einladen/löschen/Passkey
    zurücksetzen). Zusätzliche Absicherung neben dem modulweiten
    admin_only=True (config/modul.yaml): das blockt bereits jeden
    Nicht-Admin-Zugriff auf /ui/users/* mit 403 (siehe
    module_registry.py::register_ui_modules()), _require_admin() greift
    also nur noch, falls admin_only je entfernt würde."""
    user = _current_user(request)
    if not user.get("is_admin"):
        raise HTTPException(403, "nur der Admin darf Nutzer verwalten")
    return user


def _ctx(request: Request) -> dict:
    """cfg ist ein {item_id_str: item_dict}, wie list_wrapper_inner.html es
    für jedes Modul erwartet -- 'description' füllt dessen fest verdrahtete
    Name-Spalte (item_data.description or .job or .host or item_name),
    credential_display/credential_category speisen die deklarative
    Col.dot_text-Spalte aus modules/users/__init__.py."""
    current = _current_user(request)
    counts: dict[int, int] = {}
    for cred in authmod.list_credentials():
        counts[cred["user_id"]] = counts.get(cred["user_id"], 0) + 1
    users = authmod.list_users()
    cfg: dict[str, dict] = {}
    for u in users:
        cred_count = counts.get(u["id"], 0)
        name = u.get("display_name") or u["username"]
        cfg[str(u["id"])] = {
            **u,
            "description": name + (" (du)" if u["id"] == current["id"] else ""),
            "credential_display": f"{cred_count} Passkey{'' if cred_count == 1 else 's'}"
            if cred_count
            else "kein Passkey",
            "credential_category": "ok" if cred_count else "error",
            "role": "admin" if u.get("is_admin") else "user",
        }
    return {
        "module": KEY,
        "has_create": False,
        # Rendert den "Neu"-Button in den echten Seiten-Header (statt eines
        # statischen Header([...])), damit er wie bei jedem anderen Modul
        # dort sitzt -- die Datei selbst prüft current_user.is_admin, siehe
        # modules/users/__init__.py-Kommentar zu ui_header=None.
        "extra_page_actions_template": f"{KEY}/partials/header_actions.html",
        # Einladen/Passkey-Reset/Löschen -- admin-gated, siehe partials/row_actions.html.
        "extra_actions_template": f"{KEY}/partials/row_actions.html",
        "container_id": "mod-users",
        "cfg": cfg,
        "running": {},
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


@router.get(f"/ui/{KEY}/create", response_class=HTMLResponse)
def create_dialog(request: Request):
    _require_admin(request)
    return render(request, f"{KEY}/dialogs/create/modal.html", {})


@router.post(f"/ui/{KEY}", response_class=HTMLResponse)
async def create_new_user(request: Request):
    _require_admin(request)
    body = await request.json()
    username = (body.get("username") or "").strip()
    if not username:
        raise HTTPException(400, "Benutzername fehlt")
    if any(u["username"] == username for u in authmod.list_users()):
        raise HTTPException(409, "Benutzername bereits vergeben")
    display_name = (body.get("display_name") or "").strip() or username
    new_id = authmod.create_user(username, display_name)
    if body.get("is_admin"):
        authmod.set_admin(new_id, True)
    return render(request, "content.html", _ctx(request))


def _active_admin_count(exclude_id: int | None = None) -> int:
    return sum(
        1
        for u in authmod.list_users()
        if u.get("is_admin") and u.get("enabled", True) and u["id"] != exclude_id
    )


def _is_last_active_admin(user: dict) -> bool:
    """True, wenn user selbst aktiver Admin ist UND kein anderer aktiver
    Admin existiert -- weder Rolle noch Aktiviert-Status duerfen dann
    geaendert werden (sonst waere niemand mehr uebrig, der administrieren
    kann)."""
    if not (user.get("is_admin") and user.get("enabled", True)):
        return False
    return _active_admin_count(exclude_id=user["id"]) == 0


@router.get(f"/ui/{KEY}/{{user_id}}/edit", response_class=HTMLResponse)
def edit_dialog(user_id: int, request: Request):
    current = _require_admin(request)
    user = authmod.get_user(user_id)
    if user is None:
        raise HTTPException(404, "Nutzer nicht gefunden")
    return render(
        request,
        f"{KEY}/dialogs/edit/modal.html",
        {
            "user": user,
            "locked": _is_last_active_admin(user),
            "is_self": user_id == current["id"],
            "credentials": authmod.list_credentials(user_id),
        },
    )


@router.post(f"/ui/{KEY}/{{user_id}}/credentials/{{credential_id}}/delete")
def delete_credential(user_id: int, credential_id: int, request: Request):
    _require_admin(request)
    if authmod.get_user(user_id) is None:
        raise HTTPException(404, "Nutzer nicht gefunden")
    if not authmod.delete_credential(credential_id, user_id):
        raise HTTPException(404, "Passkey nicht gefunden")
    return Response(status_code=204)


@router.post(f"/ui/{KEY}/{{user_id}}/update", response_class=HTMLResponse)
async def update_user(user_id: int, request: Request):
    current = _require_admin(request)
    user = authmod.get_user(user_id)
    if user is None:
        raise HTTPException(404, "Nutzer nicht gefunden")
    body = await request.json()
    username = (body.get("username") or "").strip()
    if not username:
        raise HTTPException(400, "Benutzername fehlt")
    if username != user["username"] and any(
        u["username"] == username for u in authmod.list_users()
    ):
        raise HTTPException(409, "Benutzername bereits vergeben")
    want_admin = bool(body.get("is_admin"))
    want_enabled = bool(body.get("enabled", True))
    if user_id == current["id"] and not want_enabled:
        # Sonst deaktiviert sich die eigene Session mitten im Request --
        # render(_ctx()) am Ende braucht current_user() noch fuer die
        # Antwort, waere dann faelschlich "nicht angemeldet". Gleiche
        # Absicherung wie schon bei remove_user() (kein Selbst-Loeschen).
        raise HTTPException(400, "Der eigene Account kann hier nicht deaktiviert werden.")
    if _is_last_active_admin(user) and not (want_admin and want_enabled):
        raise HTTPException(
            409, "Es muss mindestens ein aktiver Administrator bestehen bleiben."
        )
    authmod.set_username(user_id, username)
    display_name = (body.get("display_name") or "").strip() or username
    authmod.set_display_name(user_id, display_name)
    if want_admin != bool(user.get("is_admin")):
        authmod.set_admin(user_id, want_admin)
    if want_enabled != bool(user.get("enabled", True)):
        authmod.set_enabled(user_id, want_enabled)
    return render(request, "content.html", _ctx(request))


def _invite_modal_response(request: Request, user: dict, current: dict) -> HTMLResponse:
    """Gemeinsam für "Einladen" und "Passkey zurücksetzen" -- beide enden im
    selben Ergebnis (neuer Einladungslink + QR für user), nur ob vorher
    bestehende Credentials gelöscht werden, unterscheidet sich."""
    token = auth_invites.create_invite_token(current["id"], existing_user_id=user["id"])
    server_url = str(request.base_url).rstrip("/")
    invite_url = f"{server_url}/auth/invite/{token}"
    qr_img = qrcode.make(invite_url, image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=2)
    return render(
        request,
        f"{KEY}/dialogs/invite/modal.html",
        {
            "user": user,
            "invite_url": invite_url,
            "ttl_minutes": auth_invites.ttl_seconds() // 60,
            "qr_svg": qr_img.to_string().decode("utf-8"),
        },
    )


@router.get(f"/ui/{KEY}/{{user_id}}/invite", response_class=HTMLResponse)
def invite_dialog(user_id: int, request: Request):
    """Einladungslink + QR-Code für einen bereits angelegten Nutzer --
    Gegenstück zum "Neu"-Button (der nur die Zeile anlegt, ohne Zugangsdaten).
    Gleiche Token-Semantik wie Passkey zurücksetzen (existing_user_id), setzt
    aber -- anders als das -- keine bestehenden Credentials zurück."""
    current = _require_admin(request)
    user = authmod.get_user(user_id)
    if user is None:
        raise HTTPException(404, "Nutzer nicht gefunden")
    return _invite_modal_response(request, user, current)


@router.post(f"/ui/{KEY}/{{user_id}}/delete", response_class=HTMLResponse)
def remove_user(user_id: int, request: Request):
    current = _require_admin(request)
    if user_id == current["id"]:
        raise HTTPException(400, "Der eigene Account kann hier nicht gelöscht werden.")
    try:
        authmod.delete_user(user_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return render(request, "content.html", _ctx(request))


@router.post(f"/ui/{KEY}/{{user_id}}/reset-passkey", response_class=HTMLResponse)
def reset_passkey(user_id: int, request: Request):
    current = _require_admin(request)
    user = authmod.get_user(user_id)
    if user is None:
        raise HTTPException(404, "Nutzer nicht gefunden")
    authmod.reset_credentials(user_id)
    return _invite_modal_response(request, user, current)
