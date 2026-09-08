# core/system/auth_invites.py
"""In-Memory-Speicher für kurzlebige Nutzer-Einladungs-Tokens.

1:1 das Muster aus astrapi_sync/modules/devices/pairing_store.py, hier
generisch in astrapi-core (wiederverwendbar für jede App, die
`app.yaml: auth.multi_user: true` setzt). Bewusst nicht in der DB:
Einladungs-Tokens sind einmalig, laufen nach 10 Minuten ab und müssen
keinen Neustart überleben.

Zwei Zugriffsarten: peek (nicht-destruktiv, für die GET-Einladungsseite --
zeigt "wer lädt dich ein" ohne den Token schon zu verbrauchen) und redeem
(destruktiv, beim finalen POST /verify)."""
import secrets
import time

_TTL_SECONDS = 600

# token -> {"created_at": float, "invited_by_user_id": int, "user_id": int optional}
_pending: dict[str, dict] = {}


def create_invite_token(invited_by_user_id: int, existing_user_id: "int | None" = None) -> str:
    """existing_user_id: statt einen neuen Nutzer anzulegen, wird die
    Passkey-Registrierung an eine BESTEHENDE user_id gebunden -- Nutzung:
    Passkey zurücksetzen (modules/users), z.B. nach einer abgebrochenen
    Erst-Registrierung, die eine credential-lose User-Zeile hinterlassen
    hat, oder nach Geräteverlust."""
    _cleanup()
    token = secrets.token_urlsafe(24)
    entry = {"created_at": time.time(), "invited_by_user_id": invited_by_user_id}
    if existing_user_id is not None:
        entry["user_id"] = existing_user_id
    _pending[token] = entry
    return token


def peek_invite_token(token: str) -> dict | None:
    """Nicht-destruktiv -- für die GET-Seite, die die Einladung anzeigt,
    bevor tatsächlich registriert wird."""
    _cleanup()
    return _pending.get(token)


def attach_user(token: str, user_id: int) -> None:
    """Verknüpft den während /options bereits angelegten Nutzer mit dem
    Token, damit /verify (nach redeem_invite_token()) weiß, welche
    User-Zeile gerade ihre Passkey fertig registriert."""
    if token in _pending:
        _pending[token]["user_id"] = user_id


def redeem_invite_token(token: str) -> dict | None:
    """Entfernt den Token (Einmal-Nutzung) und gibt seine Metadaten zurück,
    oder None wenn er ungültig/abgelaufen ist."""
    _cleanup()
    return _pending.pop(token, None)


def _cleanup() -> None:
    now = time.time()
    expired = [t for t, meta in _pending.items() if now - meta["created_at"] > _TTL_SECONDS]
    for t in expired:
        _pending.pop(t, None)


def ttl_seconds() -> int:
    return _TTL_SECONDS
