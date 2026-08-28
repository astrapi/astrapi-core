# core/system/format.py
"""Gemeinsame Formatierungsfunktionen."""


def fmt_bytes(n: float | None) -> str:
    """Formatiert eine Byte-Anzahl lesbar (B, KB, MB, GB, TB, PB)."""
    if n is None:
        return "—"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def fmt_now() -> str:
    """Aktuellen Zeitstempel im deutschen Format: TT.MM.JJJJ HH:MM"""
    from datetime import datetime
    return datetime.now().strftime("%d.%m.%Y %H:%M")


def fmt_timestamp(ts: float) -> str:
    """Beliebigen Unix-Zeitstempel (z.B. Path.stat().st_mtime) im selben
    deutschen Format wie fmt_now(): TT.MM.JJJJ HH:MM"""
    from datetime import datetime
    return datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M")
