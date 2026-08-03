"""
core/ui/page_factory.py  –  Automatische Page- und Content-Routen (FastAPI)

URL-Schema:
  GET /<key>              → App-Shell (index.html), rendert Content-Partial direkt server-seitig
  GET /ui/<key>/content   → Inhalt-Partial (Nav-Klick + Reload + Refresh via HTMX)

/api/... bleibt ausschließlich FastAPI (JSON).
/ui/...  HTML-Partials, Modals (FastAPI).
/<key>   ist die sichtbare Browser-URL.
"""

from typing import Callable

from fastapi import Request
from fastapi.responses import HTMLResponse

# Registry: key → fn(request) -> str
# Wird von make_crud_router befüllt; Shell-Handler nutzt es für serverseitiges Rendering.
_content_renderers: dict[str, Callable] = {}


def register_content_renderer(key: str, fn: Callable) -> None:
    """Registriert einen Content-Renderer für einen Modul-Key.

    fn muss die Signatur (request: Request) -> str haben.
    Wird von make_crud_router aufgerufen, damit der Shell-Handler den Content
    direkt server-seitig rendern kann (kein zweiter HTTP-Request nötig).
    """
    _content_renderers[key] = fn


def _label(key: str, nav_items: list[dict]) -> str:
    return next(
        (it["label"] for it in nav_items if not it.get("separator") and it["key"] == key),
        key.replace("_", " ").title(),
    )


def register_pages(
    api,
    nav_items: list[dict],
    shell_only_keys: set[str] | None = None,
) -> None:
    """Registriert Shell- und Content-Route für jeden Nav-Eintrag."""
    from astrapi_core.ui.render import render

    shell_only = shell_only_keys or set()

    for item in nav_items:
        if item.get("separator"):
            continue

        key   = item["key"]
        title = _label(key, nav_items)

        # Closure-safe Werte binden
        _key   = key
        _title = title

        def _make_shell(k, t):
            list_partial = f"partials/lists/{k}.html"

            def shell(request: Request):
                from astrapi_core.ui.render import render_string
                if k in _content_renderers:
                    initial_content = _content_renderers[k](request)
                else:
                    initial_content = render_string(request, list_partial)
                return render(request, "index.html", dict(
                    active_tab=k,
                    initial_content=initial_content,
                    title=t,
                ))
            shell.__name__ = f"shell_{k}"
            return shell

        def _make_content(k):
            list_partial = f"partials/lists/{k}.html"

            def content(request: Request):
                return render(request, list_partial)
            content.__name__ = f"content_{k}"
            return content

        api.add_api_route(
            f"/{_key}",
            _make_shell(_key, _title),
            methods=["GET"],
            response_class=HTMLResponse,
        )

        if _key not in shell_only:
            api.add_api_route(
                f"/ui/{_key}/content",
                _make_content(_key),
                methods=["GET"],
                response_class=HTMLResponse,
            )
