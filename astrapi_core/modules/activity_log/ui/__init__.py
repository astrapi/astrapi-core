# core/modules/activity_log/ui/routes.py
import re

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from astrapi_core.ui.page_factory import register_content_renderer
from astrapi_core.ui.render import render, render_string

from ..engine import (
    KEY,
    _page_size,
    build_pagination,
    clear_activity_log,
    count_activity,
    enrich,
    get_activity_log,
    get_log_lines,
    list_activity,
    parse_date_range,
    registered_modules,
)

router = APIRouter(tags=[KEY])

# Gleiche Filter wie in ui_header (siehe modules/activity_log/__init__.py) --
# dort fuer die <select>-Optionen, hier fuer filter_defs (Aktiv-Zustand fuer
# vorausgewaehlte Option + Mobile-Badge). Getrennt gehalten, analog zum
# filters=[]-Parameter von make_crud_router, der ebenfalls unabhaengig vom
# ui_header ist.
_FILTER_SPECS = [
    {
        "param": "log_type",
        "label": "Typ",
        "all_label": "Alle Typen",
        "options_fn": lambda: [
            {"value": "job", "label": "Jobs"},
            {"value": "scheduler", "label": "Scheduler"},
            {"value": "error", "label": "Errors"},
            {"value": "warning", "label": "Warnings"},
            {"value": "system", "label": "System"},
        ],
    },
    {
        "param": "module",
        "label": "Modul",
        "all_label": "Alle Module",
        "options_fn": lambda: [
            {"value": m, "label": m.replace("_", " ").title()} for m in registered_modules()
        ],
    },
    {
        "param": "status",
        "label": "Status",
        "all_label": "Alle Status",
        "options_fn": lambda: [
            {"value": "ok", "label": "OK"},
            {"value": "error", "label": "Fehler"},
            {"value": "warning", "label": "Warnung"},
            {"value": "running", "label": "Läuft"},
            {"value": "skipped", "label": "Übersprungen"},
        ],
    },
    {
        "param": "date_range",
        "label": "Zeitraum",
        "all_label": None,
        "options_fn": lambda: [
            {"value": "24h", "label": "Letzte 24h"},
            {"value": "7d", "label": "7 Tage"},
            {"value": "30d", "label": "30 Tage", "default": True},
            {"value": "", "label": "Alle"},
        ],
    },
]


def _resolve_filter_value(request: Request, param: str) -> str:
    """Query-Param hat Vorrang, sonst Cookie-Fallback -- gleiche Reihenfolge
    wie crud_blueprint.resolve_filters_for_request()."""
    val = request.query_params.get(param, "")
    if not val:
        cookie_name = re.sub(r"[^a-zA-Z0-9]", "_", f"mf_{KEY}__{param}")
        val = request.cookies.get(cookie_name, "")
    return val


def _filter_kwargs(request: Request) -> dict:
    log_type = _resolve_filter_value(request, "log_type")
    module = _resolve_filter_value(request, "module")
    status = _resolve_filter_value(request, "status")
    date_range = _resolve_filter_value(request, "date_range") or "30d"
    return dict(
        log_type=log_type or None,
        module=module or None,
        status=status or None,
        date_from=parse_date_range(date_range),
        search=request.query_params.get("search") or None,
    )


def _filter_defs(request: Request) -> list[dict]:
    return [
        {
            "param": spec["param"],
            "label": spec["label"],
            "all_label": spec.get("all_label", "Alle"),
            "active": _resolve_filter_value(request, spec["param"]),
            "options": spec["options_fn"](),
        }
        for spec in _FILTER_SPECS
    ]


def _pagination_url(request: Request, page: int) -> str:
    params = {k: v for k, v in request.query_params.items() if k != "page"}
    params["page"] = str(page)
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    return f"/ui/{KEY}/content?{qs}"


def _content_ctx(request: Request) -> dict:
    try:
        page = max(1, int(request.query_params.get("page", 1)))
    except ValueError:
        page = 1
    fkw = _filter_kwargs(request)
    total = count_activity(**fkw)
    pagination = build_pagination(total, page)
    if pagination:
        pagination["prev_url"] = _pagination_url(request, pagination["page"] - 1)
        pagination["next_url"] = _pagination_url(request, pagination["page"] + 1)
        for p in pagination["pages"]:
            p["url"] = "#" if p.get("is_ellipsis") else _pagination_url(request, p["num"])
    ps = _page_size()
    entries = enrich(
        list_activity(
            limit=ps,
            offset=(page - 1) * ps,
            **fkw,
        )
    )
    cfg = {str(e["id"]): e for e in entries}
    return dict(
        module=KEY,
        has_create=False,
        container_id=f"mod-{KEY}",
        cfg=cfg,
        pagination=pagination,
        filter_defs=_filter_defs(request),
    )


def _render_content(request) -> str:
    return render_string(request, "content.html", _content_ctx(request))


register_content_renderer(KEY, _render_content)


@router.delete(f"/api/{KEY}/clear", response_class=HTMLResponse)
def activity_log_clear(request: Request):
    clear_activity_log()
    return render(
        request,
        "content.html",
        {
            "module": KEY,
            "has_create": False,
            "container_id": f"mod-{KEY}",
            "cfg": {},
            "pagination": None,
            "filter_defs": _filter_defs(request),
        },
    )


@router.get(f"/ui/{KEY}/clear-confirm", response_class=HTMLResponse)
def clear_confirm(request: Request):
    return render(
        request,
        "dialog_confirm.html",
        dict(
            title="Löschen",
            description="Alle Activity-Log-Einträge",
            verb="löschen",
            confirm_url=f"/api/{KEY}/clear",
            method="delete",
            reload_url=f"/ui/{KEY}/content",
        ),
    )


@router.get(f"/ui/{KEY}/content", response_class=HTMLResponse)
def content(request: Request):
    return render(request, "content.html", _content_ctx(request))



@router.get(f"/ui/{KEY}/{{log_id}}/log", response_class=HTMLResponse)
def log_viewer(request: Request, log_id: int):
    entry = get_activity_log(log_id)
    if not entry:
        return HTMLResponse("<div>Log nicht gefunden</div>")
    rows = get_log_lines(log_id)
    if rows:
        lines = [f"{r['level']}: {r['line']}" for r in rows]
    else:
        # full_log ist eine echte Spalte und meist NULL – der Default von
        # dict.get() greift nur bei fehlendem Schluessel, nicht bei None.
        # Sonst landet [None] im Template und 'WARNING:' in None wirft.
        lines = [entry.get("full_log") or "(kein Log vorhanden)"]
    return render(
        request,
        "dialog_log.html",
        {
            "module": KEY,
            "item_id": log_id,
            "description": entry.get("description", str(log_id)),
            "lines": lines,
            "dates": [],
            "selected": None,
            "live": False,
        },
    )
