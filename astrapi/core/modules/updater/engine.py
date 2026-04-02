# core/modules/updater/engine.py
"""Update-Engine: pip-Upgrade für App + astrapi-core, dann Self-Restart."""
import logging
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

_log = logging.getLogger(__name__)

_app_root: Path | None = None
_app_package: str | None = None

_state: dict = {
    "status":       "idle",   # idle | checking | running | done | error
    "log_id":       None,
    "last_checked": None,
    "packages":     [],       # [{name, pip_name, installed, latest, update_available}]
    "output":       [],       # Ausgabe-Zeilen des laufenden pip-Prozesses
    "error":        None,
}
_lock = threading.Lock()


# ── Konfiguration ─────────────────────────────────────────────────────────────

def configure(app_root: Path) -> None:
    """Wird von der App beim Start aufgerufen.

    Args:
        app_root: Verzeichnis der App (enthält app.yaml).
    """
    global _app_root, _app_package
    _app_root = app_root
    try:
        import yaml
        app_yaml = app_root / "app.yaml"
        if app_yaml.exists():
            with open(app_yaml, encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            _app_package = cfg.get("name") or None
    except Exception:
        pass


# ── Settings-Helpers ──────────────────────────────────────────────────────────

_INDEX_URL = "https://gitlab.com/api/v4/groups/astrapi-os%2Fctl/-/packages/pypi/simple"


def _index_url() -> str:
    return _INDEX_URL


def _index_token() -> str:
    try:
        from astrapi.core.system.secrets import get_secret_safe
        return get_secret_safe("module.updater.index_token") or ""
    except Exception:
        return ""


def _pip_index_args() -> list[str]:
    url   = _index_url()
    token = _index_token()
    if not url:
        return []
    if token:
        from urllib.parse import urlparse, urlunparse
        p        = urlparse(url)
        auth_url = urlunparse(p._replace(netloc=f"__token__:{token}@{p.netloc}"))
    else:
        auth_url = url
    return ["--index-url", auth_url]


def _packages_to_update() -> list[str]:
    pkgs = ["astrapi-core"]
    if _app_package:
        pkgs.append(_app_package)
    return pkgs


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def _installed_version(package: str) -> str:
    try:
        from importlib.metadata import version
        return version(package)
    except Exception:
        return "—"


def _latest_version(package: str) -> str | None:
    """Fragt den Simple-Index nach der neuesten Version ab.

    Gibt None zurück wenn die Abfrage fehlschlägt.
    """
    import urllib.request
    import urllib.error
    import re

    url   = _index_url().rstrip("/")
    token = _index_token()
    if not url:
        return None

    pkg_url = f"{url}/{package}/"
    req     = urllib.request.Request(pkg_url)
    if token:
        req.add_header("Private-Token", token)
    _log.debug("updater: GET %s (token=%s)", pkg_url, "ja" if token else "nein")

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        _log.warning("updater: HTTP %s für %s", e.code, pkg_url)
        if e.code == 404:
            return None
        raise
    except Exception as e:
        _log.warning("updater: Fehler beim Abrufen von %s: %s", pkg_url, e)
        return None

    # Link-Texte: ">astrapi_core-26.4.2-py3-none-any.whl<"
    pkg_norm  = package.lower().replace("-", "_")
    filenames = re.findall(r'>([^<]+\.(?:whl|tar\.gz))<', html)
    _log.debug("updater: %d Dateien im Index für %s", len(filenames), package)

    versions = []
    for filename in filenames:
        fn_norm = filename.lower().replace("-", "_")
        if fn_norm.startswith(pkg_norm + "_"):
            rest = filename[len(pkg_norm) + 1:]   # "26.4.2-py3-none-any.whl"
            ver  = re.split(r'[-.](?:py\d|cp\d|tar|whl)', rest)[0]
            _log.debug("updater:   %s → rest=%r ver=%r", filename, rest, ver)
            if ver and re.match(r'^\d', ver):
                versions.append(ver)

    _log.debug("updater: gefundene Versionen für %s: %s", package, versions)
    if not versions:
        return None

    try:
        from packaging.version import Version
        versions.sort(key=Version, reverse=True)
    except Exception:
        versions.sort(reverse=True)

    return versions[0]


# ── Versionscheck ─────────────────────────────────────────────────────────────

def check_updates() -> list[dict]:
    """Prüft synchron via Simple-Index, ob Updates verfügbar sind."""
    with _lock:
        _state["status"] = "checking"

    packages = []
    for pip_name in _packages_to_update():
        installed = _installed_version(pip_name)
        error     = None
        try:
            latest = _latest_version(pip_name)
        except Exception as e:
            latest = None
            error  = str(e)

        if latest is None:
            update_available = False
            latest_display   = "—"
        else:
            latest_display = latest
            try:
                from packaging.version import Version
                update_available = Version(latest) > Version(installed)
            except Exception:
                update_available = latest != installed

        packages.append({
            "name":             pip_name,
            "pip_name":         pip_name,
            "installed":        installed,
            "latest":           latest_display,
            "update_available": update_available,
            "error":            error,
        })

    with _lock:
        _state["packages"]     = packages
        _state["last_checked"] = datetime.now().strftime("%d.%m.%Y %H:%M")
        _state["status"]       = "idle"

    return packages


# ── Update ────────────────────────────────────────────────────────────────────

def run_update() -> bool:
    """Startet den Update-Prozess in einem Hintergrund-Thread."""
    with _lock:
        if _state["status"] in ("running", "checking"):
            return False
        _state["status"] = "running"
        _state["output"] = []
        _state["error"]  = None
        _state["log_id"] = None

    threading.Thread(target=_do_update, daemon=True, name="updater-thread").start()
    return True


def _do_update() -> None:
    from astrapi.core.system.activity_log import log_activity, update_activity_log

    pkgs   = _packages_to_update()
    log_id = log_activity(
        log_type    = "system",
        module      = "updater",
        description = f"Update: {', '.join(pkgs)}",
        status      = "running",
        started_at  = datetime.now().isoformat(),
    )

    with _lock:
        _state["log_id"] = log_id

    try:
        cmd  = [sys.executable, "-m", "pip", "install", "--upgrade"] + pkgs + _pip_index_args()
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        output_lines: list[str] = []
        for line in proc.stdout:
            line = line.rstrip()
            output_lines.append(line)
            with _lock:
                _state["output"].append(line)

        proc.wait()
        full_log = "\n".join(output_lines)

        if proc.returncode == 0:
            update_activity_log(log_id, status="ok", full_log=full_log)
            with _lock:
                _state["status"]   = "done"
                _state["packages"] = []
            _schedule_restart()
        else:
            update_activity_log(
                log_id,
                status        = "error",
                full_log      = full_log,
                error_message = f"pip exit code {proc.returncode}",
            )
            with _lock:
                _state["status"] = "error"
                _state["error"]  = f"pip fehlgeschlagen (exit code {proc.returncode})"

    except Exception as e:
        err = str(e)
        try:
            update_activity_log(log_id, status="error", error_message=err)
        except Exception:
            pass
        with _lock:
            _state["status"] = "error"
            _state["error"]  = err


def _schedule_restart() -> None:
    import os
    threading.Timer(2.0, lambda: os.execv(sys.executable, [sys.executable] + sys.argv)).start()


# ── Status ────────────────────────────────────────────────────────────────────

def get_status() -> dict:
    with _lock:
        return {
            "status":       _state["status"],
            "log_id":       _state["log_id"],
            "last_checked": _state["last_checked"],
            "packages":     list(_state["packages"]),
            "output":       list(_state["output"]),
            "error":        _state["error"],
        }


def get_packages_with_versions() -> list[dict]:
    """Gibt die Paket-Liste zurück; füllt 'installed' ohne Netzwerkzugriff auf."""
    with _lock:
        cached = list(_state["packages"])

    if cached:
        return cached

    return [
        {
            "name":             p,
            "pip_name":         p,
            "installed":        _installed_version(p),
            "latest":           "—",
            "update_available": False,
            "error":            None,
        }
        for p in _packages_to_update()
    ]
