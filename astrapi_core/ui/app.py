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

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from astrapi_core.ui.color_palette import color_palette
from jinja2 import ChoiceLoader, FileSystemLoader

from ..system.categories_scope import set_categories_scope_mode
from ..system.manifest import register_manifest
from ..system.paths import is_debug, is_ui_debug
from ..system.version import (
    DEFAULT_ICON_SVG,
    get_app_icon_svg,
    get_app_name,
    get_app_version,
    get_auth_config,
    get_categories_scope,
    get_core_version,
    get_display_name,
)
from .module_registry import (
    build_nav_items,
    load_modules,
    register_ui_modules,
)
from .page_factory import register_pages
from .settings_registry import (
    get as settings_get,
)
from .settings_registry import (
    get_activity_log_retention_days,
    seed_defaults,
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
    _icon_svg = get_app_icon_svg(app_root) or DEFAULT_ICON_SVG

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

    # Auth (WebAuthn/Passkey-Login, opt-in über app.yaml: auth.enabled) --
    # Startwerte für rp_id/rp_name/origin, später über die Settings-UI
    # änderbar ohne app.yaml erneut anzufassen (siehe [[E-003]]).
    auth_cfg = get_auth_config(app_root)
    # Kategorien (modules/categories) -- 'owner' (Default) oder 'shared'
    # (app.yaml: categories.scope), siehe system/categories_scope.py.
    # Einmal pro Prozess gesetzt, kein Settings-Wert wie AUTH_* oben --
    # unabhaengig davon spaeter aenderbar zu machen waere eine Migration
    # bestehender Kategorien-Zeilen wert, kein reiner Konfig-Wert.
    set_categories_scope_mode(get_categories_scope(app_root))
    global_defaults.setdefault("AUTH_RP_ID", auth_cfg["rp_id"])
    global_defaults.setdefault("AUTH_RP_NAME", auth_cfg["rp_name"] or _display_name)
    global_defaults.setdefault("AUTH_ORIGIN", auth_cfg["origin"])
    global_defaults.setdefault("AUTH_PASSWORD_FALLBACK", auth_cfg["password_fallback"])
    # Fuer ui/auth_routes.py::login_password() -- ob ein Passwort-Login
    # einen Nutzernamen braucht (mehrere eigene Passwoerter moeglich) oder
    # nicht (Single-Owner, ein geteiltes Passwort, bisheriges Verhalten).
    global_defaults.setdefault("AUTH_MULTI_USER", auth_cfg["multi_user"])

    seed_defaults(global_defaults, modules, failed_module_keys)

    # Reparatur für Apps, die schon vor dieser Einführung von auth.enabled
    # gelaufen sind: seed_defaults() schreibt einen Default nur EINMAL, wenn
    # der Schlüssel noch fehlt. AUTH_RP_ID wurde aber schon bei jedem
    # bisherigen Boot berechnet (get_auth_config() liefert "" wenn kein
    # auth:-Block existiert) und dadurch als "" persistiert -- ein späteres
    # Nachtragen von auth.rp_id in app.yaml hätte also NIE gegriffen, seed
    # sieht den Schlüssel ja schon als vorhanden an. Ohne diese gezielte
    # Korrektur bricht die WebAuthn-Registrierung mit "rp_id cannot be an
    # empty string", sobald auth erstmals für eine bereits laufende App
    # aktiviert wird (sync-dev, T-Multi-User). Überschreibt NUR den
    # Leerstring-Fall -- ein über die Settings-UI bewusst gesetzter Wert
    # bleibt unangetastet.
    if auth_cfg["enabled"] and auth_cfg["rp_id"] and not settings_get("AUTH_RP_ID", ""):
        settings_set("AUTH_RP_ID", auth_cfg["rp_id"])

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

    def _admin_only_guard(request: Request) -> None:
        """Dependency für Module mit admin_only=True (siehe _base.py) --
        Single-Owner-Apps (auth.multi_user nicht gesetzt) bleiben unberührt,
        der eine Nutzer ist dort immer is_admin=1 (system/auth.py-Migration)."""
        if not auth_cfg["multi_user"]:
            return
        from astrapi_core.system import auth as authmod
        from astrapi_core.ui.auth_routes import _session_cookie

        user = authmod.get_current_user(_session_cookie(request))
        if not user or not user.get("is_admin"):
            raise HTTPException(403, "nur der Admin darf auf dieses Modul zugreifen")

    all_loaders = list(base_loaders)
    # register_ui_modules fügt Modul-Loader vorne ein (höchste Priorität)
    register_ui_modules(api, modules, all_loaders, admin_guard=_admin_only_guard)

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

    # T-323-CORE: HTMX-Ziel-URL fuer einen Sortier-Klick auf eine Col.sortable-
    # Spaltenueberschrift -- uebernimmt die aktuellen Query-Parameter (Filter),
    # setzt sort=<key> + togglet dir, Seite zurueck auf 1.
    def _sort_url(request, sort_key: str) -> str:
        cur_sort = request.query_params.get("sort")
        cur_dir = request.query_params.get("dir", "asc")
        new_dir = "desc" if cur_sort == sort_key and cur_dir == "asc" else "asc"
        params = {
            k: v for k, v in request.query_params.items() if k not in ("page", "sort", "dir")
        }
        params["sort"] = sort_key
        params["dir"] = new_dir
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{request.url.path}?{qs}"

    jinja_env.globals["sort_url"] = _sort_url

    def _global_ctx(request: Request) -> dict:
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

        _nav = _nav_items_ref[0]
        _current_user = None
        if auth_cfg["enabled"]:
            # current_user fuer die Seitenleiste (angemeldeter Nutzername,
            # siehe navigation/index.html) -- bei Multi-User-Apps zusaetzlich
            # fuer die Nav-Filterung unten wiederverwendet.
            from astrapi_core.system import auth as authmod
            from astrapi_core.ui.auth_routes import _session_cookie

            _current_user = authmod.get_current_user(_session_cookie(request))
        if auth_cfg["multi_user"]:
            # Abgespeckte Oberfläche für Nicht-Admins: admin_only-Module
            # (system/settings/notify/activity_log) aus der Nav filtern --
            # serverseitig, pro Request, da nav_items sonst nur einmal beim
            # Start berechnet wird (siehe _admin_only_guard oben für den
            # dazugehörigen Routen-Schutz, falls die URL trotzdem geraten wird).
            if not (_current_user and _current_user.get("is_admin")):
                _nav = [it for it in _nav if not it.get("admin_only")]

        return {
            "app_name": _display_name,
            "app_version": _app_version,
            "core_version": _core_version,
            "app_icon_svg": _icon_svg,
            "app_lang": _srget("APP_LANG", app_cfg.get("APP_LANG", "de")),
            "light_mode": (_light == "1" or _light is True),
            "modules": modules,
            "module_obj": module_obj,
            "module_label": module_label,
            "module_card_actions": module_card_actions,
            "col_widths": col_widths,
            "color_palette": color_palette,
            "resolve_remote_host": _resolve_remote_host,
            "last_run_status": last_run_status,
            "show_ssh_key": app_cfg.get("SHOW_SSH_KEY", False),
            "nav_items": _nav,
            "auth_enabled": auth_cfg["enabled"],
            "current_user": _current_user,
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
    register_pages(api, nav_items, shell_only_keys=module_keys, admin_guard=_admin_only_guard)

    # ── PWA-Manifest (Installierbarkeit unter Android/Chrome) ────────────────
    register_manifest(api, _display_name, _icon_svg)

    # ── Optionale App-Blueprints / App-Routes ─────────────────────────────────
    routes_init_path = app_root / "routes" / "__init__.py"
    if routes_init_path.exists():
        mod = _load_module_file("app_routes", routes_init_path)
        if hasattr(mod, "register"):
            mod.register(api)
        elif hasattr(mod, "router"):
            api.include_router(mod.router)

    # ── Auth-Routen + Login-Gate (nur wenn app.yaml: auth.enabled) ───────────
    if auth_cfg["enabled"]:
        from .auth_middleware import RequireLoginMiddleware
        from .auth_routes import router as _auth_router

        api.include_router(_auth_router)
        api.add_middleware(RequireLoginMiddleware, exempt_prefixes=auth_cfg["exempt_prefixes"])

        # T-325-CORE: current_user_id() braucht dafuer aktive Middleware --
        # generisch fuer jede App mit auth.enabled, nicht nur multi_user
        # (Single-Owner-Apps bekommen so denselben current_user_id()-
        # Rueckfall-Pfad wie Multi-User-Apps, siehe current_user.py).
        from ..system.current_user import CurrentUserMiddleware

        api.add_middleware(CurrentUserMiddleware)

        if auth_cfg["multi_user"]:
            from .multi_user_routes import router as _multi_user_router

            api.include_router(_multi_user_router)

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
    # Bei gesetztem admin_prefix (astrapi-mirror/-packages/-sync) liegt die
    # blanke Wurzel "/" NICHT beim Dashboard -- die App liefert dort ihre
    # eigenen Inhalte (z.B. repo.py's Datei-Index) aus. Der Redirect zieht
    # dann auf f"{admin_prefix}/" um, sonst wuerde er "/" mit der
    # App-eigenen Route kollidieren (Registrierungsreihenfolge in
    # Starlette entscheidet sonst zufaellig, wer gewinnt).
    default_item = next(
        (it for it in nav_items if not it.get("separator") and it.get("default")),
        next((it for it in nav_items if not it.get("separator")), None),
    )
    if default_item:
        from astrapi_core.system.paths import admin_prefix as _admin_prefix

        _redirect_target = default_item["url"]
        _root_path = f"{_admin_prefix()}/" if _admin_prefix() else "/"

        @api.get(_root_path, response_class=RedirectResponse, include_in_schema=False)
        def _root():
            return RedirectResponse(_redirect_target)

        # Bei gesetztem Praefix zusaetzlich die trailing-slash-lose
        # Variante (z.B. "/admin" ohne "/") explizit registrieren --
        # Starlettes eingebauter redirect_slashes greift hier NICHT
        # automatisch, weil "/admin" sonst schon von einer anderen,
        # generischen App-Route (z.B. repo.py's "/{os_type}") abgefangen
        # wuerde, bevor der automatische Fallback je zum Zug kaeme.
        if _admin_prefix():

            @api.get(_admin_prefix(), response_class=RedirectResponse, include_in_schema=False)
            def _root_no_slash():
                return RedirectResponse(_root_path)

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
