# core/modules/activity_log/ui/routes.py
import json

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
    fmt_bytes,
    fmt_duration,
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


def _content_ctx(request: Request) -> dict:
    try:
        page = max(1, int(request.query_params.get("page", 1)))
    except ValueError:
        page = 1
    fkw = _filter_kwargs(request)
    total = count_activity(**fkw)
    pagination = build_pagination(total, page)
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
        "partials/confirm_modal.html",
        dict(
            description="Alle Activity-Log-Einträge",
            verb="löschen",
            confirm_url=f"/api/{KEY}/clear",
            method="delete",
            container_id=f"mod-{KEY}",
            loading_id=f"{KEY}-loading",
        ),
    )


@router.get(f"/ui/{KEY}/content", response_class=HTMLResponse)
def content(request: Request):
    return render(request, "content.html", _content_ctx(request))


@router.get(f"/ui/{KEY}/{{log_id}}/detail", response_class=HTMLResponse)
def detail(request: Request, log_id: int):
    entry = get_activity_log(log_id)
    if not entry:
        return HTMLResponse("<div>Log-Eintrag nicht gefunden</div>")
    entry["duration_fmt"] = fmt_duration(entry.get("duration_s"))
    entry["bytes_fmt"] = fmt_bytes(entry.get("bytes_processed"))
    if entry.get("metadata"):
        try:
            entry["metadata_dict"] = json.loads(entry["metadata"])
        except Exception:
            entry["metadata_dict"] = {}
    return render(
        request,
        "activity_log/dialogs/detail/modal.html",
        {"entry": entry},
    )


@router.get(f"/ui/{KEY}/{{log_id}}/log", response_class=HTMLResponse)
def log_viewer(request: Request, log_id: int):
    entry = get_activity_log(log_id)
    if not entry:
        return HTMLResponse("<div>Log nicht gefunden</div>")
    lines = get_log_lines(log_id)
    full_log = (
        "\n".join(f"[{r['level']}] {r['line']}" for r in lines)
        if lines
        else entry.get("full_log", "")
    )
    return render(
        request,
        "activity_log/dialogs/log_viewer/modal.html",
        {"entry": entry, "full_log": full_log},
    )
