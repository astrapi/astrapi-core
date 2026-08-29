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


def _version_tokens(v: str) -> list[str]:
    import re
    return re.findall(r"\d+|\D+", v or "")


def version_is_newer(a: str, b: str) -> bool:
    """True wenn Versionsstring a echt neuer ist als b.

    Natural-Version-Sort wie GNU `sort -V` (Ziffern-Laeufe numerisch,
    Rest lexikografisch vergleichen) -- passt auf unsere ueblichen
    punktgetrennten Versionen mit optionalem -pkgrel-Suffix
    (z.B. "26.8.2-1" vs "26.8.1-1"). Keine echte pacman-vercmp-
    Implementierung, aber fuer diesen Zweck (Badge "Update verfuegbar"
    nur bei echtem Fortschritt zeigen) ausreichend.
    """
    for x, y in zip(_version_tokens(a), _version_tokens(b)):
        if x == y:
            continue
        if x.isdigit() and y.isdigit():
            return int(x) > int(y)
        return x > y
    return len(_version_tokens(a)) > len(_version_tokens(b))
