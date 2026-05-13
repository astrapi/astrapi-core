# core/modules/system/engine.py
"""Systeminfo-Datensammlung und Update-Engine für das Core-System-Modul.

Projekte können optional projektspezifische Extras und Services konfigurieren:

    from astrapi_core.modules.system.engine import configure, configure_updater

    configure(
        services=["myapp", "nginx"],
        extra_info_fn=lambda: {"Version": "1.2.3", "DB": "4 MB"},
    )
    configure_updater(app_root=Path("/opt/myapp"))
"""

import subprocess
import sys
import time
from datetime import datetime

_START_TIME: float = time.time()
_services: list[str] = []
_extra_info_fn = None
_extra_disks: list[str] = []
_update_packages_fn = None

_cache: dict = {}
_cache_ts: float = 0.0
_CACHE_TTL: float = 2.0


def configure(
    services: list[str] = None,
    extra_info_fn=None,
    extra_disks: list[str] = None,
    update_packages_fn=None,
) -> None:
    """Konfiguriert projektspezifische Erweiterungen.

    Args:
        services:           Liste von systemd-Service-Namen die angezeigt werden sollen.
        extra_info_fn:      Callable () → dict[str, str] mit zusätzlichen Infozeilen.
        extra_disks:        Liste von Mountpoints die als zusätzliche Gauge-Karten angezeigt werden.
        update_packages_fn: Callable () → list[dict] mit Paket-Versionsdaten (name, installed, latest, update_available).
    """
    global _services, _extra_info_fn, _extra_disks, _update_packages_fn
    _services = services or []
    _extra_info_fn = extra_info_fn
    _extra_disks = extra_disks or []
    _update_packages_fn = update_packages_fn


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────


def _run(cmd: list, timeout: int = 5) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception:
        return ""


from astrapi_core.system.format import fmt_bytes as _fmt_size


def _fmt_uptime(seconds: float) -> str:
    s = int(seconds)
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m, _ = divmod(s, 60)
    parts = []
    if d:
        parts.append(f"{d}d")
    if h:
        parts.append(f"{h}h")
    if m:
        parts.append(f"{m}m")
    return " ".join(parts) or "< 1m"


def _disk_usage() -> list:
    try:
        import psutil

        disks = []
        for part in psutil.disk_partitions():
            if part.fstype in ("tmpfs", "devtmpfs", "squashfs", "overlay", "proc", "sysfs"):
                continue
            try:
                usage = psutil.disk_usage(part.mountpoint)
                disks.append(
                    {
                        "device": part.device,
                        "mountpoint": part.mountpoint,
                        "fstype": part.fstype,
                        "total_fmt": _fmt_size(usage.total),
                        "used_fmt": _fmt_size(usage.used),
                        "free_fmt": _fmt_size(usage.free),
                        "percent": usage.percent,
                    }
                )
            except (PermissionError, OSError):
                continue
        return disks
    except Exception:
        return []


def _net_interfaces() -> list:
    try:
        import psutil

        ifaces = []
        stats = psutil.net_if_stats()
        addrs = psutil.net_if_addrs()
        for name, addr_list in addrs.items():
            if name == "lo":
                continue
            ipv4 = [a.address for a in addr_list if a.family.name == "AF_INET"]
            ipv6 = [a.address.split("%")[0] for a in addr_list if a.family.name == "AF_INET6"]
            st = stats.get(name)
            ifaces.append(
                {
                    "name": name,
                    "ipv4": ipv4,
                    "ipv6": ipv6,
                    "up": st.isup if st else False,
                    "speed": f"{st.speed} Mbit/s" if st and st.speed else "—",
                }
            )
        return ifaces
    except Exception:
        return []


def _systemd_service(name: str) -> dict:
    status = _run(["systemctl", "is-active", name])
    enabled = _run(["systemctl", "is-enabled", name])
    desc = ""
    out = _run(["systemctl", "show", name, "--property=Description"])
    if "=" in out:
        desc = out.split("=", 1)[1]
    return {
        "name": name,
        "active": status,
        "enabled": enabled,
        "desc": desc,
        "ok": status == "active",
    }


# ── Datensammlung ─────────────────────────────────────────────────────────────


def collect() -> dict:
    """Sammelt alle Systemdaten (ohne Cache)."""
    try:
        import psutil
    except ImportError:
        return {"ok": False, "error": "psutil nicht installiert (pip install psutil)"}

    try:
        cpu_pct = psutil.cpu_percent(interval=0.3)
        cpu_count = psutil.cpu_count(logical=True)
        cpu_freq = psutil.cpu_freq()
        cpu_model = ""
        try:
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if line.startswith("model name"):
                        cpu_model = line.split(":", 1)[1].strip()
                        break
        except Exception:
            pass

        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        boot = psutil.boot_time()

        hostname = _run(["hostname", "-f"]) or _run(["hostname"]) or "?"
        kernel = _run(["uname", "-r"])
        try:
            import platform

            os_name = platform.platform()
        except Exception:
            os_name = "?"

        import getpass
        import os as _os

        try:
            current_user = getpass.getuser()
        except Exception:
            current_user = "?"
        cwd = _os.getcwd()

        services = [_systemd_service(s) for s in _services]
        extra_info = _extra_info_fn() if _extra_info_fn else {}

        updater = None
        if _update_packages_fn:
            try:
                st = get_status()
                updater = {
                    "status": st["status"],
                    "last_checked": st["last_checked"],
                    "error": st["error"],
                    "packages": st["packages"] or _update_packages_fn(),
                }
            except Exception:
                updater = {"status": "idle", "last_checked": None, "error": None, "packages": []}

        procs = []
        for p in sorted(
            psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]),
            key=lambda p: p.info["cpu_percent"] or 0,
            reverse=True,
        )[:8]:
            procs.append(p.info)

        root_disk = None
        try:
            _rd = psutil.disk_usage("/")
            root_disk = {
                "mountpoint": "/",
                "total_fmt": _fmt_size(_rd.total),
                "used_fmt": _fmt_size(_rd.used),
                "free_fmt": _fmt_size(_rd.free),
                "percent": _rd.percent,
            }
        except Exception:
            pass

        extra_disks_data = []
        for mp in _extra_disks:
            try:
                _d = psutil.disk_usage(mp)
                extra_disks_data.append(
                    {
                        "mountpoint": mp,
                        "label": mp.lstrip("/").upper() or mp,
                        "total_fmt": _fmt_size(_d.total),
                        "used_fmt": _fmt_size(_d.used),
                        "free_fmt": _fmt_size(_d.free),
                        "percent": _d.percent,
                    }
                )
            except Exception:
                pass

        return {
            "ok": True,
            "collected_at": datetime.now().strftime("%H:%M:%S"),
            "cpu": {
                "percent": cpu_pct,
                "cores": cpu_count,
                "freq": f"{cpu_freq.current:.0f} MHz" if cpu_freq else "—",
                "model": cpu_model,
            },
            "mem": {
                "percent": mem.percent,
                "total": _fmt_size(mem.total),
                "used": _fmt_size(mem.used),
                "free": _fmt_size(mem.available),
            },
            "swap": {
                "percent": swap.percent,
                "total": _fmt_size(swap.total),
                "used": _fmt_size(swap.used),
            },
            "system": {
                "hostname": hostname,
                "kernel": kernel,
                "os_name": os_name,
                "sys_uptime": _fmt_uptime(time.time() - boot),
                "app_uptime": _fmt_uptime(time.time() - _START_TIME),
                "user": current_user,
                "cwd": cwd,
            },
            "software": {
                "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
                "psutil": psutil.__version__,
                **extra_info,
            },
            "root_disk": root_disk,
            "extra_disks": extra_disks_data,
            "disks": _disk_usage(),
            "interfaces": _net_interfaces(),
            "services": services,
            "processes": procs,
            "updater": updater,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def collect_cached() -> dict:
    global _cache, _cache_ts
    if time.monotonic() - _cache_ts >= _CACHE_TTL:
        _cache = collect()
        _cache_ts = time.monotonic()
    return _cache


# ── Updater ───────────────────────────────────────────────────────────────────
# (ehemals updater.py – Update-Engine: pip-Upgrade für App + astrapi-core,
#  dann Self-Restart via os.execv)

import logging as _logging
import threading as _threading
from pathlib import Path as _Path

_upd_log = _logging.getLogger(__name__)

_app_root: "_Path | None" = None
_app_package: "str | None" = None

_upd_state: dict = {
    "status": "idle",  # idle | checking | running | done | error
    "log_id": None,
    "last_checked": None,
    "packages": [],
    "error": None,
}
_upd_lock = _threading.Lock()

_INDEX_URL = "https://gitlab.com/api/v4/projects/81004951/packages/pypi/simple"


def configure_updater(app_root: "_Path") -> None:
    """Konfiguriert die Update-Engine. Wird von der App beim Start aufgerufen.

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


def _pip_index_args() -> list:
    return ["--index-url", _INDEX_URL] if _INDEX_URL else []


def _packages_to_update() -> list:
    pkgs = ["astrapi-core"]
    if _app_package:
        pkgs.append(_app_package)
    return pkgs


def _packages_to_display() -> list:
    return [p for p in _packages_to_update() if p != "astrapi-core"]


def _installed_version(package: str) -> str:
    try:
        from importlib.metadata import version

        return version(package)
    except Exception:
        return "—"


def _latest_version(package: str) -> "str | None":
    import re
    import urllib.error
    import urllib.request

    if not _INDEX_URL:
        return None

    pkg_url = f"{_INDEX_URL.rstrip('/')}/{package}/"
    req = urllib.request.Request(pkg_url)
    _upd_log.debug("updater: GET %s", pkg_url)

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        _upd_log.warning("updater: HTTP %s für %s", e.code, pkg_url)
        if e.code == 404:
            return None
        raise
    except Exception as e:
        _upd_log.warning("updater: Fehler beim Abrufen von %s: %s", pkg_url, e)
        return None

    pkg_norm = package.lower().replace("-", "_")
    filenames = re.findall(r">([^<]+\.(?:whl|tar\.gz))<", html)
    versions = []
    for filename in filenames:
        fn_norm = filename.lower().replace("-", "_")
        if fn_norm.startswith(pkg_norm + "_"):
            rest = filename[len(pkg_norm) + 1 :]
            ver = re.split(r"[-.](?:py\d|cp\d|tar|whl)", rest)[0]
            if ver and re.match(r"^\d", ver):
                versions.append(ver)

    if not versions:
        return None

    try:
        from packaging.version import Version

        versions.sort(key=Version, reverse=True)
    except Exception:
        versions.sort(reverse=True)

    return versions[0]


def check_updates() -> list:
    """Prüft synchron via Simple-Index, ob Updates verfügbar sind."""
    with _upd_lock:
        _upd_state["status"] = "checking"

    packages = []
    for pip_name in _packages_to_display():
        installed = _installed_version(pip_name)
        error = None
        try:
            latest = _latest_version(pip_name)
        except Exception as e:
            latest = None
            error = str(e)

        if latest is None:
            update_available = False
            latest_display = "—"
        else:
            latest_display = latest
            try:
                from packaging.version import Version

                update_available = Version(latest) > Version(installed)
            except Exception:
                update_available = latest != installed

        packages.append(
            {
                "name": pip_name,
                "pip_name": pip_name,
                "installed": installed,
                "latest": latest_display,
                "update_available": update_available,
                "error": error,
            }
        )

    with _upd_lock:
        _upd_state["packages"] = packages
        _upd_state["last_checked"] = datetime.now().strftime("%d.%m.%Y %H:%M")
        _upd_state["status"] = "idle"

    return packages


def run_update() -> bool:
    """Startet den Update-Prozess in einem Hintergrund-Thread."""
    with _upd_lock:
        if _upd_state["status"] in ("running", "checking"):
            return False
        _upd_state["status"] = "running"
        _upd_state["error"] = None
        _upd_state["log_id"] = None

    _threading.Thread(target=_do_update, daemon=True, name="system-updater-thread").start()
    return True


def _do_update() -> None:
    import subprocess as _subprocess

    from astrapi_core.system.activity_log import log_activity, update_activity_log
    from astrapi_core.system.logger import (
        clear_active_log_id,
        clear_tee_context,
        set_active_log_id,
        set_tee_context,
    )

    pkgs = _packages_to_update()
    log_id = log_activity(
        log_type="system",
        module="system",
        item_id="update",
        description=f"Update: {', '.join(pkgs)}",
        status="running",
        started_at=datetime.now().isoformat(),
    )

    with _upd_lock:
        _upd_state["log_id"] = log_id

    set_tee_context("system", "update")
    set_active_log_id(log_id)

    try:
        cmd = [sys.executable, "-m", "pip", "install", "--upgrade"] + pkgs + _pip_index_args()
        proc = _subprocess.Popen(
            cmd,
            stdout=_subprocess.PIPE,
            stderr=_subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        import logging as _l

        _ul = _l.getLogger(__name__)
        for line in proc.stdout:
            _ul.info(line.rstrip())

        proc.wait()

        if proc.returncode == 0:
            update_activity_log(log_id, status="ok")
            with _upd_lock:
                _upd_state["status"] = "done"
                _upd_state["packages"] = []
            _schedule_restart()
        else:
            update_activity_log(
                log_id,
                status="error",
                error_message=f"pip exit code {proc.returncode}",
            )
            with _upd_lock:
                _upd_state["status"] = "error"
                _upd_state["error"] = f"pip fehlgeschlagen (exit code {proc.returncode})"

    except Exception as e:
        err = str(e)
        try:
            update_activity_log(log_id, status="error", error_message=err)
        except Exception:
            pass
        with _upd_lock:
            _upd_state["status"] = "error"
            _upd_state["error"] = err
    finally:
        clear_active_log_id()
        clear_tee_context()


def _schedule_restart() -> None:
    import os

    _threading.Timer(2.0, lambda: os.execv(sys.executable, [sys.executable] + sys.argv)).start()


def get_status() -> dict:
    """Gibt den aktuellen Updater-Status zurück."""
    with _upd_lock:
        return {
            "status": _upd_state["status"],
            "log_id": _upd_state["log_id"],
            "last_checked": _upd_state["last_checked"],
            "packages": list(_upd_state["packages"]),
            "error": _upd_state["error"],
        }


def get_packages_with_versions() -> list:
    """Gibt die Paket-Liste zurück; füllt 'installed' ohne Netzwerkzugriff auf."""
    with _upd_lock:
        cached = list(_upd_state["packages"])

    if cached:
        return cached

    return [
        {
            "name": p,
            "pip_name": p,
            "installed": _installed_version(p),
            "latest": "—",
            "update_available": False,
            "error": None,
        }
        for p in _packages_to_display()
    ]
