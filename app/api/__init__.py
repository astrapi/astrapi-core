"""
app/api/__init__.py  –  API-Einstiegspunkt

Zwei Modi:

  Flask-only (main_flask.py):
    register(flask_app) wird vom Framework automatisch aufgerufen.
    Hier Flask-Routen als JSON-Endpunkte registrieren.

  FastAPI+Flask (main.py):
    fastapi_app.py / routers/ übernehmen die API.
    register() wird in diesem Modus NICHT aufgerufen.
"""


def register(app) -> None:
    """Flask-only: JSON-API-Endpunkte direkt an Flask registrieren.

    Wird automatisch vom Framework aufgerufen wenn main_flask.py verwendet wird.
    Im FastAPI-Modus (main.py) ist diese Funktion nicht aktiv –
    dort übernehmen app/api/fastapi_app.py und app/api/routers/ die API.
    """
    from flask import jsonify

    @app.route("/api/items", methods=["GET"])
    def api_items_list():
        return jsonify({"items": [], "total": 0})

    @app.route("/api/items/<item_id>", methods=["GET"])
    def api_items_get(item_id: str):
        return jsonify({"id": item_id})

    @app.route("/api/items/<item_id>/toggle", methods=["POST"])
    def api_items_toggle(item_id: str):
        return jsonify({"id": item_id, "toggled": True})

    @app.route("/api/items/<item_id>/delete", methods=["DELETE"])
    def api_items_delete(item_id: str):
        return jsonify({"id": item_id, "deleted": True})

    @app.route("/api/health", methods=["GET"])
    def api_health():
        return jsonify({"status": "ok"})
