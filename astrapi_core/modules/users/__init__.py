"""core/modules/users/__init__.py – Nutzerverwaltung für echte
Mehrbenutzer-Apps (Löschen, Passkey zurücksetzen).

Nur geladen, wenn `app.yaml: auth.multi_user: true` gesetzt ist --
system/version.py::get_disabled_modules() nimmt "users" sonst automatisch
in die Sperrliste auf (astrapi-admin, Single-Owner, bleibt unberührt).

Die eigentliche Registrierungs-/Einladungs-Zeremonie bleibt in
ui/multi_user_routes.py unter /auth/* (dort ist die eingeladene Person noch
nicht eingeloggt) -- dieses Modul ist die login-pflichtige Verwaltungsseite
darüber: Liste, Löschen, Passkey zurücksetzen (erzeugt intern einen neuen
Einladungslink, gebunden an die bestehende user_id statt einen neuen
Nutzer anzulegen)."""
from pathlib import Path

from astrapi_core.ui.controls import ContentCustom, Header
from astrapi_core.ui.module_loader import load_modul

_KEY = Path(__file__).parent.name

from .ui import router as ui_router  # noqa: E402

module = load_modul(
    Path(__file__).parent,
    _KEY,
    None,
    ui_router,
    ui_header=Header([]),
    ui_content=ContentCustom(template=f"{_KEY}/partials/content.html"),
)
