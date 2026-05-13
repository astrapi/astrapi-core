# core/modules/activity_log/engine.py
# Re-exports aus system.activity_log – werden von api.py und ui.py direkt importiert.
# noqa-Kommentare verhindern, dass Formatter/Linter diese als "ungenutzt" entfernen.
from astrapi_core.system.activity_log import (
    append_log_line,  # noqa: F401
    clear_activity_log,  # noqa: F401
    count_activity,  # noqa: F401
    get_activity_log,  # noqa: F401
    get_latest_activity_log_id,  # noqa: F401
    get_log_lines,  # noqa: F401
    history_finish,  # noqa: F401
    history_start,  # noqa: F401
    list_activity,  # noqa: F401
    list_history,  # noqa: F401
    list_runs_for_item,  # noqa: F401
    log_activity,  # noqa: F401
    update_activity_log,  # noqa: F401
)

KEY = "activity_log"


def fmt_duration(s: int | None) -> str:
    if s is None:
        return "—"
    if s < 60:
        return f"{s}s"
    m, sec = divmod(s, 60)
    if m < 60:
        return f"{m}m {sec}s"
    h, min_ = divmod(m, 60)
    return f"{h}h {min_}m"


from astrapi_core.system.format import fmt_bytes


def enrich(entries: list) -> list:
    for e in entries:
        e["duration_fmt"] = fmt_duration(e.get("duration_s"))
        e["bytes_fmt"] = fmt_bytes(e.get("bytes_processed"))
    return entries


def registered_modules() -> list[str]:
    try:
        from astrapi_core.ui.module_registry import _mod_registry

        return [key for key in _mod_registry if not key.startswith("_")]
    except Exception:
        return []


def _page_size() -> int:
    """Liest die konfigurierte Seitengröße aus den Settings (Default: 15)."""
    try:
        from astrapi_core.ui.settings_registry import get_page_size

        return get_page_size()
    except Exception:
        return 15


# PAGE_SIZE bleibt als Fallback-Konstante für Importe in api.py / ui.py
PAGE_SIZE = 15


def parse_date_range(date_range: str) -> str | None:
    """Wandelt einen date_range-String (24h, 7d, 30d) in ein ISO-Datumsdatum um."""
    from datetime import datetime, timedelta

    if date_range == "24h":
        return (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    if date_range == "7d":
        return (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    if date_range == "30d":
        return (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    return None


def build_pagination(total: int, page: int) -> dict | None:
    """Baut ein Pagination-Dict für Activity-Log-Templates."""
    ps = _page_size()
    total_pages = max(1, (total + ps - 1) // ps)
    page = min(max(1, page), total_pages)
    if total_pages <= 1:
        return None

    def _page_range(cur: int, tot: int) -> list:
        if tot <= 7:
            return list(range(1, tot + 1))
        pages: list = [1]
        if cur > 3:
            pages.append("…")
        for p in range(max(2, cur - 1), min(tot, cur + 2)):
            pages.append(p)
        if cur < tot - 2:
            pages.append("…")
        if tot > 1:
            pages.append(tot)
        return pages

    return {
        "page": page,
        "page_size": ps,
        "total": total,
        "total_pages": total_pages,
        "has_prev": page > 1,
        "has_next": page < total_pages,
        "prev_page": page - 1,
        "next_page": page + 1,
        "pages": [
            {"num": p, "active": p == page, "is_ellipsis": p == "…"}
            for p in _page_range(page, total_pages)
        ],
        "start": (page - 1) * ps + 1,
        "end": min(page * ps, total),
    }
