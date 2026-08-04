# core/modules/activity_log/ui/routes.py
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
)

router = APIRouter(tags=[KEY])


def _filter_kwargs(request: Request) -> dict:
    p = request.query_params
    return dict(
        log_type=p.get("log_type") or None,
        module=p.get("module") or None,
        status=p.get("status") or None,
        date_from=parse_date_range(p.get("date_range", "30d")),
        search=p.get("search") or None,
    )


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
