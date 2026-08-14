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

_COLLECT_TIMEOUT = 20.0


def collect() -> dict:
    """Sammelt alle Systemdaten (ohne Cache), mit Timeout-Schutz.

    _collect_uncapped() läuft synchron in einem eigenen Thread: hostname/uname
    haben zwar über _run() bereits ein Timeout, `open("/proc/cpuinfo")` und vor
    allem psutil.disk_usage() auf den (seit T-109 frei konfigurierbaren)
    extra_disks-Mountpoints nicht - ein haengendes NFS-Mount dort wuerde sonst
    den Request-Handler unbegrenzt blockieren. Der Thread selbst kann dabei
    nicht abgebrochen werden (uninterruptible I/O), laeuft als Daemon-Thread
    aber harmlos im Hintergrund weiter, statt die Antwort zu verzoegern.

    Stoesst keinen Update-Check an - das passiert ausschliesslich explizit
    über den "Update prüfen"-Button (check_updates()), nicht bei jedem
    Seitenaufruf.
    """
    result: dict = {}
    done = _threading.Event()

    def _work():
        result["data"] = _collect_uncapped()
        done.set()

    _threading.Thread(target=_work, daemon=True, name="system-collect").start()
    if not done.wait(timeout=_COLLECT_TIMEOUT):
        return {
            "ok": False,
            "error": f"Sammeln der Systemdaten dauert länger als {_COLLECT_TIMEOUT:.0f}s "
            "– evtl. ein hängender Mount unter den zusätzlichen Festplatten.",
        }
    return result["data"]


def _collect_uncapped() -> dict:
    """Eigentliche Datensammlung, siehe collect() für den Timeout-Schutz."""
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

        os_pretty = "?"
        try:
            with open("/etc/os-release", encoding="utf-8") as _f:
                for _line in _f:
                    if _line.startswith("PRETTY_NAME="):
                        os_pretty = _line.split("=", 1)[1].strip().strip('"')
                        break
        except Exception:
            os_pretty = os_name

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
        try:
            st = get_status()
            packages = st["packages"]
            if not packages:
                packages = _update_packages_fn() if _update_packages_fn else get_packages_with_versions()
            updater = {
                "status": st["status"],
                "last_checked": st["last_checked"],
                "error": st["error"],
                "packages": packages,
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

        disk_paths = list(_extra_disks)
        try:
            from astrapi_core.ui.settings_registry import get_module as _get_module

            _extra = _get_module("system", "extra_disks", [])
            if isinstance(_extra, str):
                # Alte Werte aus der Zeit vor T-109 (type: text, kommagetrennt).
                # Nicht migriert, wie bei aehnlichen Faellen ueblich - hier
                # nur defensiv gelesen, statt bei jedem Zeichen der Zeichenkette
                # einzeln nachzusehen.
                _extra = [p.strip() for p in _extra.split(",") if p.strip()]
            for _p in _extra:
                _p = _p.strip()
                if _p and _p not in disk_paths:
                    disk_paths.append(_p)
        except Exception:
            pass

        extra_disks_data = []
        for mp in disk_paths:
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
                "os_pretty": os_pretty,
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
    "status": "idle",  # idle | checking | running | done | warning | error
    "log_id": None,
    "last_checked": None,
    "packages": [],
    "error": None,
    # Was der letzte Lauf tatsaechlich veraendert hat, z.B.
    # [{"name": "astrapi-core", "from": "26.8.3", "to": "26.8.4"}].
    # Die UI liest das vor dem Neustart aus und meldet es danach.
    "changed": [],
    # Ob ein Client den "done"-Status schon abgeholt hat - Kriterium fuer
    # _schedule_restart(), siehe dort.
    "seen": True,
}
_upd_lock = _threading.Lock()

_PYPI_SIMPLE = "https://pypi.org/simple"


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


def _packages_to_update() -> list:
    pkgs = []
    if _app_package:
        pkgs.append(_app_package)
    pkgs.append("astrapi-core")
    return pkgs


def _packages_to_display() -> list:
    """Alle direkten Abhängigkeiten des App-Pakets für die Anzeige."""
    import re
    from importlib.metadata import requires as pkg_requires

    seen: set[str] = set()
    pkgs: list[str] = []

    def _add(name: str) -> None:
        key = name.lower().replace("-", "_")
        if key not in seen:
            seen.add(key)
            pkgs.append(name)

    rest: list[str] = []

    if _app_package:
        _add(_app_package)
        try:
            for req in pkg_requires(_app_package) or []:
                if "; extra ==" in req:
                    continue
                name = re.split(r"[\[;>=<!@\s]", req)[0].strip()
                if name and name.lower().replace("-", "_") not in seen:
                    rest.append(name)
        except Exception:
            pass

    _add("astrapi-core")
    for name in sorted(rest, key=lambda n: n.lower()):
        _add(name)
    return pkgs


def _installed_version(package: str) -> str:
    try:
        from importlib.metadata import version

        return version(package)
    except Exception:
        return "—"


def _latest_version(package: str) -> "str | None":
    import json
    import urllib.error
    import urllib.request

    url = f"https://pypi.org/pypi/{package}/json"
    _upd_log.debug("updater: GET %s", url)
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read())
        return data["info"]["version"]
    except urllib.error.HTTPError as e:
        _upd_log.warning("updater: HTTP %s für %s", e.code, url)
        if e.code == 404:
            return None
        raise
    except Exception as e:
        _upd_log.warning("updater: Fehler beim Abrufen von %s: %s", url, e)
        return None


def check_updates() -> bool:
    """Startet die Update-Pruefung in einem Hintergrund-Thread.

    Gibt False zurueck, wenn bereits eine Pruefung oder ein Update laeuft
    (analog run_update()) - vorher lief die Pruefung synchron im
    Request-Handler und blockierte ihn bis zu 14x15s lang.
    """
    with _upd_lock:
        if _upd_state["status"] in ("running", "checking"):
            return False
        _upd_state["status"] = "checking"

    _threading.Thread(target=_do_check_updates, daemon=True, name="system-check-thread").start()
    return True


def _do_check_updates() -> None:
    """Eigentliche Update-Pruefung, siehe check_updates() fuer den Thread-Start."""
    packages = []
    # try/finally: bleibt der Status auf "checking" haengen, lehnt run_update()
    # danach jeden Update-Start stillschweigend ab.
    try:
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
                if installed == "—":
                    update_available = True
                else:
                    try:
                        from packaging.version import Version

                        update_available = Version(latest) > Version(installed)
                    except Exception as e:
                        update_available = False
                        _upd_log.warning(
                            "updater: Versionsvergleich %s (%s vs. %s) fehlgeschlagen: %s",
                            pip_name, installed, latest, e,
                        )

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
    except Exception as e:
        _upd_log.warning("updater: Update-Pruefung fehlgeschlagen: %s", e)
        with _upd_lock:
            _upd_state["error"] = f"Update-Prüfung fehlgeschlagen: {e}"
    finally:
        with _upd_lock:
            _upd_state["status"] = "idle"


def run_update() -> bool:
    """Startet den Update-Prozess in einem Hintergrund-Thread."""
    with _upd_lock:
        if _upd_state["status"] in ("running", "checking"):
            return False
        _upd_state["status"] = "running"
        _upd_state["error"] = None
        _upd_state["log_id"] = None
        _upd_state["changed"] = []

    _threading.Thread(target=_do_update, daemon=True, name="system-updater-thread").start()
    return True


def _installed_versions_fresh(packages: list) -> dict:
    """Liest die installierten Versionen in einem frischen Interpreter.

    importlib.metadata cached im laufenden Prozess: nach einem pip-Upgrade
    meldet es weiterhin den Stand vom Start. Nur ein eigener Prozess sieht,
    was tatsaechlich auf der Platte liegt.
    """
    import json as _json
    import subprocess as _sp

    code = (
        "import json,sys\n"
        "from importlib.metadata import version, PackageNotFoundError\n"
        "out={}\n"
        "for p in sys.argv[1:]:\n"
        "    try: out[p]=version(p)\n"
        "    except PackageNotFoundError: out[p]=None\n"
        "print(json.dumps(out))"
    )
    try:
        r = _sp.run(
            [sys.executable, "-c", code, *packages],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if r.returncode == 0:
            return _json.loads(r.stdout)
        _upd_log.warning("updater: Versionsabfrage rc=%s: %s", r.returncode, r.stderr.strip())
    except Exception as e:
        _upd_log.warning("updater: Versionsabfrage fehlgeschlagen: %s", e)
    return {}


def _do_update() -> None:
    # Alles ab hier im try: run_update() hat den Status bereits auf "running"
    # gesetzt. Kommt diese Funktion nicht bis zum finally, bleibt er dort
    # stehen und jeder weitere Update-Start wird stillschweigend abgelehnt.
    log_id = None
    clear_active_log_id = clear_tee_context = None

    try:
        import subprocess as _subprocess

        from astrapi_core.system.activity_log import log_activity, update_activity_log
        from astrapi_core.system.logger import (
            clear_active_log_id,
            clear_tee_context,
            set_active_log_id,
            set_tee_context,
        )
        from astrapi_core.system.logger import log as _core_log

        pkgs = _packages_to_update()

        # Das Activity-Log ist Beiwerk – schlaegt es fehl, laeuft das Update
        # trotzdem, nur ohne Live-Ausgabe im Modal.
        try:
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
        except Exception as e:
            _upd_log.warning("updater: Activity-Log nicht verfuegbar: %s", e)

        vorher = _installed_versions_fresh(pkgs)

        # --no-cache-dir: pips lokaler Cache soll nicht zwischen uns und dem
        # Index stehen, sonst ist bei Problemen nie klar, woher der Stand kam.
        cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "--no-cache-dir"] + pkgs
        _core_log("INFO", f"$ {' '.join(cmd)}")
        proc = _subprocess.Popen(
            cmd,
            stdout=_subprocess.PIPE,
            stderr=_subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )

        # core-log() statt logging.getLogger(): nur ersteres schreibt nach
        # activity_log_lines und damit ins Log-Modal.
        for line in proc.stdout:
            _core_log("INFO", line.rstrip())

        proc.wait()

        if proc.returncode == 0:
            nachher = _installed_versions_fresh(pkgs)
            geaendert = [
                {"name": p, "from": vorher.get(p) or "—", "to": nachher.get(p) or "—"}
                for p in pkgs
                if vorher.get(p) != nachher.get(p)
            ]

            if geaendert:
                for z in geaendert:
                    _core_log("INFO", f"Aktualisiert – {z['name']}: {z['from']} → {z['to']}")
                if log_id is not None:
                    update_activity_log(log_id, status="ok")
                with _upd_lock:
                    _upd_state["status"] = "done"
                    _upd_state["packages"] = []
                    _upd_state["changed"] = geaendert
                    _upd_state["seen"] = False
                # Ohne diesen Hinweis bricht gleich die SSE-Verbindung ab und
                # das Log-Modal meldet nur "Verbindung getrennt" – das sieht
                # nach Fehler aus, ist aber der geplante Neustart.
                _core_log("INFO", "Dienst startet neu, sobald die Oberfläche das Ergebnis abgeholt hat – Seite danach neu laden.")
                _schedule_restart()
            else:
                # pip beendet sich auch dann mit 0, wenn es nichts zu tun fand.
                # Typischer Fall: die Pruefung liest die PyPI-JSON-API, die einen
                # Upload sofort zeigt, waehrend pip den Simple-Index abfragt, der
                # ueber ein CDN laeuft und ein paar Minuten hinterherhaengt.
                msg = (
                    "pip meldet Erfolg, aber keine Version hat sich geändert. "
                    "Der Paket-Index von pip hinkt einem frischen Release meist "
                    "ein paar Minuten hinterher – in Kürze erneut versuchen."
                )
                _core_log("WARNING", msg)
                if log_id is not None:
                    update_activity_log(log_id, status="warning", error_message=msg)
                with _upd_lock:
                    _upd_state["status"] = "warning"
                    _upd_state["error"] = msg
        else:
            msg = f"pip fehlgeschlagen (exit code {proc.returncode})"
            if log_id is not None:
                update_activity_log(log_id, status="error", error_message=msg)
            with _upd_lock:
                _upd_state["status"] = "error"
                _upd_state["error"] = msg

    except Exception as e:
        err = str(e)
        _upd_log.warning("updater: Update fehlgeschlagen: %s", err)
        if log_id is not None:
            try:
                from astrapi_core.system.activity_log import (
                    update_activity_log as _ual,
                )

                _ual(log_id, status="error", error_message=err)
            except Exception:
                pass
        with _upd_lock:
            _upd_state["status"] = "error"
            _upd_state["error"] = err
    finally:
        # Sicherheitsnetz: der Status darf "running" unter keinen Umstaenden
        # ueberleben, sonst ist der Button dauerhaft wirkungslos.
        with _upd_lock:
            if _upd_state["status"] == "running":
                _upd_state["status"] = "error"
                if not _upd_state["error"]:
                    _upd_state["error"] = "Update unerwartet abgebrochen"
        for _fn in (clear_active_log_id, clear_tee_context):
            if _fn is not None:
                try:
                    _fn()
                except Exception:
                    pass


_RESTART_MAX_WAIT = 15.0  # Sicherheitsnetz, falls kein Client mehr pollt (Tab zu o.ae.)


def _wait_for_seen_then_restart() -> None:
    """Wartet bis ein Client den "done"-Status abgeholt hat (get_status()
    setzt "seen"), hoechstens _RESTART_MAX_WAIT Sekunden. Vorher lief hier
    eine geratene feste Wartezeit (2s, dann 3s) - kein Kriterium, nur eine
    Vermutung, dass die Oberflaeche bis dahin einmal gepollt hat."""
    waited = 0.0
    while waited < _RESTART_MAX_WAIT:
        with _upd_lock:
            if _upd_state["seen"]:
                break
        time.sleep(0.3)
        waited += 0.3
    _restart_process()


def _restart_process() -> None:
    """Startet den Dienst neu. Bevorzugt `systemctl restart <package>` -
    systemd-konform, sauberer Prozesswechsel, sichtbarer Restart-Status.
    Schlaegt das fehl (kein systemd, Unit-Name weicht ab, keine Berechtigung
    o.ae.), faellt es auf os.execv zurueck - das ersetzt den Prozess zwar nur
    in-place statt ihn ueber den Service-Manager neu zu starten, funktioniert
    aber garantiert, unabhaengig von Unit-Namen und Berechtigungen."""
    import os

    if _app_package:
        try:
            r = subprocess.run(
                ["systemctl", "restart", _app_package],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if r.returncode == 0:
                # systemd hat den Stop-Job ausgeloest - dieser Prozess bekommt
                # gleich SIGTERM und laeuft nicht weiter bis hierher zurueck.
                return
            _upd_log.warning(
                "updater: systemctl restart %s fehlgeschlagen (rc=%s): %s "
                "- falle zurueck auf os.execv",
                _app_package, r.returncode, r.stderr.strip(),
            )
        except Exception as e:
            _upd_log.warning(
                "updater: systemctl restart nicht verfuegbar (%s) - falle zurueck auf os.execv", e
            )
    os.execv(sys.executable, [sys.executable] + sys.argv)


def _schedule_restart() -> None:
    _threading.Thread(
        target=_wait_for_seen_then_restart, daemon=True, name="system-restart-wait"
    ).start()


def set_error(message: str) -> None:
    """Hinterlegt eine Meldung, die beim nächsten Render angezeigt wird."""
    with _upd_lock:
        _upd_state["error"] = message


def get_status() -> dict:
    """Gibt den aktuellen Updater-Status zurück.

    Markiert nebenbei "seen": ein Aufruf, waehrend kein Lauf mehr aktiv ist
    (status nicht running/checking), zaehlt als abgeholt - Kriterium fuer
    _schedule_restart(), das damit nicht mehr blind eine feste Zeit warten
    muss (siehe dort).
    """
    with _upd_lock:
        if _upd_state["status"] not in ("running", "checking"):
            _upd_state["seen"] = True
        return {
            "status": _upd_state["status"],
            "log_id": _upd_state["log_id"],
            "last_checked": _upd_state["last_checked"],
            "packages": list(_upd_state["packages"]),
            "error": _upd_state["error"],
            "changed": list(_upd_state["changed"]),
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
