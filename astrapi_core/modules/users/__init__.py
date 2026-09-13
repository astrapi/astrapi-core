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
Nutzer anzulegen).

Liste/Tabelle laufen über das normale deklarative ContentTable-System
(wie hosts/devices/folders) statt über ein eigenes content.html -- Header,
Tabellenkopf, Zeilen und Drei-Punkte-Menü kommen damit aus
list_wrapper_inner.html wie bei jedem anderen Modul. has_edit/has_delete/
has_toggle sind aus, weil es dafür keine generischen Aktionen gibt
(kein Bearbeiten-Dialog; Löschen/Passkey-Reset/Einladen sind admin-gated
und brauchen eigene Business-Regeln) -- die drei echten Zeilen-Aktionen
kommen stattdessen über extra_actions_template (ui/__init__.py::_ctx()),
das list_wrapper_inner.html schon für genau diesen Zweck vorsieht."""
from pathlib import Path

from astrapi_core.ui.controls import Col, ContentTable
from astrapi_core.ui.module_loader import load_modul

_KEY = Path(__file__).parent.name

from .ui import router as ui_router  # noqa: E402

module = load_modul(
    Path(__file__).parent,
    _KEY,
    None,
    ui_router,
    # ui_header=None (nicht Header([])) -- nur so fällt content.html in den
    # "kein deklaratives Header"-Zweig, der extra_page_actions_template
    # einbindet (siehe _ctx() in ui/__init__.py): der "Neu"-Button lebt damit
    # im echten Seiten-Header wie bei jedem anderen Modul, bleibt aber
    # per current_user.is_admin bedingt -- ein statisches Header([...])
    # kennt "nur für Admins sichtbar" nicht.
    ui_header=None,
    ui_content=ContentTable(
        has_run_buttons=False,
        has_status=False,
        has_create=False,
        has_edit=False,
        has_delete=False,
        has_toggle=False,
        columns=[
            Col.mono("username", "Benutzername"),
            Col.badge_enum(
                "role",
                "Rolle",
                {
                    "admin": {"label": "Administrator", "cls": "badge-blue"},
                    "user": {"label": "Nutzer", "cls": "badge-grey"},
                },
                css="col-type",
            ),
            Col.dot_text("credential_display", "Passkey", category_key="credential_category", css="col-info"),
        ],
    ),
)
