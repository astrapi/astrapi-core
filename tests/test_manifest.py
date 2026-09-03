"""system/manifest.py::register_manifest() -- PWA-Installierbarkeit unter
Android/Chrome. Generisch: Name/Icon kommen als Parameter rein (echte
app.yaml-Anbindung siehe ui/app.py::create() + test_version_auth_config.py)."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from astrapi_core.system.manifest import register_manifest


def test_manifest_liefert_pflichtfelder_fuer_installierbarkeit():
    app = FastAPI()
    register_manifest(app, "Test-App", None)
    r = TestClient(app).get("/manifest.json")

    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Test-App"
    assert body["display"] == "standalone"
    assert body["start_url"] == "/"
    assert len(body["icons"]) == 1
    assert body["icons"][0]["type"] == "image/svg+xml"


def test_manifest_ohne_icon_svg_nutzt_default_icon():
    app = FastAPI()
    register_manifest(app, "Test-App", None)
    r = TestClient(app).get("/manifest.json")
    assert r.json()["icons"][0]["src"].startswith("data:image/svg+xml,")


def test_manifest_nutzt_eigenes_icon_svg():
    app = FastAPI()
    register_manifest(app, "Test-App", "data:image/svg+xml,<svg>eigenes</svg>")
    r = TestClient(app).get("/manifest.json")
    assert r.json()["icons"][0]["src"] == "data:image/svg+xml,<svg>eigenes</svg>"
