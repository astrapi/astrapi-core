"""core/modules/settings/ui.py – FastAPI-Router für Settings UI-Routen."""

import subprocess
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from astrapi_core.ui.render import render

KEY = "settings"
router = APIRouter()

_SSH_DIR = Path.home() / ".ssh"
_KEY_TYPES = ["id_ed25519", "id_ecdsa", "id_rsa"]


def _find_key() -> tuple[Path | None, Path | None]:
    """Gibt (private_key_path, public_key_path) des ersten gefundenen Keys zurück."""
    for name in _KEY_TYPES:
        priv = _SSH_DIR / name
        pub = _SSH_DIR / f"{name}.pub"
        if priv.exists():
            return priv, pub
    return None, None


def _read_pubkey() -> str | None:
    _, pub = _find_key()
    if pub and pub.exists():
        return pub.read_text().strip()
    return None


def _generate_key() -> tuple[bool, str]:
    """Erzeugt ein neues ed25519-Schlüsselpaar. Gibt (ok, message) zurück."""
    _SSH_DIR.mkdir(mode=0o700, exist_ok=True)
    key_path = _SSH_DIR / "id_ed25519"
    try:
        subprocess.run(
            ["ssh-keygen", "-t", "ed25519", "-N", "", "-f", str(key_path)],
            check=True,
            capture_output=True,
        )
        return True, "Neues Schlüsselpaar erfolgreich erzeugt."
    except FileNotFoundError:
        return False, "ssh-keygen nicht gefunden."
    except subprocess.CalledProcessError as e:
        return False, e.stderr.decode().strip() or "Fehler beim Erzeugen des Schlüssels."


def _ctx(flash: str = "") -> dict:
    from astrapi_core.system.secrets import get_secret_safe as _get_secret
    from astrapi_core.ui.field_resolver import resolve_options_endpoint as _resolve
    from astrapi_core.ui.module_registry import _instance as _registry
    from astrapi_core.ui.settings_registry import all_settings
    from astrapi_core.ui.settings_registry import get_module as _get_mod

    # Stabiler Sort nach settings_order allein (nicht zusaetzlich nach key) --
    # bei Gleichstand (Default 0) bleibt die bisherige Registrierungs-
    # Reihenfolge erhalten (Core-Module vor App-Modulen, siehe
    # module_registry.load_modules()), nur explizit gesetzte Werte weichen ab.
    modules = sorted(_registry.all().values(), key=lambda m: m.settings_order)

    mod_settings = {}
    for m in modules:
        if not m.settings_schema:
            continue
        try:
            values = {
                f["key"]: (
                    _get_secret(f"module.{m.key}.{f['key']}", f.get("default", ""))
                    if f.get("type") == "password"
                    else _get_mod(m.key, f["key"], f.get("default", ""))
                )
                for f in m.settings_schema
                if "key" in f
            }
            mod_settings[m.key] = {
                "mod": m,
                "schema": _resolve(m.settings_schema),
                "values": values,
            }
        except Exception:
            pass

    # "System" hat aktuell nur ein Feld (extra_disks) -- statt einer eigenen
    # Karte wird es direkt in "Allgemein" mit angezeigt/gespeichert (siehe
    # settings.html + settings_save_global unten).
    mod_settings.pop("system", None)
    from astrapi_core.system.paths import extra_disk as _extra_disk

    return {
        "settings": all_settings(),
        "modules": modules,
        "flash_message": flash,
        "mod_settings": mod_settings,
        "extra_disk": _extra_disk(),
    }


def _ssh_ctx(flash: str = "", flash_ok: bool = True) -> dict:
    return {
        "pubkey": _read_pubkey(),
        "flash": flash,
        "flash_ok": flash_ok,
    }


def _content_ctx(flash: str = "") -> dict:
    return {"module": KEY, "has_create": False, "container_id": "mod-settings", **_ctx(flash)}


@router.get(f"/ui/{KEY}/content", response_class=HTMLResponse)
def settings_content(request: Request):
    return render(request, "content.html", _content_ctx())


def _content_string(request: Request) -> str:
    """Rendert den Content serverseitig fuer die generische Shell aus
    page_factory.py, siehe register_content_renderer() unten."""
    from astrapi_core.ui.render import render_string

    return render_string(request, "content.html", _content_ctx())


from astrapi_core.ui.page_factory import register_content_renderer  # noqa: E402

register_content_renderer(KEY, _content_string)


@router.post(f"/ui/{KEY}/save/global", response_class=HTMLResponse)
async def settings_save_global(request: Request):
    from astrapi_core.ui.settings_registry import set_many

    form = await request.form()
    values = dict(form)

    # extra_disks (System) ist in die Allgemein-Karte mit eingezogen (siehe
    # _ctx() oben) -- direkt mit dem module.system.-Praefix gespeichert
    # statt ueber eine eigene Modul-Karte.
    values["module.system.extra_disks"] = values.pop("extra_disks", "").strip()

    set_many(values)
    return render(
        request, "partials/lists/settings.html", _ctx("Globale Einstellungen gespeichert.")
    )


@router.post(f"/ui/{KEY}/save/module/{{module_key}}", response_class=HTMLResponse)
async def settings_save_module(module_key: str, request: Request):
    from astrapi_core.system.secrets import set_secret as _set_secret
    from astrapi_core.ui.module_registry import _instance as _registry
    from astrapi_core.ui.settings_registry import set_many

    mod = _registry.get(module_key)
    if mod is None:
        return HTMLResponse("Modul nicht gefunden", status_code=404)

    schema = mod.settings_schema or []
    password_keys = {f["key"] for f in schema if f.get("type") == "password"}
    list_keys = {f["key"] for f in schema if f.get("type") == "list"}

    form = await request.form()
    prefixed = {}
    for lk in list_keys:
        items, i = [], 0
        while True:
            val = form.get(f"{lk}_{i}")
            if val is None:
                break
            if val.strip():
                items.append(val.strip())
            i += 1
        prefixed[f"module.{module_key}.{lk}"] = items

    handled = {f"{lk}_{i}" for lk in list_keys for i in range(50)}
    for k, v in form.multi_items():
        if k in handled:
            continue
        if k in password_keys:
            if v.strip():
                _set_secret(f"module.{module_key}.{k}", v.strip())
        else:
            prefixed[f"module.{module_key}.{k}"] = v

    set_many(prefixed)
    return render(
        request,
        "partials/lists/settings.html",
        _ctx(f'Einstellungen für "{mod.label}" gespeichert.'),
    )


@router.get(f"/ui/{KEY}/ssh-key", response_class=HTMLResponse)
def ssh_key(request: Request):
    return render(request, "settings/partials/ssh_key.html", _ssh_ctx())


@router.post(f"/ui/{KEY}/ssh-key/generate", response_class=HTMLResponse)
def ssh_key_generate(request: Request):
    key_path = _SSH_DIR / "id_ed25519"
    if key_path.exists():
        backup = _SSH_DIR / "id_ed25519.bak"
        key_path.rename(backup)
        pub = _SSH_DIR / "id_ed25519.pub"
        if pub.exists():
            pub.rename(_SSH_DIR / "id_ed25519.pub.bak")
    ok, msg = _generate_key()
    return render(request, "settings/partials/ssh_key.html", _ssh_ctx(msg, ok))
