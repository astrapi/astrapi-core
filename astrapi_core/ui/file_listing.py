# core/ui/file_listing.py
#
# Wiederverwendbarer HTML-Datei-Browser (Seiten-Gerüst + Verzeichnisliste)
# für Apps, die einen eigenen Datei-/Repository-Baum über HTTP ausliefern
# (astrapi-mirror, astrapi-packages, astrapi-sync). Bewusst reines
# HTML/String-Rendering ohne Jinja2 -- diese Routen liegen außerhalb des
# normalen Modul-/Template-Systems (direkte Dateiauslieferung an
# Paketmanager wie pacman/apt, kein UI-Modul mit Navigation/Layout).
#
# Optisch an die Admin-Oberfläche angelehnt: lädt deren echtes
# /static/css/app.css (gleiche CSS-Variablen/Fonts wie im Dashboard),
# ergänzt nur noch die seitenspezifische Karten-/Tabellen-Optik lokal --
# kein Duplizieren der Farbwerte, die bleiben damit automatisch in Sync
# mit dem Dashboard. Icons sind bewusst als einzelne <svg>-Konstanten
# inline gehalten statt über den Jinja-Sprite-Mechanismus
# (astrapi_core/ui/icons.py::build_sprite()), der außerhalb des
# Template-Systems nicht zur Verfügung steht.
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


def _icon(path_d: str, color: str = "currentColor") -> str:
    return (
        f'<svg width="14" height="14" viewBox="0 0 24 24" fill="{color}" stroke="none">'
        f'<path d="{path_d}"/></svg>'
    )


# Gleiche Pfaddaten wie astrapi_core/ui/icons/{folder,file,chevron-left,copy,check}.svg
# (mdi-Icons) -- hier hartkodiert statt build_sprite() zu nutzen, siehe Modul-Docstring.
_ICON_FOLDER_ROW = _icon(
    "M10,4H4C2.89,4 2,4.89 2,6V18A2,2 0 0,0 4,20H20A2,2 0 0,0 22,18V8C22,6.89 21.1,6 20,6H12L10,4Z",
    "#f5c211",
)
_ICON_FILE_ROW = _icon(
    "M13,9V3.5L18.5,9M6,2C4.89,2 4,2.89 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2H6Z",
    "var(--text-3)",
)
_ICON_BACK = _icon("M15.41,16.58L10.83,12L15.41,7.41L14,6L8,12L14,18L15.41,16.58Z")
_COPY_SVG = _icon(
    "M19,21H8V7H19M19,5H8A2,2 0 0,0 6,7V21A2,2 0 0,0 8,23H19A2,2 0 0,0 21,21V7A2,2 0 0,0 19,5"
    "M16,1H4A2,2 0 0,0 2,3V17H4V3H16V1Z"
)
_CHECK_SVG = _icon("M21,7L9,19L3.5,13.5L4.91,12.09L9,16.17L19.59,5.59L21,7Z", "#3fb950")

_CSS = """
    body { font-family:var(--font); background:var(--bg); color:var(--text); margin:0; padding:28px; }
    a { text-decoration:none; }
    .fb-topbar { display:flex; align-items:center; gap:10px; margin-bottom:14px; }
    .fb-back { display:inline-flex; align-items:center; gap:4px; padding:6px 10px;
               border-radius:6px; background:var(--card); color:var(--text-2);
               font-size:12px; flex-shrink:0; }
    .fb-back:hover { color:var(--text); }
    h1 { font-size:18px; font-weight:600; margin:0; color:var(--text); }
    .fb-hint { color:var(--text-3); font-size:13px; margin-bottom:16px; }
    .fb-card { background:var(--card); border:1px solid var(--border-s);
               border-radius:var(--rad-lg); overflow:hidden; margin-bottom:20px; }
    table { border-collapse:collapse; width:100%; table-layout:fixed;
            font-family:var(--mono); font-size:13px; }
    col.c-name { width:14%; }
    col.c-date { width:17%; }
    col.c-size { width:8%; }
    col.c-inst { width:61%; }
    col.c-size2 { width:12%; }
    col.c-name1 { width:100%; }
    thead th { text-align:left; padding:9px 16px; border-bottom:1px solid var(--border-s);
               color:var(--text-3); font-size:11px; font-weight:600; text-transform:uppercase;
               letter-spacing:.06em; background:var(--card-hi); }
    thead th:nth-child(2) { text-align:right; }
    thead th:nth-child(3) { text-align:right; padding-right:2.5rem; }
    thead th:nth-child(2):last-child { text-align:right; }
    thead th:nth-child(3):last-child { text-align:right; }
    tbody tr { border-bottom:1px solid var(--border-s); transition:background .1s; }
    tbody tr:last-child { border-bottom:none; }
    tbody tr:hover { background:rgba(128,128,128,0.07); }
    td { padding:8px 16px; vertical-align:middle; overflow:hidden; color:var(--text-2); }
    td[colspan] { text-align:center; color:var(--text-3); padding:32px; }
    td a { color:var(--text); display:flex; align-items:center; gap:8px; overflow:hidden; }
    td a svg { flex-shrink:0; opacity:.85; }
    td a span { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    td.size { text-align:right; color:var(--text-3); white-space:nowrap; }
    td.num { text-align:right; color:var(--text-3); white-space:nowrap; }
    td.num-gap { text-align:right; color:var(--text-3); white-space:nowrap; padding-right:2.5rem; }
    .copy-btn { background:none; border:none; cursor:pointer; padding:4px 6px; border-radius:4px;
                opacity:.55; color:var(--text-3); transition:opacity .15s; flex-shrink:0; }
    .copy-btn:hover { opacity:1; color:var(--text); }
    .copy-btn svg { display:block; }
    .cmd { display:flex; align-items:center; gap:.5rem; overflow:hidden; }
    .cmd code { color:var(--text-3); white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
                flex:1; min-width:0; }
    .setup { background:var(--card); border:1px solid var(--border-s); border-radius:var(--rad-lg);
             padding:16px 20px; margin-bottom:20px; }
    .setup h2 { color:var(--text); font-size:14px; font-weight:600; margin:0 0 10px; }
    .step { color:var(--text-3); font-size:12px; margin:14px 0 5px; }
    .pre-wrap { position:relative; }
    .pre-wrap .copy-btn { position:absolute; top:4px; right:4px; }
    .setup pre { background:var(--card-hi); border:1px solid var(--border-s); border-radius:6px;
                 padding:10px 16px; margin:4px 0 0; font-size:12px; font-family:var(--mono);
                 overflow-x:auto; line-height:1.5; white-space:pre; color:var(--text-2); }
"""


def copy_button(uid: str, text: str) -> str:
    """Kopieren-Button (Zwischenablage) für ein Snippet, z.B. einen curl-Befehl."""
    return (
        f'<textarea id="{uid}" style="display:none">{_html.escape(text)}</textarea>'
        f'<button class="copy-btn" onclick="copySnippet(\'{uid}\',this)" title="Kopieren">'
        f'<span class="ci">{_COPY_SVG}</span>'
        f'<span class="ck" style="display:none">{_CHECK_SVG}</span>'
        f'</button>'
    )


def dir_link(label: str, href: str) -> str:
    """Verzeichnis-Link (Ordner-Icon + Name) für manuell gebaute Index-Zeilen
    (Distro-/Repo-/Ordner-Übersichten), die nicht über
    list_dir_entries()/render_row() laufen. label wird escaped -- unescaped
    übergeben, nicht vorher schon selbst html.escape()en."""
    return f'<a href="{href}">{_ICON_FOLDER_ROW}<span>{_html.escape(label)}</span></a>'


def file_link(label: str, href: str) -> str:
    """Wie dir_link(), aber mit Datei-Icon -- für einzelne Dateien in
    manuell gebauten Zeilen (z.B. virtuelle .sources/.gpg-Einträge)."""
    return f'<a href="{href}">{_ICON_FILE_ROW}<span>{_html.escape(label)}</span></a>'


def render_page(
    title: str,
    hint: str,
    rows_html: str,
    back: str | None = None,
    col_headers: tuple[str, ...] = ("Name", "Größe"),
    colgroup: str = "",
) -> str:
    """Seiten-Gerüst: Titel, Hinweistext, Tabelle, Zurück-Link, Copy-Script.

    Lädt /static/css/app.css (in mirror/packages/sync identisch unter
    diesem Pfad gemountet, siehe _app.py) für Fonts + Farbvariablen --
    dieselbe Optik wie das Admin-Dashboard, ohne sie hier zu duplizieren."""
    back_html = f'<a class="fb-back" href="{back}">{_ICON_BACK}<span>Zurück</span></a>' if back else ""
    headers_html = "".join(f"<th>{h}</th>" for h in col_headers)
    hint_html = f'<div class="fb-hint">{hint}</div>' if hint else ""
    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8"><title>{title}</title>
<link rel="stylesheet" href="/static/css/app.css">
<style>{_CSS}</style>
</head>
<body>
  <div class="fb-topbar">
    {back_html}
    <h1>{title}</h1>
  </div>
  {hint_html}
  <div class="fb-card">
    <table>
      {colgroup}
      <thead><tr>{headers_html}</tr></thead>
      <tbody>{rows_html}</tbody>
    </table>
  </div>
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
    icon = _ICON_FOLDER_ROW if entry.is_dir else _ICON_FILE_ROW
    return (
        f'<tr><td><a href="{entry.href}">{icon}<span>{_html.escape(display)}</span></a></td>'
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
    """Gibt aufgelösten Pfad zurück; wirft 400 bei Path-Traversal.

    Vergleicht die echte Path.parents-Hierarchie statt eines
    String-Präfix -- ein reiner Präfix-Vergleich würde z.B. Repo "1" und
    "18" verwechseln (".../1" ist ein String-Präfix von ".../18/geheim",
    obwohl "18" kein Kindverzeichnis von "1" ist). Identische Fehlerklasse
    wie vor T-213-SYNC (astrapi_sync._paths.py::resolve_within(), dort
    schon so gefixt)."""
    base = base.resolve()
    resolved = (base / Path(*parts)).resolve()
    if resolved != base and base not in resolved.parents:
        raise HTTPException(400, "Ungültiger Pfad")
    return resolved
