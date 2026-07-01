from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.routing import APIRouter

from .render import render

router = APIRouter()


@router.get("/ui/dev/dialog", response_class=HTMLResponse, include_in_schema=False)
def dev_dialog(request: Request, title: str = ""):
    return render(request, "dialog_core.html", {"title": title or "Test-Dialog"})


@router.get("/ui/dev/dialog/confirm", response_class=HTMLResponse, include_in_schema=False)
def dev_dialog_confirm(request: Request):
    return render(request, "dialog_confirm.html", {
        "title": "Host löschen",
        "description": "server-01",
        "verb": "löschen",
        "confirm_url": "/ui/dev/dialog/confirm/action",
        "method": "post",
    })


@router.get("/ui/dev/dialog/form", response_class=HTMLResponse, include_in_schema=False)
def dev_dialog_form(request: Request):
    return render(request, "dialog_form.html", {
        "title": "Host erstellen",
    })
