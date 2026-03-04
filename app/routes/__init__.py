"""
app/routes/__init__.py  –  Flask-Routen des Projekts

Hier werden projektspezifische Flask-Blueprints registriert.
Die Funktion register(app) wird automatisch vom Framework aufgerufen.

Beispiel – Modal-Routen für CRUD-Operationen:
  from .modals import bp as modals_bp
  app.register_blueprint(modals_bp)
"""

from flask import Flask


def register(app: Flask) -> None:
    """Registriert alle App-Blueprints an der Flask-Instanz."""

    # ── UI-Routen (Modals, CRUD-Dialoge) ─────────────────────────────────────
    # Auskommentieren und anpassen sobald eigene Modal-Routen benötigt werden:
    #
    # from .modals import bp as modals_bp
    # app.register_blueprint(modals_bp)

    # ── Weitere Blueprints ────────────────────────────────────────────────────
    # from .my_feature import bp as my_feature_bp
    # app.register_blueprint(my_feature_bp)

    pass
