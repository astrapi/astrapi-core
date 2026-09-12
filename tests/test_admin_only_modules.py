"""Modul-Sichtbarkeit für Nicht-Admins bei Multi-User-Apps (astrapi-sync):
system/settings/notify/activity_log/scheduler sind admin_only=True (siehe
modul.yaml der jeweiligen Module) -- normale Nutzer sollen eine abgespeckte
Oberfläche sehen (nur folders/folder_groups/devices + read-only Nutzerliste).

Diese Tests decken die drei plumbing-Stellen ab, nicht den vollen App-Start:
1. Module.to_nav_item() liefert admin_only mit.
2. module_loader.load_modul() liest admin_only aus modul.yaml.
3. register_ui_modules()/register_pages() blocken admin_only-Router/-Routen
   serverseitig, wenn ein admin_guard übergeben wird -- unabhängig davon, ob
   das Modul in der Nav auftaucht (Schutz gegen direkten URL-Aufruf)."""
from pathlib import Path
from unittest.mock import patch

import yaml
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from astrapi_core.ui._base import Module
from astrapi_core.ui.module_loader import load_modul
from astrapi_core.ui.module_registry import register_ui_modules
from astrapi_core.ui.page_factory import register_pages


def test_to_nav_item_enthaelt_admin_only_default_false():
    mod = Module(key="folders", label="Ordner")
    assert mod.to_nav_item()["admin_only"] is False


def test_to_nav_item_enthaelt_admin_only_true():
    mod = Module(key="system", label="System", admin_only=True)
    assert mod.to_nav_item()["admin_only"] is True


def test_load_modul_liest_admin_only_aus_modul_yaml(tmp_path: Path):
    module_dir = tmp_path / "system"
    (module_dir / "config").mkdir(parents=True)
    (module_dir / "config" / "modul.yaml").write_text(
        yaml.dump({"label": "System", "admin_only": True}), encoding="utf-8"
    )
    mod = load_modul(module_dir, "system", None, None)
    assert mod.admin_only is True


def test_load_modul_ohne_admin_only_key_ist_false(tmp_path: Path):
    module_dir = tmp_path / "folders"
    (module_dir / "config").mkdir(parents=True)
    (module_dir / "config" / "modul.yaml").write_text(
        yaml.dump({"label": "Ordner"}), encoding="utf-8"
    )
    mod = load_modul(module_dir, "folders", None, None)
    assert mod.admin_only is False


def _denying_guard(request: Request) -> None:
    raise HTTPException(403, "nur der Admin darf auf dieses Modul zugreifen")


def _passing_guard(request: Request) -> None:
    return None


# ── register_ui_modules() ────────────────────────────────────────────────


def test_register_ui_modules_blockt_admin_only_router_mit_guard():
    router = APIRouter()

    @router.get("/ui/system/content")
    def _content():
        return {"ok": True}

    mod = Module(key="system", label="System", admin_only=True, ui_router=router)
    app = FastAPI()
    register_ui_modules(app, [mod], [], admin_guard=_denying_guard)
    client = TestClient(app)
    assert client.get("/ui/system/content").status_code == 403


def test_register_ui_modules_laesst_nicht_admin_only_router_unberuehrt():
    router = APIRouter()

    @router.get("/ui/folders/content")
    def _content():
        return {"ok": True}

    mod = Module(key="folders", label="Ordner", admin_only=False, ui_router=router)
    app = FastAPI()
    register_ui_modules(app, [mod], [], admin_guard=_denying_guard)
    client = TestClient(app)
    assert client.get("/ui/folders/content").status_code == 200


def test_register_ui_modules_ohne_guard_param_aendert_nichts():
    """Rückwärtskompatibilität: admin_guard=None (Default) -- alle anderen
    Apps (backup/mirror/packages/admin, kein multi_user) rufen
    register_ui_modules() unverändert ohne den neuen Parameter auf."""
    router = APIRouter()

    @router.get("/ui/system/content")
    def _content():
        return {"ok": True}

    mod = Module(key="system", label="System", admin_only=True, ui_router=router)
    app = FastAPI()
    register_ui_modules(app, [mod], [])
    client = TestClient(app)
    assert client.get("/ui/system/content").status_code == 200


# ── register_pages() (Shell-/Content-Route, NICHT Teil von mod.ui_router) ──


def test_register_pages_blockt_shell_und_content_route_fuer_admin_only():
    """Die Dependency wirft schon vor dem Route-Body -- render() wird für
    den 403-Fall gar nicht erst erreicht, muss hier also nicht gemockt
    werden (anders als im Erfolgsfall unten)."""
    nav_items = [{"key": "system", "label": "System", "admin_only": True, "default": True}]
    app = FastAPI()
    register_pages(app, nav_items, admin_guard=_denying_guard)
    client = TestClient(app)
    assert client.get("/system").status_code == 403
    assert client.get("/ui/system/content").status_code == 403


def test_register_pages_laesst_normale_module_unberuehrt():
    nav_items = [{"key": "folders", "label": "Ordner", "admin_only": False, "default": True}]
    app = FastAPI()
    with patch("astrapi_core.ui.render.render") as mock_render, patch(
        "astrapi_core.ui.render.render_string"
    ) as mock_render_string:
        mock_render.return_value = "ok"
        mock_render_string.return_value = "ok"
        register_pages(app, nav_items, admin_guard=_denying_guard)
        client = TestClient(app)
        assert client.get("/folders").status_code == 200
        assert client.get("/ui/folders/content").status_code == 200
