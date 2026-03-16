"""
tests/test_version.py – Tests für core.system.version
"""
from pathlib import Path
import tempfile
import yaml

import pytest

from core.system.version import get_app_version, get_core_version, _read_yaml_version

CORE_ROOT = Path(__file__).resolve().parents[1] / "core"
APP_ROOT  = Path(__file__).resolve().parents[1] / "app"


# ── Hilfsfunktion ────────────────────────────────────────────────────────────

def _write_version_yaml(directory: Path, version: str) -> Path:
    """Schreibt eine temporäre version.yaml in das angegebene Verzeichnis."""
    path = directory / "version.yaml"
    path.write_text(yaml.dump({"version": version}), encoding="utf-8")
    return path


# ── Tests ────────────────────────────────────────────────────────────────────

class TestReadYamlVersion:
    def test_liest_vorhandene_version(self, tmp_path):
        _write_version_yaml(tmp_path, "26.3.1")
        assert _read_yaml_version(tmp_path / "version.yaml") == "26.3.1"

    def test_gibt_default_zurück_wenn_datei_fehlt(self, tmp_path):
        result = _read_yaml_version(tmp_path / "missing.yaml", default="0.0.0")
        assert result == "0.0.0"

    def test_gibt_default_zurück_wenn_key_fehlt(self, tmp_path):
        path = tmp_path / "version.yaml"
        path.write_text(yaml.dump({"other_key": "irrelevant"}), encoding="utf-8")
        result = _read_yaml_version(path, default="n/a")
        assert result == "n/a"


class TestGetAppVersion:
    def test_liest_echte_app_version(self):
        version = get_app_version(APP_ROOT)
        # Version muss dem Schema JAHR.MONAT.NUMMER entsprechen oder "—" sein
        assert version == "—" or len(version.split(".")) == 3

    def test_gibt_default_zurück_wenn_kein_app_root(self, tmp_path):
        result = get_app_version(tmp_path, default="fallback")
        assert result == "fallback"


class TestGetCoreVersion:
    def test_liest_echte_core_version(self):
        version = get_core_version(CORE_ROOT)
        assert version == "—" or len(version.split(".")) == 3

    def test_gibt_default_zurück_wenn_kein_core_root(self, tmp_path):
        result = get_core_version(tmp_path, default="fallback")
        assert result == "fallback"
