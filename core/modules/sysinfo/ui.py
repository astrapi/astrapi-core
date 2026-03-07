"""core/modules/sysinfo/ui.py – Flask-Blueprint für /ui/sysinfo/"""

from flask import Blueprint, render_template

bp = Blueprint("sysinfo_ui", __name__)


def _collect() -> dict:
    """Gleiche Logik wie api.py — direkt genutzt für HTMX-Partials."""
    try:
        import psutil, time

        cpu_pct   = psutil.cpu_percent(interval=0.2)
        cpu_count = psutil.cpu_count(logical=True)
        cpu_freq  = psutil.cpu_freq()

        ram  = psutil.virtual_memory()
        swap = psutil.swap_memory()
        disk = psutil.disk_usage("/")

        boot_ts  = psutil.boot_time()
        uptime_s = int(time.time() - boot_ts)

        net = psutil.net_io_counters()

        # Top-Prozesse nach CPU
        procs = []
        for p in sorted(
            psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]),
            key=lambda p: p.info["cpu_percent"] or 0,
            reverse=True,
        )[:8]:
            procs.append(p.info)

        return {
            "ok": True,
            "cpu": {
                "percent": cpu_pct,
                "cores":   cpu_count,
                "freq":    round(cpu_freq.current, 0) if cpu_freq else "—",
            },
            "ram": {
                "total":   round(ram.total   / 1024**3, 1),
                "used":    round(ram.used    / 1024**3, 1),
                "percent": ram.percent,
            },
            "swap": {
                "total":   round(swap.total  / 1024**3, 1),
                "used":    round(swap.used   / 1024**3, 1),
                "percent": swap.percent,
            },
            "disk": {
                "total":   round(disk.total  / 1024**3, 1),
                "used":    round(disk.used   / 1024**3, 1),
                "percent": disk.percent,
            },
            "uptime": f"{uptime_s // 3600}h {(uptime_s % 3600) // 60}m",
            "network": {
                "sent": round(net.bytes_sent / 1024**2, 1),
                "recv": round(net.bytes_recv / 1024**2, 1),
            },
            "processes": procs,
        }
    except ImportError:
        return {"ok": False, "error": "psutil nicht installiert"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@bp.route("/ui/sysinfo/content")
def sysinfo_content():
    return render_template("sysinfo/partials/tab.html", info=_collect())
