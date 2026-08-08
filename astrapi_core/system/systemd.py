# core/systemd.py
"""Systemd-Integration: sd_notify und Watchdog-Thread."""
import os
import socket
import threading
import time

# Zeitpunkt des letzten erfolgreich gesendeten WATCHDOG=1-Pings und das dabei
# verwendete Intervall - Grundlage fuer watchdog_active(), siehe dort.
_last_ping_ts: float | None = None
_watchdog_interval: int | None = None


def sd_notify(msg: str) -> bool:
    """Sendet eine Nachricht an systemd (NOTIFY_SOCKET) falls verfügbar.
    Gibt True zurück, wenn das Senden geglückt ist."""
    try:
        sock_path = os.environ.get("NOTIFY_SOCKET", "")
        if not sock_path:
            return False
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as s:
            s.connect(sock_path)
            s.sendall(msg.encode())
        return True
    except Exception:
        return False


def start_watchdog(interval: int = 20, check_fn=None) -> None:
    """Startet einen Watchdog-Thread für systemd.

    Sendet alle `interval` Sekunden WATCHDOG=1 an systemd.
    Falls check_fn angegeben, wird WATCHDOG=1 nur gesendet wenn check_fn() True zurückgibt.
    WatchdogSec in der Unit sollte mindestens 3× interval betragen (z.B. 60s bei interval=20).
    Tut nichts wenn NOTIFY_SOCKET nicht gesetzt ist.
    """
    if not os.environ.get("NOTIFY_SOCKET"):
        return

    global _watchdog_interval
    _watchdog_interval = interval

    def _ping():
        global _last_ping_ts
        while True:
            time.sleep(interval)
            try:
                if check_fn is None or check_fn():
                    if sd_notify("WATCHDOG=1"):
                        _last_ping_ts = time.time()
            except Exception:
                pass

    threading.Thread(target=_ping, daemon=True, name="systemd-watchdog").start()


def watchdog_active() -> bool:
    """Ob der Watchdog-Thread kürzlich erfolgreich an systemd gepingt hat.

    Anders als eine reine `NOTIFY_SOCKET`-Prüfung (nur: ist der Kanal da)
    zeigt das, ob der periodische WATCHDOG=1-Ping tatsächlich läuft und
    ankommt - `check_fn` in start_watchdog() muss dafür zuletzt `True`
    geliefert und der Socket-Versand geklappt haben. `False` u.a. auch dann,
    wenn start_watchdog() nie aufgerufen wurde oder der erste Intervall-Takt
    noch nicht verstrichen ist.
    """
    if _last_ping_ts is None or _watchdog_interval is None:
        return False
    return (time.time() - _last_ping_ts) <= 3 * _watchdog_interval
