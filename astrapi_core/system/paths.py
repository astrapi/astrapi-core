# core/system/paths.py
"""Zentrale Laufzeit-Pfadverwaltung für astrapi-Anwendungen.

Jede App ruft einmalig beim Start configure(app_name) auf:

    from astrapi_core.system.paths import configure
    configure("astrapi-backup")

Danach stehen work_dir(), db_path() und log_dir() zur Verfügung.
Das Arbeitsverzeichnis wird über einen CLI-Parameter oder eine
Umgebungsvariable gesetzt:

    astrapi-backup --work-dir /opt/astrapi-backup
    # → setzt ASTRAPI_BACKUP_WORK_DIR=/opt/astrapi-backup

Ist weder Parameter noch Env-Variable gesetzt, schlägt work_dir() mit
einem RuntimeError fehl – kein stiller Fallback.
"""
import os
from pathlib import Path

_app_name: str | None = None


def configure(app_name: str) -> None:
    """Setzt den App-Namen. Muss vor work_dir() aufgerufen werden."""
    global _app_name
    _app_name = app_name


def _env_var() -> str:
    """Leitet den Namen der Work-Dir-Variable aus dem App-Namen ab.

    Bindestriche werden zu Unterstrichen: die App-Namen enthalten seit der
    Umbenennung von "backupctl" auf "astrapi-backup" einen Bindestrich, und
    `upper()` allein liesse ihn stehen. Ein solcher Name ist kein gueltiger
    Bezeichner -- die Shell lehnt `NAME-X=wert befehl` ab, systemd verwirft
    ein `Environment=` damit stillschweigend. Nur `env "NAME-X=wert"` haette
    funktioniert (T-128).
    """
    if _app_name is None:
        raise RuntimeError(
            "astrapi_core.system.paths nicht konfiguriert – configure(app_name) aufrufen!"
        )
    return f"{_app_name.upper().replace('-', '_')}_WORK_DIR"


def work_dir() -> Path:
    """Gibt das konfigurierte Arbeitsverzeichnis zurück.

    Liest die Env-Variable {APP_NAME}_WORK_DIR (z.B. ASTRAPI_BACKUP_WORK_DIR).
    Schlägt fehl wenn nicht gesetzt.
    """
    val = os.environ.get(_env_var(), "").strip()
    if not val:
        raise RuntimeError(
            f"{_env_var()} nicht gesetzt. "
            f"Anwendung mit --work-dir /pfad starten."
        )
    return Path(val)


def extra_disk() -> str:
    """Gibt den konfigurierten Zusatzspeicher-Pfad zurück, oder '' wenn nicht
    gesetzt (Einstellungen → Allgemein → "Zusätzlicher Speicher",
    module.system.extra_disks).

    Robust gegen ältere gespeicherte Formate von vor der Vereinfachung auf
    ein einzelnes Textfeld -- Liste (frühere Mehrfach-Eintrags-UI) oder
    kommagetrennter String (noch früheres Format) werden beide auf den
    ersten/einzigen Eintrag reduziert, ohne dass eine Datenmigration nötig
    wäre."""
    from astrapi_core.ui.settings_registry import get_module

    raw = get_module("system", "extra_disks", "") or ""
    if isinstance(raw, list):
        raw = raw[0] if raw else ""
    if isinstance(raw, str):
        raw = raw.split(",")[0].strip()
    return raw or ""


def require_extra_disk() -> str:
    """Wie extra_disk(), bricht aber mit klarer Fehlermeldung ab statt
    still auf '' zurückzufallen -- für Apps, die zwingend einen
    Zusatzspeicher benötigen (mirror, packages, sync)."""
    disk = extra_disk()
    if not disk:
        raise RuntimeError(
            'Kein Zusätzlicher Speicher konfiguriert (Einstellungen → '
            'Allgemein → "Zusätzlicher Speicher") -- diese App benötigt '
            "zwingend einen."
        )
    return disk


def db_path() -> Path:
    return work_dir() / "data" / "app.db"


def log_dir() -> Path:
    return work_dir() / "logs"


def add_work_dir_argument(parser) -> None:
    """Fügt --work-dir als Pflichtargument zu einem argparse.ArgumentParser hinzu
    und setzt nach dem Parsen die Env-Variable.

    Verwendung in _cli.py:

        from astrapi_core.system.paths import add_work_dir_argument
        add_work_dir_argument(parser)
        args = parser.parse_args()
        # ASTRAPI_BACKUP_WORK_DIR ist jetzt gesetzt
    """
    parser.add_argument(
        "--work-dir",
        required=True,
        help="Arbeitsverzeichnis mit data/ und logs/",
    )


def apply_work_dir_argument(args, app_name: str) -> None:
    """Konfiguriert app_name und setzt die Env-Variable aus dem argparse-Namespace."""
    configure(app_name)
    os.environ[_env_var()] = args.work_dir


_debug: bool = False
_ui_debug: bool = False
_admin_prefix: str = ""


def add_debug_argument(parser) -> None:
    """Fügt --debug als optionales Flag zu einem argparse.ArgumentParser hinzu."""
    parser.add_argument(
        "--debug",
        action="store_true",
        default=False,
        help="Debug-Modus aktivieren",
    )


def apply_debug_argument(args) -> None:
    """Übernimmt args.debug in den globalen Debug-Zustand und setzt ASTRAPI_DEBUG."""
    global _debug
    _debug = bool(args.debug)
    if _debug:
        import os
        os.environ["ASTRAPI_DEBUG"] = "1"


def is_debug() -> bool:
    """Gibt True zurück wenn die App mit --debug gestartet wurde."""
    import os
    return _debug or os.environ.get("ASTRAPI_DEBUG") == "1"


def is_ui_debug() -> bool:
    """Gibt True zurück wenn die App mit --ui-debug gestartet wurde."""
    import os
    return _ui_debug or os.environ.get("ASTRAPI_UI_DEBUG") == "1"


def set_admin_prefix(prefix: str) -> None:
    """Setzt den URL-Prefix, unter dem das Dashboard extern erreichbar ist.

    Default "" (Dashboard liegt auf der Wurzel, unveraendertes Verhalten
    fuer astrapi-backup/astrapi-admin). Apps wie astrapi-mirror/-packages/
    -sync, die echte Inhalte direkt auf "/" ausliefern und das Dashboard
    stattdessen z.B. per Caddy unter "/admin" reverse-proxien (Praefix
    dort abgeschnitten, App-Routen selbst bleiben unveraendert bei "/"),
    setzen hier "/admin" -- wird nur fuer sichtbare Browser-URLs gebraucht
    (Nav-Links/hx-push-url, siehe Module.nav_url), NICHT fuer die
    tatsaechliche Routenregistrierung, die bleibt unpraefixiert, weil
    Caddy den Praefix vor der Weiterleitung schon entfernt. Muss vor
    load_modules() gesetzt werden (Module._base.py::__post_init__ liest
    das beim Modul-Objekt-Bau)."""
    global _admin_prefix
    _admin_prefix = prefix.rstrip("/") if prefix else ""


def admin_prefix() -> str:
    """Aktueller Dashboard-URL-Prefix (leerer String = Wurzel, Normalfall)."""
    return _admin_prefix


def run_app(app: str, app_name: str, default_port: int = 5000) -> None:
    """Standardisierter CLI-Einstiegspunkt für astrapi-Apps.

    Parst --host, --port, --debug, --reload und --work-dir, konfiguriert
    Pfade und startet uvicorn.

    --debug und --reload sind bewusst getrennte Schalter (vorher hing
    Reload komplett an --debug): --debug markiert nur noch die Instanz
    als Dev/Debug (Titel-Suffix "- dev", Debug-Routen, kein automatischer
    Uvicorn-Reload mehr). Reload watcht ohne explizites reload_dirs das
    aktuelle Arbeitsverzeichnis -- auf einem Dev-LXC ohne WorkingDirectory=
    in der systemd-Unit ist das "/" und beobachtet damit faktisch das
    gesamte Dateisystem (100%-CPU-Vorfall auf sync-dev, 2026-09-07). Bei
    einem über astrapi-admin/Claude gedeployten Dev-Server folgt ohnehin
    immer ein expliziter `systemctl restart` nach jedem Deploy -- Reload
    bringt dort keinen Nutzen, nur das Risiko. Für lokale Testinstanzen
    (E-002, systemd --user) bleibt Reload weiterhin sinnvoll und muss dort
    explizit per --reload zusätzlich zu --debug gesetzt werden.

    Verwendung in _cli.py::

        from astrapi_core.system.paths import run_app
        run_app("astrapi_backup._app:app", "astrapi-backup", default_port=5001)
    """
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(prog=app_name)
    parser.add_argument("--port", type=int, default=default_port)
    parser.add_argument("--host", default="0.0.0.0")
    add_debug_argument(parser)
    parser.add_argument(
        "--reload",
        action="store_true",
        default=False,
        help="Uvicorn-Autoreload bei Dateiänderungen (unabhängig von --debug)",
    )
    parser.add_argument(
        "--ui-debug",
        action="store_true",
        default=False,
        help="UI-Debug-Modus: Flächen einfärben und Rahmen sichtbar machen",
    )
    parser.add_argument(
        "--secret-key-path",
        default=None,
        help="Pfad zum Fernet-Key (außerhalb des Work-Dir, z.B. /var/lib/backupadm/secret.key)",
    )
    add_work_dir_argument(parser)
    args = parser.parse_args()
    apply_work_dir_argument(args, app_name)
    apply_debug_argument(args)

    global _ui_debug
    _ui_debug = bool(args.ui_debug)
    if _ui_debug:
        import os as _os
        _os.environ["ASTRAPI_UI_DEBUG"] = "1"

    if args.secret_key_path:
        os.environ["ASTRAPI_SECRET_KEY_PATH"] = args.secret_key_path

    uvicorn.run(app, host=args.host, port=args.port, reload=args.reload)
