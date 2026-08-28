# core/ui/file_listing.py
#
# Wiederverwendbarer HTML-Datei-Browser (Seiten-Gerüst + Verzeichnisliste)
# für Apps, die einen eigenen Datei-/Repository-Baum über HTTP ausliefern
# (astrapi-mirror, astrapi-packages). Bewusst reines HTML/String-Rendering
# ohne Jinja2 -- diese Routen liegen außerhalb des normalen
# Modul-/Template-Systems (direkte Dateiauslieferung an Paketmanager wie
# pacman/apt, kein UI-Modul mit Navigation/Layout).
#
# Vorher unabhängig in astrapi-mirror und astrapi-packages dupliziert
# (mit leicht abweichenden Details) -- siehe astrapi-hub-Vault,
# T-259-MIRROR/T-260-MIRROR: "generische Features gehören in Core,
# nicht pro App dupliziert."

from __future__ import annotations

import html as _html
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException

from astrapi_core.system.format import fmt_bytes, fmt_timestamp

_CSS = """
    @font-face { font-family:'JetBrains Mono'; src:url('/static/fonts/mono.woff2') format('woff2'); }
    :root { --mono:'JetBrains Mono',ui-monospace,monospace; }
    body { font-family:var(--mono); font-size:.85rem; padding:2rem; background:#0d1117; color:#c9d1d9; }
    h1 { color:#58a6ff; margin-bottom:.25rem; }
    p.hint { color:#8b949e; font-size:.85rem; margin-bottom:1.5rem; }
    p.back { margin-bottom:1rem; font-size:.85rem; }
    table { border-collapse:collapse; width:100%; table-layout:fixed; }
    col.c-name { width:14%; }
    col.c-date { width:17%; }
    col.c-size { width:8%; }
    col.c-inst { width:61%; }
    col.c-size2 { width:12%; }
    col.c-name1 { width:100%; }
    thead th { text-align:left; padding:.4rem 1rem; border-bottom:2px solid #30363d; color:#8b949e; font-size:.8rem; font-weight:600; letter-spacing:.04em; }
    td.size { text-align:right; color:#8b949e; white-space:nowrap; }
    thead th:nth-child(2) { text-align:right; }
    thead th:nth-child(3) { text-align:right; padding-right:2.5rem; }
    thead th:nth-child(2):last-child { text-align:right; }
    thead th:nth-child(3):last-child { text-align:right; }
    td { padding:.35rem 1rem; border-bottom:1px solid #21262d; vertical-align:middle; overflow:hidden; }
    td.num { text-align:right; color:#8b949e; white-space:nowrap; }
    td.num-gap { text-align:right; color:#8b949e; white-space:nowrap; padding-right:2.5rem; }
    div.hint { color:#8b949e; font-size:.85rem; margin-bottom:1.5rem; }
    div.hint pre { background:#161b22; border:1px solid #30363d; border-radius:6px; padding:.75rem 2.5rem .75rem 1rem; margin:.5rem 0 0; font-size:.82rem; white-space:pre; overflow-x:auto; color:#c9d1d9; }
    a { text-decoration:none; color:#58a6ff; }
    a:hover { text-decoration:underline; }
    .copy-btn { background:none; border:none; cursor:pointer; padding:4px 6px; border-radius:4px; opacity:.55; color:#8b949e; transition:opacity .15s; flex-shrink:0; }
    .copy-btn:hover { opacity:1; color:#c9d1d9; }
    .cmd { display:flex; align-items:center; gap:.5rem; overflow:hidden; }
    .cmd code { color:#8b949e; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; flex:1; min-width:0; }
    .setup { background:#161b22; border:1px solid #30363d; border-radius:6px; padding:1rem 1.25rem; margin-bottom:1.5rem; color:#c9d1d9; }
    .setup h2 { color:#58a6ff; font-size:.95rem; margin:0 0 .75rem; }
    .step { color:#8b949e; font-size:.8rem; margin:.85rem 0 .3rem; }
    .pre-wrap { position:relative; }
    .pre-wrap .copy-btn { position:absolute; top:4px; right:4px; }
    .setup pre { background:#0d1117; border:1px solid #21262d; border-radius:4px; padding:.6rem 1rem; margin:.25rem 0 0; font-size:.82rem; overflow-x:auto; line-height:1.5; white-space:pre; }
"""

_COPY_SVG = (
    '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">'
    '<path d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11'
    'c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z"/></svg>'
)


def copy_button(uid: str, text: str) -> str:
    """Kopieren-Button (Zwischenablage) für ein Snippet, z.B. einen curl-Befehl."""
    return (
        f'<textarea id="{uid}" style="display:none">{_html.escape(text)}</textarea>'
        f'<button class="copy-btn" onclick="copySnippet(\'{uid}\',this)" title="Kopieren">'
        f'<span class="ci">{_COPY_SVG}</span>'
        f'<span class="ck" style="display:none;color:#3fb950">✓</span>'
        f'</button>'
    )


def render_page(
    title: str,
    hint: str,
    rows_html: str,
    back: str | None = None,
    col_headers: tuple[str, ...] = ("Name", "Größe"),
    colgroup: str = "",
) -> str:
    """Seiten-Gerüst: Titel, Hinweistext, Tabelle, Zurück-Link, Copy-Script."""
    back_html = f'<p class="back"><a href="{back}">← Zurück</a></p>' if back else ""
    headers_html = "".join(f"<th>{h}</th>" for h in col_headers)
    return f"""<!DOCTYPE html>
<html lang="de">
<head><meta charset="utf-8"><title>{title}</title><style>{_CSS}</style></head>
<body>
  {back_html}
  <h1>{title}</h1>
  <div class="hint">{hint}</div>
  <table>
    {colgroup}
    <thead><tr>{headers_html}</tr></thead>
    <tbody>{rows_html}</tbody>
  </table>
<script>
function copySnippet(id, btn) {{
  var txt = document.getElementById(id).value;
  var done = function() {{
    var i = btn.querySelector('.ci'), c = btn.querySelector('.ck');
    i.style.display='none'; c.style.display='';
    setTimeout(function(){{i.style.display='';c.style.display='none';}},1500);
  }};
  if (navigator.clipboard) {{
    navigator.clipboard.writeText(txt).then(done).catch(done);
  }} else {{
    var ta = document.createElement('textarea');
    ta.value = txt; ta.style.position='fixed'; ta.style.opacity='0';
    document.body.appendChild(ta); ta.focus(); ta.select();
    try {{ document.execCommand('copy'); }} catch(e) {{}}
    document.body.removeChild(ta); done();
  }}
}}
</script>
</body>
</html>"""


@dataclass
class ListingEntry:
    """Eine Zeile einer Verzeichnisliste."""

    name: str
    href: str
    is_dir: bool = False
    size_bytes: int | None = None
    mtime: float | None = None


def render_row(entry: ListingEntry) -> str:
    """Rendert eine ListingEntry als <tr> mit Name/Geändert/Größe-Spalten."""
    display = entry.name + ("/" if entry.is_dir else "")
    size = "—" if entry.size_bytes is None else fmt_bytes(entry.size_bytes)
    mtime = "—" if entry.mtime is None else fmt_timestamp(entry.mtime)
    return (
        f'<tr><td><a href="{entry.href}">{_html.escape(display)}</a></td>'
        f'<td>{mtime}</td><td class="size">{size}</td></tr>'
    )


def list_dir_entries(directory: Path, href_fn) -> list[ListingEntry]:
    """Iteriert ein Verzeichnis und liefert sortierte ListingEntry-Objekte.

    Verzeichnisse zuerst, dann Dateien, jeweils alphabetisch -- gleiche
    Sortierung wie zuvor in astrapi-mirror. href_fn(entry_name, is_dir)
    baut die Ziel-URL, da das je nach Aufrufer unterschiedlich aussieht
    (mit/ohne Zwischenpfad).
    """
    entries = sorted(directory.iterdir(), key=lambda p: (p.is_file(), p.name))
    result = []
    for e in entries:
        stat = e.stat()
        result.append(
            ListingEntry(
                name=e.name,
                href=href_fn(e.name, e.is_dir()),
                is_dir=e.is_dir(),
                size_bytes=None if e.is_dir() else stat.st_size,
                mtime=stat.st_mtime,
            )
        )
    return result


def safe_child(base: Path, *parts: str) -> Path:
    """Gibt aufgelösten Pfad zurück; wirft 400 bei Path-Traversal."""
    resolved = (base / Path(*parts)).resolve()
    if not str(resolved).startswith(str(base.resolve())):
        raise HTTPException(400, "Ungültiger Pfad")
    return resolved
