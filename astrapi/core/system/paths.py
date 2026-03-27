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


def apply_work_dir_argument(args) -> None:
    """Setzt die Env-Variable aus dem geparsten argparse-Namespace."""
    os.environ[_env_var()] = args.work_dir
