"""
core/ui/page_factory.py  –  Automatische Page- und Tab-Routen

Registriert für jeden Nav-Eintrag drei Routen:

  GET /<key>               → App-Shell (index.html) mit HTMX-load-Trigger
  GET /api/ui/<key>/tab    → Tab-Partial (HTMX-Ziel)
  GET /api/ui/<key>/list   → Listen-Partial (für HTMX-Polling / Refresh)

Die URL kann in items.yaml individuell überschrieben werden.
Wird sie nicht angegeben, wird /api/ui/<key>/tab verwendet.
"""

from flask import Flask, render_template, request


# ─────────────────────────────────────────────────────────────────────────────
# View-Factories
# ─────────────────────────────────────────────────────────────────────────────

def _label(key: str, nav_items: list[dict]) -> str:
    return next(
        (it["label"] for it in nav_items if not it.get("separator") and it["key"] == key),
        key.replace("_", " ").title(),
    )


def make_page(resource_key: str, initial_url: str, nav_items: list[dict]) -> callable:
    """App-Shell-View: lädt index.html, HTMX triggert initial_url."""
    title = _label(resource_key, nav_items)

    def page():
        return render_template(
            "index.html",
            active_tab=resource_key,
            initial_content_url=initial_url,
            title=title,
        )

    page.__name__ = f"page_{resource_key}"
    return page


def make_tab(resource_key: str, nav_items: list[dict]) -> callable:
    """Tab-Partial-View: rendert partials/tab_wrapper.html."""
    title        = _label(resource_key, nav_items)
    list_partial = f"partials/lists/{resource_key}.html"

    def tab():
        return render_template(
            "partials/tab_wrapper.html",
            active_tab=resource_key,
            title=title,
            list_partial=list_partial,
            # Kontext-Variablen für list_wrapper.html (backupctl-Kompatibilität)
            module=resource_key,
            container_id=f"tab-{resource_key}",
            loading_id=f"{resource_key}-loading",
        )

    tab.__name__ = f"tab_{resource_key}"
    return tab


def make_list(resource_key: str) -> callable:
    """Listen-Partial-View: rendert nur partials/lists/<key>.html."""
    list_partial = f"partials/lists/{resource_key}.html"

    def lst():
        return render_template(list_partial)

    lst.__name__ = f"list_{resource_key}"
    return lst


# ─────────────────────────────────────────────────────────────────────────────
# Registrierung
# ─────────────────────────────────────────────────────────────────────────────

def register_pages(app: Flask, nav_items: list[dict]) -> None:
    """Registriert Page-, Tab- und List-Route für jeden Nav-Eintrag."""
    for item in nav_items:
        if item.get("separator"):
            continue

        key = item["key"]
        url = item["url"]   # z. B. /api/ui/overview/tab

        # /<key>  → App-Shell
        app.add_url_rule(
            f"/{key}",
            endpoint=f"page_{key}",
            view_func=make_page(key, url, nav_items),
        )

        # /api/ui/<key>/tab  → Tab-Partial
        app.add_url_rule(
            url,
            endpoint=f"tab_{key}",
            view_func=make_tab(key, nav_items),
        )

        # /api/ui/<key>/list  → Listen-Partial (Refresh)
        list_url = url.replace("/tab", "/list")
        if list_url != url:
            app.add_url_rule(
                list_url,
                endpoint=f"list_{key}",
                view_func=make_list(key),
            )
