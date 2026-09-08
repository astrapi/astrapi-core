"""system/auth_invites.py -- In-Memory-TTL-Store für Nutzer-Einladungen,
1:1 das Muster aus astrapi_sync/modules/devices/pairing_store.py."""
from unittest.mock import patch

from astrapi_core.system import auth_invites


def setup_function():
    auth_invites._pending.clear()


def test_create_and_peek_invite_token():
    token = auth_invites.create_invite_token(invited_by_user_id=1)
    info = auth_invites.peek_invite_token(token)
    assert info["invited_by_user_id"] == 1


def test_peek_ist_nicht_destruktiv():
    token = auth_invites.create_invite_token(invited_by_user_id=1)
    auth_invites.peek_invite_token(token)
    assert auth_invites.peek_invite_token(token) is not None


def test_redeem_ist_destruktiv():
    token = auth_invites.create_invite_token(invited_by_user_id=1)
    auth_invites.redeem_invite_token(token)
    assert auth_invites.redeem_invite_token(token) is None


def test_unbekannter_token_ist_none():
    assert auth_invites.peek_invite_token("nie-erzeugt") is None
    assert auth_invites.redeem_invite_token("nie-erzeugt") is None


def test_abgelaufener_token_wird_bereinigt():
    with patch("astrapi_core.system.auth_invites.time.time", return_value=1_000_000_000):
        token = auth_invites.create_invite_token(invited_by_user_id=1)
    with patch("astrapi_core.system.auth_invites.time.time", return_value=1_000_000_000 + 700):
        assert auth_invites.peek_invite_token(token) is None


def test_attach_user_verknuepft_user_id_mit_dem_token():
    token = auth_invites.create_invite_token(invited_by_user_id=1)
    auth_invites.attach_user(token, user_id=42)
    info = auth_invites.redeem_invite_token(token)
    assert info["user_id"] == 42


def test_attach_user_auf_unbekannten_token_tut_nichts():
    # Darf nicht werfen -- z.B. wenn der Token zwischen /options und dem
    # attach()-Aufruf abgelaufen ist.
    auth_invites.attach_user("nie-erzeugt", user_id=1)
