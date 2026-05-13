"""
core/ui/controls.py  –  Deklaratives UI-System für Astrapi-Module

Module deklarieren ihre UI in Python (in __init__.py) statt in modul-spezifischen
Jinja2-Templates. Core rendert alles via Makros in ui_macros.html.

Beispiel (in einem Modul-__init__.py):

    from astrapi_core.ui.controls import Col, Header, ContentTable

    module = load_modul(
        ...,
        ui_header=Header([
            Header.filter_select("log_type", options=[
                {"value": "job", "label": "Jobs"},
                {"value": "error", "label": "Fehler"},
            ]),
        ]),
        ui_content=ContentTable(
            has_create=False,
            has_run_buttons=False,
            columns=[
                Col.text("name", "Name"),
                Col.trunc("description", "Beschreibung"),
                Col.join("tags", "Tags", sep=", "),
            ],
        ),
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ── Tabellenspalten ────────────────────────────────────────────────────────────


@dataclass
class Col:
    """Descriptor für eine Tabellenspalte in list_wrapper_inner.html.

    type-Werte:
        text        – einfacher Text
        trunc       – abgeschnittener Text mit title-Tooltip
        remote_path – "Hostname:Pfad" (remote_key + path_key)
        remote_host – nur der Hostname (remote_key)
        join        – Liste mit Trennzeichen verbinden
        mono        – monospace Text (Version, Key, …)
        badge_enum  – ein Badge basierend auf Wert-Mapping
        badge_list  – Badges für eine Liste von Werten
        link        – anklickbarer Link
        composed    – Template-String mit {key} Platzhaltern
    """

    type: str
    key: str
    label: str
    cls: str = ""
    sortable: bool = False

    # type-spezifische Felder
    remote_key: str = ""  # für remote_path / remote_host
    path_key: str = ""  # für remote_path
    sep: str = ", "  # für join
    template: str = ""  # für composed: "ctl/{item_name}:{key}"
    values: dict = field(default_factory=dict)  # für badge_enum / badge_list: {val: {label, cls}}

    # ── Factory-Methoden ──────────────────────────────────────────────────────

    @classmethod
    def text(cls, key: str, label: str, css: str = "", sortable: bool = True) -> "Col":
        return cls(type="text", key=key, label=label, cls=css, sortable=sortable)

    @classmethod
    def trunc(cls, key: str, label: str, sortable: bool = True) -> "Col":
        return cls(type="trunc", key=key, label=label, cls="col-trunc", sortable=sortable)

    @classmethod
    def remote_path(
        cls, remote_key: str, path_key: str, label: str, sortable: bool = False
    ) -> "Col":
        return cls(
            type="remote_path",
            key=path_key,
            label=label,
            cls="col-trunc",
            remote_key=remote_key,
            path_key=path_key,
            sortable=sortable,
        )

    @classmethod
    def remote_host(cls, remote_key: str, label: str, sortable: bool = False) -> "Col":
        return cls(type="remote_host", key=remote_key, label=label, sortable=sortable)

    @classmethod
    def join(cls, key: str, label: str, sep: str = ", ", css: str = "col-version") -> "Col":
        return cls(type="join", key=key, label=label, cls=css, sep=sep)

    @classmethod
    def mono(cls, key: str, label: str, css: str = "col-version") -> "Col":
        return cls(type="mono", key=key, label=label, cls=css)

    @classmethod
    def badge_enum(cls, key: str, label: str, values: dict, css: str = "col-type") -> "Col":
        """values: {value_str: {label: str, cls: str}}
        Beispiel: {"ok": {"label": "OK", "cls": "badge-status-ok"}}
        """
        return cls(type="badge_enum", key=key, label=label, cls=css, values=values)

    @classmethod
    def badge_list(cls, key: str, label: str, values: dict, css: str = "col-trunc") -> "Col":
        """Wie badge_enum, aber rendert eine Liste von Werten."""
        return cls(type="badge_list", key=key, label=label, cls=css, values=values)

    @classmethod
    def link(cls, key: str, label: str, css: str = "col-trunc") -> "Col":
        return cls(type="link", key=key, label=label, cls=css)

    @classmethod
    def composed(cls, key: str, label: str, template: str, css: str = "col-mono") -> "Col":
        """template: String mit {item_name} und {key} (z.B. 'ctl/{item_name}:{key}')"""
        return cls(type="composed", key=key, label=label, cls=css, template=template)


# ── Card-Body-Felder (meta-grid) ───────────────────────────────────────────────


@dataclass
class Field:
    """Descriptor für eine Zeile im card_body / meta-grid."""

    type: str
    key: str
    label: str
    mono: bool = False

    remote_key: str = ""
    path_key: str = ""
    sep: str = ", "
    values: dict = field(default_factory=dict)

    @classmethod
    def text(cls, key: str, label: str, mono: bool = False) -> "Field":
        return cls(type="text", key=key, label=label, mono=mono)

    @classmethod
    def join(cls, key: str, label: str, sep: str = ", ", mono: bool = False) -> "Field":
        return cls(type="join", key=key, label=label, sep=sep, mono=mono)

    @classmethod
    def remote_path(cls, remote_key: str, path_key: str, label: str) -> "Field":
        return cls(
            type="remote_path", key=path_key, label=label, remote_key=remote_key, path_key=path_key
        )

    @classmethod
    def badge_enum(cls, key: str, label: str, values: dict) -> "Field":
        return cls(type="badge_enum", key=key, label=label, values=values)


# ── Header-Controls ────────────────────────────────────────────────────────────


@dataclass
class HeaderControl:
    """Ein Element in content-header-actions.

    Typen:
        filter_select   – <select> mit Optionen, triggert HTMX-Request
        action_button   – <button> mit HTMX-Attributen
    """

    type: str

    # Gemeinsame Felder
    label: str = ""
    style: str = "primary"  # primary | danger | ghost | warning

    # HTMX
    hx_get: str = ""
    hx_post: str = ""
    hx_target: str = ""  # leer = auto (#container_id)
    hx_swap: str = ""  # leer = auto (innerHTML)
    hx_include: str = ""  # leer = auto (data-filter-for='module')

    # Für filter_select
    name: str = ""
    all_label: str = "Alle"
    options: list[dict] = field(default_factory=list)
    # Callable () -> list[dict]: dynamische Optionen (werden zur Render-Zeit ausgewertet)
    options_fn: object = field(default=None, repr=False)

    # Marker-Attribute
    data_attr: str = ""  # z.B. "data-actlog-filter" für individuelles hx-include


@dataclass
class Header:
    """Deklarativer Content-Header mit Controls-Liste."""

    controls: list[HeaderControl] = field(default_factory=list)

    # ── Factory-Methoden für Controls ─────────────────────────────────────────

    @staticmethod
    def filter_select(
        name: str,
        options: list[dict] | None = None,
        all_label: str = "Alle",
        hx_get: str = "",
        hx_target: str = "",
        hx_swap: str = "",
        hx_include: str = "",
        data_attr: str = "",
        options_fn=None,
    ) -> HeaderControl:
        """options: [{"value": ..., "label": ..., "default": True/False}]
        options_fn: callable () -> list[dict]  (dynamisch, wird zur Render-Zeit aufgerufen)
        """
        return HeaderControl(
            type="filter_select",
            name=name,
            options=options or [],
            all_label=all_label,
            hx_get=hx_get,
            hx_target=hx_target,
            hx_swap=hx_swap,
            hx_include=hx_include,
            data_attr=data_attr,
            options_fn=options_fn,
        )

    @staticmethod
    def action_button(
        label: str,
        hx_get: str = "",
        hx_post: str = "",
        hx_target: str = "",
        hx_swap: str = "beforeend",
        style: str = "primary",
    ) -> HeaderControl:
        return HeaderControl(
            type="action_button",
            label=label,
            hx_get=hx_get,
            hx_post=hx_post,
            hx_target=hx_target or "body",
            hx_swap=hx_swap,
            style=style,
        )


# ── Content-Typen ──────────────────────────────────────────────────────────────


@dataclass
class ContentTable:
    """Standard-Tabelle mit Spalten und Card-Fields."""

    type: str = "table"

    columns: list[Col] = field(default_factory=list)
    card_fields: list[Field] = field(default_factory=list)

    has_run_buttons: bool = True
    has_status: bool = True
    has_create: bool = True
    has_edit: bool = True
    has_delete: bool = True
    has_toggle: bool = True

    title: str = ""  # Titel für eingebettete Tabellen in columns-Layout

    # Für ContentColumns: gibt an, welches Context-Key die Tabellendaten enthält
    cfg_key: str = "cfg"
    # URL-Prefix für edit/delete/toggle-Aktionen (z.B. "jobs/" für Jobs-Sub-Tabellen)
    item_url_prefix: str = ""
    # Eigene card_actions für diese Tabelle (überschreibt modul.yaml card_actions)
    card_actions: list = field(default_factory=list)


@dataclass
class ContentColumns:
    """Mehrere Tabellen/Inhalte nebeneinander."""

    type: str = "columns"
    stretch: bool = False
    wide: bool = False
    cols: list[ContentTable] = field(default_factory=list)


@dataclass
class ContentMetricsGrid:
    """Metriken-Raster (z.B. CPU/RAM/Disk)."""

    type: str = "metrics_grid"
    reload_url: str = ""
    partial: str = ""  # Template-Pfad für das Metriken-Partial


@dataclass
class ContentCustom:
    """Benutzerdefiniertes Inner-Template statt list_wrapper_inner.html.

    Das angegebene Template wird direkt in den {% block inner %} von content.html
    eingebunden. Der volle Render-Context (entries, pagination, …) steht zur Verfügung.
    """

    type: str = "custom"
    template: str = ""  # z.B. "activity_log/partials/body.html"


# Type-Alias
Content = ContentTable | ContentColumns | ContentMetricsGrid | ContentCustom
