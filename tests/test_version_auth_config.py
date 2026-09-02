"""system/version.py::get_auth_config() -- insbesondere password_fallback,
das per Default True bleibt (Rueckwaertskompatibilitaet fuer Apps ohne
HTTPS) und von einer App gezielt auf false gestellt werden kann."""
from astrapi_core.system.version import get_auth_config


def _write_app_yaml(tmp_path, auth_block: str) -> None:
    (tmp_path / "app.yaml").write_text(f"name: test-app\n{auth_block}\n", encoding="utf-8")


def test_password_fallback_default_true_ohne_app_yaml(tmp_path):
    cfg = get_auth_config(tmp_path)
    assert cfg["password_fallback"] is True


def test_password_fallback_default_true_wenn_nicht_gesetzt(tmp_path):
    _write_app_yaml(tmp_path, "auth:\n  enabled: true\n")
    cfg = get_auth_config(tmp_path)
    assert cfg["password_fallback"] is True


def test_password_fallback_explizit_deaktiviert(tmp_path):
    _write_app_yaml(tmp_path, "auth:\n  enabled: true\n  password_fallback: false\n")
    cfg = get_auth_config(tmp_path)
    assert cfg["password_fallback"] is False
