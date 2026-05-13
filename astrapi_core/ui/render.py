# core/ui/render.py
#
# Globaler Context + render()-Helper für FastAPI-HTML-Responses.
# Ersetzt Flask's render_template() + context_processor-Mechanismus.
#
# Ablauf:
#   1. app.py konfiguriert einmalig eine Context-Funktion via configure()
#   2. Jede UI-Route ruft render(request, template, ctx) auf
#   3. render() mischt den globalen Context mit dem lokalen ctx zusammen

from typing import Callable

_ctx_fn: Callable[[], dict] | None = None


def configure(ctx_fn: Callable[[], dict]) -> None:
    """Registriert die globale Context-Funktion. Wird von app.py aufgerufen."""
    global _ctx_fn
    _ctx_fn = ctx_fn


def render(request, template: str, ctx: dict | None = None, *, status_code: int = 200):
    """Rendert ein Template mit globalem + lokalem Context.

    Entspricht Flask's render_template() kombiniert mit context_processor.
    Globaler Context (app_name, modules, nav_items, …) wird automatisch
    eingefügt – keine manuelle Übergabe notwendig.

    url_for-Kompatibilität: Flask nutzt `filename=`, Starlette nutzt `path=`.
    Der Wrapper übersetzt automatisch, sodass bestehende Templates unverändert
    bleiben können.
    """
    from .fastapi_templates import get_templates

    base: dict = _ctx_fn() if _ctx_fn is not None else {}
    if ctx:
        base.update(ctx)

    # Flask-kompatibler url_for-Wrapper: 'filename' → 'path' für static-Route
    def _url_for(name: str, **path_params) -> str:
        if name == "static" and "filename" in path_params:
            path_params["path"] = path_params.pop("filename")
        return str(request.url_for(name, **path_params))

    base["url_for"] = _url_for

    return get_templates().TemplateResponse(request, template, base, status_code=status_code)


def render_string(request, template: str, ctx: dict | None = None) -> str:
    """Rendert ein Template zu einem String (kein Response-Objekt).

    Identisch zu render(), aber gibt den gerenderten HTML-String zurück.
    Nützlich um Partials server-seitig in einen anderen Template-Context einzubetten.
    """
    from .fastapi_templates import get_templates

    base: dict = _ctx_fn() if _ctx_fn is not None else {}
    if ctx:
        base.update(ctx)

    def _url_for(name: str, **path_params) -> str:
        if name == "static" and "filename" in path_params:
            path_params["path"] = path_params.pop("filename")
        return str(request.url_for(name, **path_params))

    base["url_for"] = _url_for
    base["request"] = request

    return get_templates().env.get_template(template).render(base)


def render_toast_badge(request, ok: bool, msg: str):
    """Rendert ein floating Toast-Badge (oben mittig, auto-dismiss nach 4s).

    Für Test/Ping-Aktionen in beliebigen Modulen. Das Badge wird via HTMX
    mit hx-swap="beforeend" in den body eingefügt und verschwindet automatisch.

    Verwendung in einem Modul-Router::

        from astrapi_core.ui.render import render_toast_badge

        @router.post("/ui/mymodule/{item_id}/test")
        def test_item(item_id: str, request: Request):
            ok, msg = _do_test(item_id)
            return render_toast_badge(request, ok, msg)
    """
    return render(request, "partials/toast_badge.html", {"ok": ok, "msg": msg, "toast": True})
