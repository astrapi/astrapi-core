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
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from jinja2 import ChoiceLoader, FileSystemLoader

from ..system.paths import is_debug, is_ui_debug
from ..system.version import get_app_name, get_app_version, get_core_version, get_display_name
from .module_registry import (
    build_nav_items,
    list_available_core_modules,
    load_modules,
    register_ui_modules,
)
from .page_factory import register_pages
from .settings_registry import (
    all_settings,
    seed_defaults,
    set_many,
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
from .storage import init as storage_init

CORE_ROOT = Path(__file__).resolve().parent


def _load_module_file(name: str, path: Path):
    import sys

    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


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
    storage_init(app_root)
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
    seed_defaults(global_defaults, modules, failed_module_keys)

    # ── Template-Loader: Modul > App > Core ──────────────────────────────────
    app_templates = app_root / "templates"
    core_templates = CORE_ROOT / "templates"

    base_loaders: list = []
    if app_templates.exists():
        base_loaders.append(FileSystemLoader(str(app_templates)))
    base_loaders.append(FileSystemLoader(str(core_templates)))

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
        try:
            from app.modules.remotes.engine import get_remote

            r = get_remote(remote_id)
            return r.get("host") or "—" if r else "—"
        except Exception:
            return "—"

    jinja_env.globals["resolve_remote_host"] = _resolve_remote_host

    # module_obj als Jinja2-Global damit Makros (col_cell etc.) darauf zugreifen können
    def _module_obj(key: str):
        return _mod_map.get(key)

    jinja_env.globals["module_obj"] = _module_obj

    def _global_ctx() -> dict:
        def module_has_settings(key: str) -> bool:
            m = _mod_map.get(key)
            return bool(m and m.settings_schema and m.settings_button)

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
            "module_has_settings": module_has_settings,
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
    register_pages(
        api, [it for it in nav_items if it.get("key") != "settings"], shell_only_keys=module_keys
    )

    # ── Optionale App-Blueprints / App-Routes ─────────────────────────────────
    routes_init_path = app_root / "routes" / "__init__.py"
    if routes_init_path.exists():
        mod = _load_module_file("app_routes", routes_init_path)
        if hasattr(mod, "register"):
            mod.register(api)
        elif hasattr(mod, "router"):
            api.include_router(mod.router)

    # ── Einstellungs-Routen ───────────────────────────────────────────────────
    settings_has_router = any(m.key == "settings" and m.ui_router for m in modules)
    _register_settings_routes(api, modules, app_cfg, skip_content=settings_has_router)
    _register_preferences_routes(api)

    # ── Generische Modul-Settings-Modal-Routen ────────────────────────────────
    _register_module_settings_routes(api, modules)

    # ── Projektspezifischer Hook ──────────────────────────────────────────────
    if extra_init:
        extra_init(api)

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
# Einstellungs-Routen
# ─────────────────────────────────────────────────────────────────────────────


def _register_settings_routes(
    api, modules: list, app_cfg: dict, skip_content: bool = False
) -> None:
    from astrapi_core.ui.render import render

    def _ctx(flash: str = "") -> dict:
        from astrapi_core.system.secrets import get_secret_safe as _get_secret
        from astrapi_core.ui.field_resolver import resolve_options_endpoint as _resolve
        from astrapi_core.ui.settings_registry import get_module as _get_mod

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
            "app_cfg": app_cfg,
            "flash_message": flash,
            "core_module_list": list_available_core_modules(),
            "mod_settings": mod_settings,
        }

    @api.get("/settings", response_class=HTMLResponse, include_in_schema=False)
    def settings_shell(request: Request):
        from astrapi_core.ui.render import render_string

        initial_content = render_string(
            request,
            "content.html",
            {"module": "settings", "has_create": False, "container_id": "mod-settings", **_ctx()},
        )
        return render(
            request,
            "index.html",
            dict(
                active_tab="settings",
                initial_content=initial_content,
                title="Einstellungen",
            ),
        )

    if not skip_content:

        @api.get("/ui/settings/content", response_class=HTMLResponse, include_in_schema=False)
        def settings_content(request: Request):
            return render(
                request,
                "content.html",
                {
                    "module": "settings",
                    "has_create": False,
                    "container_id": "mod-settings",
                    **_ctx(),
                },
            )

    @api.post("/ui/settings/save/global", response_class=HTMLResponse, include_in_schema=False)
    async def settings_save_global(request: Request):
        form = await request.form()
        set_many(dict(form))
        return render(
            request, "partials/lists/settings.html", _ctx("Globale Einstellungen gespeichert.")
        )

    @api.post(
        "/ui/settings/save/module/{module_key}",
        response_class=HTMLResponse,
        include_in_schema=False,
    )
    async def settings_save_module(module_key: str, request: Request):
        mod = next((m for m in modules if m.key == module_key), None)
        if mod is None:
            return HTMLResponse("Modul nicht gefunden", status_code=404)

        from astrapi_core.system.secrets import set_secret as _set_secret

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

    @api.post(
        "/ui/settings/core-module/{key}/toggle",
        response_class=HTMLResponse,
        include_in_schema=False,
    )
    def settings_toggle_core_module(key: str, request: Request):
        current = settings_get(f"core.module.{key}.enabled", "1")
        settings_set(f"core.module.{key}.enabled", "0" if current != "0" else "1")
        return render(
            request,
            "partials/lists/settings.html",
            _ctx(
                f"Core-Modul '{key}' {'deaktiviert' if current != '0' else 'aktiviert'}. Neustart erforderlich."
            ),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Generische Modul-Settings-Modal-Routen
# ─────────────────────────────────────────────────────────────────────────────


def _register_module_settings_routes(api, modules: list) -> None:
    from astrapi_core.system.secrets import get_secret_safe, set_secret
    from astrapi_core.ui.render import render

    from .settings_registry import get_module
    from .settings_registry import set_many as _set_many

    mod_map = {m.key: m for m in modules if m.settings_schema}
    if not mod_map:
        return

    @api.api_route(
        "/ui/{module_key}/settings",
        methods=["GET", "POST"],
        response_class=HTMLResponse,
        include_in_schema=False,
    )
    async def module_settings_modal(module_key: str, request: Request):
        mod = mod_map.get(module_key)
        if mod is None:
            return HTMLResponse("", status_code=404)

        if request.method == "GET":
            from astrapi_core.ui.module_loader import reload_settings

            reload_settings(mod)

        if request.method == "POST":
            form = await request.form()
            password_keys = {f["key"] for f in mod.settings_schema if f.get("type") == "password"}
            list_keys = {f["key"] for f in mod.settings_schema if f.get("type") == "list"}
            prefixed = {}
            for lk in list_keys:
                items = []
                i = 0
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
                        set_secret(f"module.{module_key}.{k}", v.strip())
                else:
                    prefixed[f"module.{module_key}.{k}"] = v
            _set_many(prefixed)

        password_keys_all = {f["key"] for f in mod.settings_schema if f.get("type") == "password"}
        current_values = {
            field["key"]: (
                get_secret_safe(f"module.{module_key}.{field['key']}", field.get("default", ""))
                if field["key"] in password_keys_all
                else get_module(module_key, field["key"], field.get("default", ""))
            )
            for field in mod.settings_schema
            if "key" in field
        }
        from astrapi_core.ui.field_resolver import resolve_options_endpoint

        return render(
            request,
            "partials/settings_modal.html",
            dict(
                mod=mod,
                schema=resolve_options_endpoint(mod.settings_schema),
                values=current_values,
            ),
        )


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
