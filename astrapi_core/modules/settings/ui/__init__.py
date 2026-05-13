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
    from astrapi_core.ui.module_registry import list_available_core_modules
    from astrapi_core.ui.settings_registry import all_settings
    from astrapi_core.ui.settings_registry import get_module as _get_mod

    modules = list(_registry.all().values())

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

    return {
        "settings": all_settings(),
        "modules": modules,
        "flash_message": flash,
        "core_module_list": list_available_core_modules(),
        "mod_settings": mod_settings,
    }


def _ssh_ctx(flash: str = "", flash_ok: bool = True) -> dict:
    return {
        "pubkey": _read_pubkey(),
        "flash": flash,
        "flash_ok": flash_ok,
    }


@router.get(f"/ui/{KEY}/content", response_class=HTMLResponse)
def settings_content(request: Request):
    return render(
        request,
        "content.html",
        {"module": KEY, "has_create": False, "container_id": "mod-settings", **_ctx()},
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
