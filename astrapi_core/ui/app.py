"""
core/ui/app.py  –  Astrapi UI-Framework  Factory

Konfiguriert eine FastAPI-App mit:
  - Modul-Discovery und Template-Loader
  - Navigation aus Modulen + optionaler items.yaml
  - Einstellungs-Registry (global + Modul-Defaults)
  - UI-Routen für alle Module (Shell, Content, Modals, Settings, Preferences)
  - Globaler Template-Context (entspricht Flask's context_processor)
"""

from __future__ import annotations

import importlib.util
import time
from pathlib import Path
from typing import Callable, Optional

from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse
from jinja2 import ChoiceLoader, FileSystemLoader

from ..system.paths import is_debug, is_ui_debug
from ..system.version import get_app_name, get_app_version, get_core_version, get_display_name
from .module_registry import (
    build_nav_items,
    load_modules,
    register_ui_modules,
)
from .page_factory import register_pages
from .settings_registry import (
    get_activity_log_retention_days,
    seed_defaults,
)
from .settings_registry import (
    get as settings_get,
)
from .settings_registry import (
    init as settings_init,
)
from .settings_registry import (
    set as settings_set,
)
CORE_ROOT = Path(__file__).resolve().parent


# ── Remote-Host-Resolver-Registry ────────────────────────────────────────────
# Apps registrieren ihre eigene Implementierung via register_remote_resolver().

_remote_host_resolver = None


def register_remote_resolver(fn) -> None:
    """Registriert eine App-spezifische Funktion zur Remote-Host-Auflösung.

    fn: Callable[[str | int], str]  →  Hostname oder '—'
    Wird von Apps (z.B. astrapi-backup) aus modules/remotes/__init__.py aufgerufen.
    """
    global _remote_host_resolver
    _remote_host_resolver = fn


def _load_module_file(name: str, path: Path):
    import sys

    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_ACTIVITY_LOG_RETENTION_INTERVAL = 24 * 60 * 60  # einmal taeglich


def _start_activity_log_retention_loop() -> None:
    """Setzt die Activity-Log-Aufbewahrung durch, sofort und danach taeglich.

    Analog zu start_watchdog() (system/systemd.py) und dem Refresh-Thread in
    astrapi_packages/modules/debian/utils/pkg_cache.py: ein Daemon-Thread mit
    einer Sleep-Schleife, weil die App-Prozesse oft wochenlang ohne Neustart
    laufen -- ein Aufruf nur beim Start wuerde in der Praxis nie greifen.
    """
    import threading
    import time

    def _loop():
        while True:
            try:
                from astrapi_core.system.activity_log import enforce_activity_log_retention

                enforce_activity_log_retention(get_activity_log_retention_days())
            except Exception:
                pass
            time.sleep(_ACTIVITY_LOG_RETENTION_INTERVAL)

    threading.Thread(target=_loop, daemon=True, name="activity-log-retention").start()


def create(
    api,
    app_root: Path,
    config: Optional[dict] = None,
    extra_init: Optional[Callable] = None,
    modules: Optional[list] = None,
) -> None:
    """Konfiguriert die FastAPI-App mit dem UI-Framework.

    api:      FastAPI-Instanz (wird in-place modifiziert)
    app_root: Root-Verzeichnis der Applikation (enthält modules/, templates/, …)
    modules:  Vorgeladene Modulliste. Wird nicht neu geladen wenn angegeben.
    """
    from jinja2 import Environment
    from starlette.templating import Jinja2Templates

    from . import fastapi_templates as _ft
    from .render import configure as configure_render

    # ── App-Konfiguration laden ───────────────────────────────────────────────
    app_cfg: dict = {}
    cfg_yaml = app_root / "config.yaml"
    if cfg_yaml.exists():
        import yaml as _yaml

        with open(cfg_yaml, encoding="utf-8") as _f:
            _raw = _yaml.safe_load(_f) or {}
        _app = _raw.get("app", {})
        app_cfg = {
            "APP_NAME": _app.get("name", "myapp"),
            "APP_LANG": _app.get("lang", "de"),
            "LIGHT_MODE": bool(_app.get("light_mode", False)),
            "APP_LOGO_SVG": _app.get("logo_svg", None),
        }
    else:
        for cfg_name in ("settings.py", "config.py"):
            cfg_path = app_root / cfg_name
            if cfg_path.exists():
                mod = _load_module_file("app_settings", cfg_path)
                app_cfg = {k: v for k, v in vars(mod).items() if not k.startswith("_")}
                break

    _app_version = get_app_version(app_root)
    _app_name = get_app_name(app_root)
    _display_name = get_display_name(app_root)
    _core_version = get_core_version(CORE_ROOT.parent)

    # ── Module laden ──────────────────────────────────────────────────────────
    failed_module_keys: set = set()
    if modules is None:
        modules, failed_module_keys = load_modules(app_root)

    # ── Einstellungs-Registry initialisieren ──────────────────────────────────
    settings_init(app_root)
    _light_default = "1" if app_cfg.get("LIGHT_MODE", False) else "0"
    global_defaults = {
        k: v
        for k, v in app_cfg.items()
        if k not in ("LIGHT_MODE", "APP_LOGO_SVG") and not callable(v)
    }
    global_defaults.setdefault("LIGHT_MODE", _light_default)
    global_defaults.setdefault("TIMEZONE", "Europe/Berlin")
    global_defaults.setdefault("DATE_FORMAT", "DD.MM.YYYY")
    global_defaults.setdefault("PAGINATION_PAGE_SIZE", 15)
    global_defaults.setdefault("ACTIVITY_LOG_RETENTION_DAYS", 90)
    seed_defaults(global_defaults, modules, failed_module_keys)

    # Aufbewahrung durchsetzen (T-113/T-114): ein einmaliger Aufruf beim Start
    # reicht nicht -- die Prozesse laufen oft wochen- bis monatelang ohne
    # Neustart. Stattdessen ein Hintergrund-Thread, der sofort einmal prueft
    # und danach taeglich erneut (Aufbewahrung ist ohnehin nur tagegenau).
    _start_activity_log_retention_loop()

    # ── Template-Loader: Modul > App > Core > Dialogs ────────────────────────
    app_templates = app_root / "templates"
    core_templates = CORE_ROOT / "templates"
    core_dialogs   = CORE_ROOT / "dialogs"

    base_loaders: list = []
    if app_templates.exists():
        base_loaders.append(FileSystemLoader(str(app_templates)))
    base_loaders.append(FileSystemLoader(str(core_templates)))
    if core_dialogs.exists():
        base_loaders.append(FileSystemLoader(str(core_dialogs)))

    all_loaders = list(base_loaders)
    # register_ui_modules fügt Modul-Loader vorne ein (höchste Priorität)
    register_ui_modules(api, modules, all_loaders)

    jinja_env = Environment(
        loader=ChoiceLoader(all_loaders),
        autoescape=True,
        auto_reload=True,
    )
    templates = Jinja2Templates(env=jinja_env)
    jinja_env.globals["is_debug"] = is_debug()
    jinja_env.globals["is_ui_debug"] = is_ui_debug()
    _static_v = int(time.time())

    _ft.configure(templates)

    # ── Icon-Sprite aus Modul-Ordnern + ui/icons/ bauen ──────────────────────
    from .icons import build_sprite as _build_sprite

    _extra_icon_dirs = [
        CORE_ROOT / "icons",  # astrapi_core/ui/icons/     (generische UI-Icons)
        app_root / "ui" / "icons",  # z.B. astrapi_backup/ui/icons/
    ]
    jinja_env.globals["icon_sprite"] = _build_sprite(modules, _extra_icon_dirs)

    # ── Globalen Template-Context konfigurieren ────────────────────────────────
    _mod_map: dict = {m.key: m for m in modules}

    # Als Jinja2-Global registrieren, damit Makros Zugriff haben
    def _resolve_remote_host(remote_id) -> str:
        if not remote_id:
            return "—"
        if _remote_host_resolver is not None:
            try:
                return _remote_host_resolver(remote_id) or "—"
            except Exception:
                return "—"
        return "—"

    jinja_env.globals["resolve_remote_host"] = _resolve_remote_host

    from ..system.format import version_is_newer

    jinja_env.globals["version_is_newer"] = version_is_newer

    # module_obj als Jinja2-Global damit Makros (col_cell etc.) darauf zugreifen können
    def _module_obj(key: str):
        return _mod_map.get(key)

    jinja_env.globals["module_obj"] = _module_obj

    def _global_ctx() -> dict:
        def module_obj(key: str):
            """Gibt das vollständige Module-Objekt zurück (für deklaratives UI)."""
            return _module_obj(key)

        def module_label(key: str) -> str:
            m = _mod_map.get(key)
            return m.label if m else key.replace("_", " ").title()

        def module_card_actions(key: str) -> list:
            m = _mod_map.get(key)
            return m.card_actions if m else []

        def col_widths(module_key: str) -> str:
            return settings_get(f"ui.col_widths.{module_key}", "{}")

        def last_run_status(module: str, item_id) -> str | None:
            try:
                from astrapi_core.system.activity_log import list_runs_for_item

                runs = list_runs_for_item(module, str(item_id), limit=5)
                for run in runs:
                    if run.get("status") != "running":
                        return run.get("status")
            except Exception:
                pass
            return None

        from astrapi_core.ui.settings_registry import get as _srget

        _light = _srget("LIGHT_MODE", _light_default)

        return {
            "app_name": _display_name,
            "app_version": _app_version,
            "core_version": _core_version,
            "app_logo_svg": app_cfg.get("APP_LOGO_SVG", None),
            "app_lang": _srget("APP_LANG", app_cfg.get("APP_LANG", "de")),
            "light_mode": (_light == "1" or _light is True),
            "modules": modules,
            "module_obj": module_obj,
            "module_label": module_label,
            "module_card_actions": module_card_actions,
            "col_widths": col_widths,
            "resolve_remote_host": _resolve_remote_host,
            "last_run_status": last_run_status,
            "show_ssh_key": app_cfg.get("SHOW_SSH_KEY", False),
            "nav_items": _nav_items_ref[0],
            "is_debug": is_debug(),
            "is_ui_debug": is_ui_debug(),
            "static_v": _static_v,
        }

    # Platzhalter – wird nach build_nav_items befüllt
    _nav_items_ref: list = [None]

    configure_render(_global_ctx)

    # ── Navigation ────────────────────────────────────────────────────────────
    nav_items = build_nav_items(modules, app_root=app_root)
    _nav_items_ref[0] = nav_items

    # ── Seiten-Routen registrieren ────────────────────────────────────────────
    module_keys = {m.key for m in modules if m.ui_router is not None}
    register_pages(api, nav_items, shell_only_keys=module_keys)

    # ── Optionale App-Blueprints / App-Routes ─────────────────────────────────
    routes_init_path = app_root / "routes" / "__init__.py"
    if routes_init_path.exists():
        mod = _load_module_file("app_routes", routes_init_path)
        if hasattr(mod, "register"):
            mod.register(api)
        elif hasattr(mod, "router"):
            api.include_router(mod.router)

    # ── Preferences-Routen ────────────────────────────────────────────────────
    _register_preferences_routes(api)

    # ── Projektspezifischer Hook ──────────────────────────────────────────────
    if extra_init:
        extra_init(api)

    # ── Dev-Routen (nur im Debug-Modus) ──────────────────────────────────────
    if is_debug():
        from .dev_routes import router as _dev_router
        api.include_router(_dev_router)

    # ── Scheduler starten ─────────────────────────────────────────────────────
    try:
        from astrapi_core.modules.scheduler.engine import init as scheduler_init

        scheduler_init()
    except Exception as _e:
        import warnings

        warnings.warn(f"Scheduler konnte nicht gestartet werden: {_e}")

    # ── Root-Redirect → erstes/default Nav-Item ───────────────────────────────
    default_item = next(
        (it for it in nav_items if not it.get("separator") and it.get("default")),
        next((it for it in nav_items if not it.get("separator")), None),
    )
    if default_item:
        _default_key = default_item["key"]

        @api.get("/", response_class=RedirectResponse, include_in_schema=False)
        def _root():
            return RedirectResponse(f"/{_default_key}")

    # ── Swagger UI-Docs (optional) ─────────────────────────────────────────────
    try:
        from .swagger_utils import register_ui_docs

        swagger_html = CORE_ROOT / "static" / "swagger.html"
        if not swagger_html.exists():
            swagger_html = app_root / "static" / "swagger.html"
        register_ui_docs(api, project_root=CORE_ROOT.parent, swagger_html_path=swagger_html)
    except Exception as e:
        import warnings

        warnings.warn(f"UI-Docs konnten nicht registriert werden: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Preferences-Routen (Spaltenbreiten etc.)
# ─────────────────────────────────────────────────────────────────────────────


def _register_preferences_routes(api) -> None:

    @api.api_route(
        "/ui/preferences/col-widths/{module_key}",
        methods=["GET", "POST"],
        response_class=JSONResponse,
        include_in_schema=False,
    )
    async def preferences_col_widths(module_key: str, request: Request):
        key = f"ui.col_widths.{module_key}"
        if request.method == "POST":
            data = await request.json()
            import json

            settings_set(key, json.dumps(data.get("widths", {})))
            return JSONResponse({"ok": True})
        return JSONResponse({"widths": __import__("json").loads(settings_get(key, "{}"))})
