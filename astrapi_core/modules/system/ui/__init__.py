"""core/modules/system/ui.py – FastAPI-Router für System-UI (Sysinfo + Updater)."""

import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, StreamingResponse

from astrapi_core.ui.render import render

from ..engine import (
    check_updates as _check_updates,
)
from ..engine import (
    collect,
)
from ..engine import (
    get_status as _get_status,
)
from ..engine import (
    run_update as _run_update,
)

KEY = "system"
router = APIRouter()


def _render_content(request) -> str:
    from astrapi_core.ui.render import render_string

    return render_string(
        request,
        "content.html",
        {
            "module": KEY,
            "has_create": False,
            "container_id": f"mod-{KEY}",
            "info": collect(),
        },
    )


from astrapi_core.ui.page_factory import register_content_renderer

register_content_renderer(KEY, _render_content)


@router.get(f"/ui/{KEY}/content", response_class=HTMLResponse)
def system_content(request: Request):
    return render(
        request,
        "content.html",
        {
            "module": KEY,
            "has_create": False,
            "container_id": f"mod-{KEY}",
            "info": collect(),
        },
    )


@router.get(f"/ui/{KEY}/metrics", response_class=HTMLResponse)
def system_metrics(request: Request):
    return render(request, f"{KEY}/partials/content.html", {"info": collect()})


@router.post(f"/ui/{KEY}/check", response_class=HTMLResponse)
def system_check(request: Request):
    _check_updates()
    return render(request, f"{KEY}/partials/content.html", {"info": collect()})


@router.post(f"/ui/{KEY}/update", response_class=HTMLResponse)
def system_update(request: Request):
    _run_update()
    response = render(request, f"{KEY}/partials/content.html", {"info": collect()})
    response.headers["HX-Trigger"] = '{"openLogModal": {"module": "system", "itemId": "update"}}'
    return response


@router.get(f"/api/{KEY}/update/logs", response_class=HTMLResponse)
def system_update_logs(request: Request, live: int = 0):
    from astrapi_core.system.activity_log import get_log_lines, list_runs_for_item

    runs = list_runs_for_item(KEY, "update")
    act_log_id = runs[0]["id"] if runs else None
    lines = [r["line"] for r in get_log_lines(act_log_id)] if act_log_id else []
    dates = [{"id": str(r["id"]), "label": r["started_at"] or str(r["id"])} for r in runs]
    return render(
        request,
        "partials/log_modal.html",
        {
            "module": KEY,
            "item_id": "update",
            "description": "System-Update",
            "dates": dates,
            "selected": str(act_log_id) if act_log_id else None,
            "lines": lines,
            "live": bool(live),
        },
    )


@router.get(f"/api/{KEY}/update/logs/stream")
async def system_update_logs_stream():
    from astrapi_core.system.activity_log import get_latest_activity_log_id, get_log_lines

    async def event_generator():
        act_log_id = None
        waited = 0.0
        while act_log_id is None and waited < 15:
            act_log_id = get_latest_activity_log_id(KEY, "update")
            if act_log_id is None:
                await asyncio.sleep(0.3)
                waited += 0.3

        if act_log_id is None:
            yield "event: done\ndata: \n\n"
            return

        last_id = 0
        idle_after_done = 0.0

        while True:
            rows = get_log_lines(act_log_id, after_id=last_id)
            for row in rows:
                last_id = row["id"]
                level = row["level"].lower()
                safe = row["line"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                yield f'data: <div class="log-line log-{level}">{safe}</div>\n\n'

            st = _get_status()
            still_running = st["status"] == "running"

            if not still_running:
                idle_after_done += 0.5
                if idle_after_done >= 3:
                    yield "event: done\ndata: \n\n"
                    return
            else:
                idle_after_done = 0.0

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
