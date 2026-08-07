"""Regressionsschutz fuer T-054/T-052: stdin-Weg von run_cmd_remote()/run_cmd_local().

Kein Geheimnis darf in argv landen; stdin=None darf das bisherige Verhalten
nicht veraendern.
"""

from unittest.mock import patch

from astrapi_core.system.cmd import run_cmd_local, run_cmd_remote


def _fake_completed(args, **kwargs):
    class _Result:
        returncode = 0
        stdout = ""
        stderr = ""

    return _Result()


def test_run_cmd_local_ohne_stdin_bleibt_unveraendert():
    with patch("astrapi_core.system.cmd.subprocess.run") as mock_run:
        mock_run.side_effect = _fake_completed
        run_cmd_local("echo hi")
        _, kwargs = mock_run.call_args
        assert kwargs["input"] is None


def test_run_cmd_local_stdin_wird_als_input_uebergeben():
    with patch("astrapi_core.system.cmd.subprocess.run") as mock_run:
        mock_run.side_effect = _fake_completed
        run_cmd_local("echo hi", stdin="geheim")
        _, kwargs = mock_run.call_args
        assert kwargs["input"] == "geheim"


def test_run_cmd_remote_hat_keinen_env_parameter_mehr():
    """run_cmd_remote() darf kein env mehr annehmen -- SSH leitet es ohnehin
    nicht weiter, ein solcher Parameter wuerde nur falsche Sicherheit
    vortaeuschen (T-054)."""
    import inspect

    params = inspect.signature(run_cmd_remote).parameters
    assert "env" not in params


def test_run_cmd_remote_secret_landet_nicht_in_argv():
    """Das eigentliche Ziel von T-052: ein per stdin uebergebenes Geheimnis
    darf nirgends in der an subprocess.run() gehenden argv-Liste auftauchen."""
    with patch("astrapi_core.system.cmd.subprocess.run") as mock_run:
        mock_run.side_effect = _fake_completed
        run_cmd_remote("BORG_PASSPHRASE_FD=0 borg info /repo", "user@host",
                        stdin="super-geheimes-passwort")
        args, kwargs = mock_run.call_args
        final_cmd = args[0]
        assert "super-geheimes-passwort" not in " ".join(final_cmd)
        assert kwargs["input"] == "super-geheimes-passwort"
