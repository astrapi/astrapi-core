"""
tests/test_hosts_toggle.py – Testet das Aktivieren und Deaktivieren eines Hosts.

Der Zustand eines Hosts wird über das Feld 'enabled' gesteuert.
core.ui.storage.YamlStorage.toggle() schaltet dieses Feld um.
"""
import pytest
from pathlib import Path

from core.ui.storage import YamlStorage


@pytest.fixture(autouse=True)
def tmp_storage(tmp_path):
    """Initialisiert den Storage mit einem temporären Verzeichnis und räumt danach auf."""
    YamlStorage.init(tmp_path)
    yield tmp_path
    YamlStorage.reset()


@pytest.fixture
def hosts_store():
    return YamlStorage("hosts")


@pytest.fixture
def host_entry(hosts_store):
    """Legt einen Host-Eintrag an, der standardmäßig aktiviert ist."""
    hosts_store.create("server-01", {
        "description": "Test-Server",
        "ip": "192.168.1.1",
        "port": 22,
        "enabled": True,
    })
    return hosts_store


class TestHostToggle:
    def test_host_ist_initial_aktiv(self, host_entry):
        host = host_entry.get("server-01")
        assert host["enabled"] is True

    def test_host_deaktivieren(self, host_entry):
        new_state = host_entry.toggle("server-01")
        assert new_state is False
        assert host_entry.get("server-01")["enabled"] is False

    def test_host_reaktivieren(self, host_entry):
        host_entry.toggle("server-01")   # → False
        new_state = host_entry.toggle("server-01")  # → True
        assert new_state is True
        assert host_entry.get("server-01")["enabled"] is True

    def test_toggle_persistiert_in_yaml(self, host_entry, tmp_path):
        host_entry.toggle("server-01")  # → False

        # Neuen Storage auf dieselbe Datei zeigen lassen → Zustand muss erhalten sein
        store2 = YamlStorage("hosts")
        assert store2.get("server-01")["enabled"] is False

    def test_toggle_nicht_vorhandener_host_wirft_key_error(self, hosts_store):
        with pytest.raises(KeyError):
            hosts_store.toggle("nicht-vorhanden")

    def test_check_hosts_ignoriert_deaktivierten_host(self, host_entry, monkeypatch):
        """check_hosts() soll deaktivierte Hosts überspringen."""
        host_entry.toggle("server-01")  # Host deaktivieren

        # storage.store muss auf unsere Test-Instanz zeigen
        import app.modules.hosts.storage as hosts_storage_module
        monkeypatch.setattr(hosts_storage_module, "store", host_entry)

        contacted = []

        import socket
        original_cc = socket.create_connection
        def fake_connect(address, timeout=None):
            contacted.append(address)
            return original_cc(address, timeout)

        monkeypatch.setattr(socket, "create_connection", fake_connect)

        from app.modules.hosts.jobs import check_hosts
        check_hosts()

        assert contacted == [], "Deaktivierter Host darf nicht kontaktiert werden"
