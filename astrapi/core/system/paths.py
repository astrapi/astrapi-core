# core/system/paths.py
"""Zentrale Laufzeit-Pfadverwaltung für astrapi-Anwendungen.

Jede App ruft einmalig beim Start configure(app_name) auf:

    from astrapi.core.system.paths import configure
    configure("backupctl")

Danach stehen work_dir(), db_path() und log_dir() zur Verfügung.
Das Arbeitsverzeichnis wird über einen CLI-Parameter oder eine
Umgebungsvariable gesetzt:

    backupctl --work-dir /opt/backupctl
    # → setzt BACKUPCTL_WORK_DIR=/opt/backupctl

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
    if _app_name is None:
        raise RuntimeError(
            "astrapi.core.system.paths nicht konfiguriert – configure(app_name) aufrufen!"
        )
    return f"{_app_name.upper()}_WORK_DIR"


def work_dir() -> Path:
    """Gibt das konfigurierte Arbeitsverzeichnis zurück.

    Liest die Env-Variable {APP_NAME}_WORK_DIR (z.B. BACKUPCTL_WORK_DIR).
    Schlägt fehl wenn nicht gesetzt.
    """
    val = os.environ.get(_env_var(), "").strip()
    if not val:
        raise RuntimeError(
            f"{_env_var()} nicht gesetzt. "
            f"Anwendung mit --work-dir /pfad starten."
        )
    return Path(val)


def db_path() -> Path:
    return work_dir() / "data" / "app.db"


def log_dir() -> Path:
    return work_dir() / "logs"


def add_work_dir_argument(parser) -> None:
    """Fügt --work-dir als Pflichtargument zu einem argparse.ArgumentParser hinzu
    und setzt nach dem Parsen die Env-Variable.

    Verwendung in _cli.py:

        from astrapi.core.system.paths import add_work_dir_argument
        add_work_dir_argument(parser)
        args = parser.parse_args()
        # BACKUPCTL_WORK_DIR ist jetzt gesetzt
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


def run_app(app: str, app_name: str, default_port: int = 5000) -> None:
    """Standardisierter CLI-Einstiegspunkt für astrapi-Apps.

    Parst --host, --port, --debug und --work-dir, konfiguriert Pfade
    und startet uvicorn. --debug aktiviert automatisch den Reload-Modus.

    Verwendung in _cli.py::

        from astrapi.core.system.paths import run_app
        run_app("astrapi_backup._app:app", "astrapi-backup", default_port=5001)
    """
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(prog=app_name)
    parser.add_argument("--port", type=int, default=default_port)
    parser.add_argument("--host", default="0.0.0.0")
    add_debug_argument(parser)
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

    uvicorn.run(app, host=args.host, port=args.port, reload=args.debug)
