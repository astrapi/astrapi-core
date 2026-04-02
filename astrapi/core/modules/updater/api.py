# core/modules/updater/api.py
from fastapi import APIRouter
from . import engine

router = APIRouter()


@router.get("/")
def get_status():
    status = engine.get_status()
    if not status["packages"]:
        status["packages"] = engine.get_packages_with_versions()
    return status


@router.post("/check")
def check():
    packages = engine.check_updates()
    return {"packages": packages}


@router.post("/update")
def update():
    started = engine.run_update()
    return {"started": started}
