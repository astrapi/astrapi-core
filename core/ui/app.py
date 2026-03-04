"""
core/ui/app.py  –  AstrapiFlaskUi V2  Framework-Factory

Erstellt die Flask-App mit:
  - Dualem Template-Loader  (app/ überschreibt core/)
  - Dualem Static-Loader    (app/static/ hat Vorrang)
  - Automatischer Page/Tab-Registrierung aus items.yaml
  - API-Blueprint-Unterstützung (app/api/__init__.py)
  - Flask-Blueprint-Unterstützung (app/routes/__init__.py)
  - Konfigurierbaren Jinja2-Globals aus app/settings.py
  - extra_init-Hook für projektspezifische Erweiterungen

Das gesamte core/-Verzeichnis kann per Update ausgetauscht werden,
ohne die app/-Implementierung zu berühren.
"""

from __future__ import annotations

from flask import Flask, redirect, send_from_directory
from pathlib import Path
from jinja2 import ChoiceLoader, FileSystemLoader
import importlib.util
from typing import Optional, Callable

from .navigation import load_nav
from .page_factory import register_pages

CORE_ROOT = Path(__file__).resolve().parents[1]


# ─────────────────────────────────────────────────────────────────────────────
# Interne Hilfsfunktion: Modul aus Dateipfad laden
# ─────────────────────────────────────────────────────────────────────────────
def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ─────────────────────────────────────────────────────────────────────────────
# create()  –  Öffentliche API des Frameworks
# ─────────────────────────────────────────────────────────────────────────────
def create(
    app_root:   Path,
    config:     Optional[dict] = None,
    extra_init: Optional[Callable] = None,
) -> Flask:
    """Erstellt und konfiguriert die Flask-Anwendung.

    Args:
        app_root:   Pfad zum app/-Verzeichnis des Projekts.
        config:     Optionales Dict mit Flask-Config-Werten.
        extra_init: Optionaler Hook – wird mit der fertigen Flask-App
                    aufgerufen, um projektspezifische Routen / Extensions
                    zu registrieren.

    Verzeichnis-Konventionen (relativ zu app_root):
        settings.py           – APP_NAME, APP_VERSION, APP_LANG, …
        templates/navigation/ – items.yaml  (und optional items.light.yaml)
        templates/partials/   – Seitenpartials
        routes/__init__.py    – (optional) Flask-Blueprints
        api/__init__.py       – (optional) app-eigene API-Blueprints
        static/               – (optional) überschreibt core/static/

    Template-Auflösung (Priorität high → low):
        1. app/templates/
        2. core/templates/

    Static-Auflösung (Priorität high → low):
        1. app/static/   (via send_static_file-Override)
        2. core/static/  (Flask-Standard-Folder)
    """
    core_static = CORE_ROOT / "static"
    app_static  = app_root / "static"

    # ── Flask-Subklasse: app/static/ überschreibt core/static/ ──────────────
    class _App(Flask):
        def send_static_file(self, filename: str):
            candidate = app_static / filename
            if app_static.exists() and candidate.is_file():
                return send_from_directory(str(app_static), filename)
            return super().send_static_file(filename)

    app = _App(
        __name__,
        static_folder=str(core_static),
        static_url_path="/static",
    )

    # ── Flask-Basiskonfiguration ──────────────────────────────────────────────
    app.config.update(
        DEBUG=True,
        TEMPLATES_AUTO_RELOAD=True,
        SEND_FILE_MAX_AGE_DEFAULT=0,
    )
    if config:
        app.config.update(config)

    # ── Template-Loader: app überschreibt core ───────────────────────────────
    app_templates  = app_root / "templates"
    core_templates = CORE_ROOT / "templates"

    loaders = []
    if app_templates.exists():
        loaders.append(FileSystemLoader(str(app_templates)))
    loaders.append(FileSystemLoader(str(core_templates)))
    app.jinja_env.loader = ChoiceLoader(loaders)

    # ── App-Konfiguration aus settings.py laden ──────────────────────────────
    app_cfg: dict = {}
    for cfg_name in ("settings.py", "config.py"):          # beide Namen erlaubt
        cfg_path = app_root / cfg_name
        if cfg_path.exists():
            mod     = _load_module("app_settings", cfg_path)
            app_cfg = {k: v for k, v in vars(mod).items() if not k.startswith("_")}
            break

    light_mode: bool = app_cfg.get("LIGHT_MODE", False)

    # ── Globale Template-Variablen ────────────────────────────────────────────
    @app.context_processor
    def _inject_globals():
        return {
            "app_name":      app_cfg.get("APP_NAME",     "myapp"),
            "app_version":   app_cfg.get("APP_VERSION",  "0.1.0"),
            "app_logo_svg":  app_cfg.get("APP_LOGO_SVG", None),
            "app_lang":      app_cfg.get("APP_LANG",     "de"),
            "light_mode":    light_mode,
        }

    # ── Navigation laden ──────────────────────────────────────────────────────
    nav_name = "items.light.yaml" if light_mode else "items.yaml"
    nav_yaml = app_root / "templates" / "navigation" / nav_name
    if not nav_yaml.exists():
        raise FileNotFoundError(
            f"Navigation-Config nicht gefunden: {nav_yaml}\n"
            f"Erstelle die Datei oder passe LIGHT_MODE in settings.py an."
        )

    nav_items = load_nav(nav_yaml)

    @app.context_processor
    def _inject_nav():
        return {"nav_items": nav_items}

    # ── Core-Seiten automatisch registrieren ─────────────────────────────────
    register_pages(app, nav_items)

    # ── Optionale App-Blueprints: app/routes/__init__.py ─────────────────────
    routes_init = app_root / "routes" / "__init__.py"
    if routes_init.exists():
        mod = _load_module("app_routes", routes_init)
        if hasattr(mod, "register"):
            mod.register(app)
        elif hasattr(mod, "blueprint"):
            app.register_blueprint(mod.blueprint)

    # ── Optionale API-Blueprints: app/api/__init__.py ─────────────────────────
    api_init = app_root / "api" / "__init__.py"
    if api_init.exists():
        mod = _load_module("app_api", api_init)
        if hasattr(mod, "register"):
            mod.register(app)
        elif hasattr(mod, "blueprint"):
            app.register_blueprint(mod.blueprint, url_prefix="/api")

    # ── Projektspezifischer Hook ───────────────────────────────────────────────
    if extra_init:
        extra_init(app)

    # ── Root-Redirect → erstes/default Nav-Item ───────────────────────────────
    default_item = next(
        (it for it in nav_items if not it.get("separator") and it.get("default")),
        next((it for it in nav_items if not it.get("separator")), None),
    )

    if default_item:
        @app.get("/")
        def _root():
            return redirect(f"/{default_item['key']}")

    return app
