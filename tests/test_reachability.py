"""Regressionsschutz fuer T-051: ssh_port wird jetzt durchgereicht statt verworfen."""

from unittest.mock import patch

from astrapi_core.system.reachability import check_ssh, require_hosts


def _fake_ok(args, **kwargs):
    class _Result:
        returncode = 0
        stdout = "ok"
        stderr = ""

    return _Result()


def test_check_ssh_ohne_port_bleibt_unveraendert():
    with patch("astrapi_core.system.reachability.subprocess.run") as mock_run:
        mock_run.side_effect = _fake_ok
        check_ssh("host", "user")
        args, _ = mock_run.call_args
        assert "-p" not in args[0]


def test_check_ssh_nicht_standard_port_wird_durchgereicht():
    with patch("astrapi_core.system.reachability.subprocess.run") as mock_run:
        mock_run.side_effect = _fake_ok
        check_ssh("host", "user", ssh_port=2222)
        args, _ = mock_run.call_args
        cmd = args[0]
        assert "-p" in cmd
        assert cmd[cmd.index("-p") + 1] == "2222"


def test_require_hosts_akzeptiert_weiterhin_2er_tupel():
    """Bestehende Aufrufer (borg, rsync, proxmox_client) uebergeben (host, user)
    ohne Port -- muss unveraendert funktionieren."""
    with patch("astrapi_core.system.reachability.check_ssh", return_value=True) as mock_check:
        assert require_hosts([("host", "user")]) is True
        mock_check.assert_called_once_with("host", "user", ssh_port=None)


def test_require_hosts_reicht_3er_tupel_port_durch():
    with patch("astrapi_core.system.reachability.check_ssh", return_value=True) as mock_check:
        assert require_hosts([("host", "user", 2222)]) is True
        mock_check.assert_called_once_with("host", "user", ssh_port=2222)
