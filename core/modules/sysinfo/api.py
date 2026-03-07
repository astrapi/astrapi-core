"""core/modules/sysinfo/api.py – FastAPI-Router für /api/sysinfo/"""

import time
from fastapi import APIRouter

router = APIRouter()

_cache: dict = {}
_cache_ts: float = 0.0
_CACHE_TTL: float = 2.0


def _collect_cached() -> dict:
    global _cache, _cache_ts
    if time.monotonic() - _cache_ts >= _CACHE_TTL:
        _cache = _collect()
        _cache_ts = time.monotonic()
    return _cache


def _collect() -> dict:
    try:
        import psutil, time

        cpu_pct     = psutil.cpu_percent(interval=0.2)
        cpu_count   = psutil.cpu_count(logical=True)
        cpu_freq    = psutil.cpu_freq()

        ram         = psutil.virtual_memory()
        swap        = psutil.swap_memory()

        disk        = psutil.disk_usage("/")

        boot_ts     = psutil.boot_time()
        uptime_s    = int(time.time() - boot_ts)
        uptime_h    = uptime_s // 3600
        uptime_m    = (uptime_s % 3600) // 60

        net         = psutil.net_io_counters()

        return {
            "cpu": {
                "percent":   cpu_pct,
                "cores":     cpu_count,
                "freq_mhz":  round(cpu_freq.current, 1) if cpu_freq else None,
            },
            "ram": {
                "total_gb":  round(ram.total / 1024**3, 2),
                "used_gb":   round(ram.used  / 1024**3, 2),
                "percent":   ram.percent,
            },
            "swap": {
                "total_gb":  round(swap.total / 1024**3, 2),
                "used_gb":   round(swap.used  / 1024**3, 2),
                "percent":   swap.percent,
            },
            "disk": {
                "total_gb":  round(disk.total / 1024**3, 2),
                "used_gb":   round(disk.used  / 1024**3, 2),
                "percent":   disk.percent,
            },
            "uptime": {
                "hours":   uptime_h,
                "minutes": uptime_m,
                "label":   f"{uptime_h}h {uptime_m}m",
            },
            "network": {
                "sent_mb":  round(net.bytes_sent / 1024**2, 2),
                "recv_mb":  round(net.bytes_recv / 1024**2, 2),
            },
        }
    except ImportError:
        return {"error": "psutil nicht installiert (pip install psutil)"}


@router.get("/", summary="System Info")
def get_sysinfo():
    return _collect()

@router.get("/cpu", summary="CPU Info")
def get_cpu():
    return _collect_cached().get("cpu", {})

@router.get("/ram", summary="RAM Info")
def get_ram():
    return _collect_cached().get("ram", {})

@router.get("/disk", summary="Disk Info")
def get_disk():
    return _collect_cached().get("disk", {})
