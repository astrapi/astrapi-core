"""
astrapi_core/ui/icons.py – SVG-Sprite-Builder

Zwei Icon-Quellen werden kombiniert:

1. Modul-Icons  – jedes Modul kann im eigenen Verzeichnis mitbringen:
     icon.svg          → Symbol-ID  "icon-{module.key}"
     icon-outline.svg  → Symbol-ID  "icon-{module.key}-outline"

2. Generische Icons – für UI-Elemente die kein Modul repräsentieren
   (z.B. moon, sun, default, bell …):
     {name}.svg in ui/icons/ → Symbol-ID "icon-{title}" oder "icon-{dateiname}"
     Priorität: <title>-Tag, Fallback: Dateiname ohne Endung.

Referenz im Template:  <use href="#icon-{name}">
"""

from __future__ import annotations

import re
from pathlib import Path


def _symbol(icon_id: str, svg_content: str) -> str:
    """Wandelt eine SVG-Datei in ein <symbol>-Element um."""
    vb_m = re.search(r'viewBox="([^"]+)"', svg_content)
    viewbox = vb_m.group(1) if vb_m else "0 0 24 24"

    inner = re.sub(r"<\?xml[^>]*\?>", "", svg_content)
    inner = re.sub(r"<svg[^>]*>", "", inner)
    inner = re.sub(r"</svg\s*>", "", inner)
    inner = re.sub(r"<title[^>]*>.*?</title>", "", inner, flags=re.DOTALL)
    inner = inner.strip()
    inner = inner.replace('fill="black"', 'fill="currentColor"')
    inner = inner.replace("fill='black'", "fill='currentColor'")

    return f'<symbol id="{icon_id}" viewBox="{viewbox}">{inner}</symbol>'


def build_sprite(modules: list, extra_dirs: list[Path] | None = None) -> str:
    """Baut einen kombinierten SVG-Sprite-String.

    Args:
        modules:    Geladene Modul-Objekte (mit module_root-Attribut).
        extra_dirs: Zusätzliche Verzeichnisse mit benannten *.svg-Dateien
                    (Dateiname / <title> wird zur Symbol-ID).
    """
    symbols: list[str] = []
    seen: set[str] = set()

    def _add(icon_id: str, path: Path) -> None:
        if icon_id in seen or not path.exists():
            return
        seen.add(icon_id)
        symbols.append(_symbol(icon_id, path.read_text(encoding="utf-8")))

    # ── 1. Modul-Icons ────────────────────────────────────────────────────────
    for mod in modules:
        root = getattr(mod, "module_root", None)
        if not root:
            continue
        _add(f"icon-{mod.key}", root / "icon.svg")
        _add(f"icon-{mod.key}-outline", root / "icon-outline.svg")

    # ── 2. Generische Icons aus extra_dirs ────────────────────────────────────
    for d in extra_dirs or []:
        if not d.is_dir():
            continue
        for svg_file in sorted(d.glob("*.svg")):
            content = svg_file.read_text(encoding="utf-8")
            title_m = re.search(r"<title[^>]*>(.*?)</title>", content, re.DOTALL)
            name = title_m.group(1).strip() if title_m else svg_file.stem
            icon_id = "icon-" + name
            if icon_id in seen:
                continue
            seen.add(icon_id)
            symbols.append(_symbol(icon_id, content))

    if not symbols:
        return ""

    return (
        '<svg xmlns="http://www.w3.org/2000/svg" style="display:none">'
        + "".join(symbols)
        + "</svg>"
    )
