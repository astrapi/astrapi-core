"""modules/settings/ui/__init__.py::settings_save_module() -- der neue
'tags'-Feldtyp (Badges statt Zeilen, siehe module_card.html) sendet
dasselbe {key}_0, {key}_1, ...-Formular-Format wie der bestehende
'list'-Typ und muss beim Parsen identisch behandelt werden -- sonst
zerfaellt der Wert beim Speichern in einzelne module.{mod}.{key}_0/_1/...
-Eintraege statt in EINE Liste unter module.{mod}.{key}."""
import asyncio
from unittest.mock import MagicMock, patch

import pytest
from starlette.datastructures import FormData

from astrapi_core.modules.settings.ui import settings_save_module
from astrapi_core.ui import module_registry


@pytest.fixture(autouse=True)
def _isolated_registry():
    """ModuleRegistry.reset() ist genau fuer diesen Zweck vorgesehen
    (siehe Docstring der Klasse)."""
    module_registry._instance.reset()
    yield
    module_registry._instance.reset()


class _FakeRequest:
    def __init__(self, items: list[tuple[str, str]]):
        self._form = FormData(items)

    async def form(self):
        return self._form


def _run(coro):
    return asyncio.run(coro)


def _register(key: str, schema: list[dict]):
    mod = MagicMock()
    mod.settings_schema = schema
    mod.label = "Test"
    mod.settings_order = 0
    module_registry._instance.update({key: mod})


def test_tags_feld_wird_wie_list_zu_einer_liste_zusammengefasst():
    _register("hosts", [{"key": "hidden_names", "type": "tags"}])

    with patch("astrapi_core.ui.settings_registry.set_many") as mock_set_many, \
         patch("astrapi_core.modules.settings.ui.render", return_value="ok"):
        _run(
            settings_save_module(
                "hosts",
                _FakeRequest([("hidden_names_0", "sshd"), ("hidden_names_1", "systemd-*")]),
            )
        )

    saved = mock_set_many.call_args[0][0]
    assert saved["module.hosts.hidden_names"] == ["sshd", "systemd-*"]
    assert "hidden_names_0" not in saved
    assert "hidden_names_1" not in saved


def test_list_feld_weiterhin_unveraendert_unterstuetzt():
    """Regressionsschutz: der bestehende 'list'-Typ (z.B. astrapi-backups
    default_sources) darf durch die 'tags'-Ergaenzung nicht brechen."""
    _register("proxmox_client", [{"key": "sources", "type": "list"}])

    with patch("astrapi_core.ui.settings_registry.set_many") as mock_set_many, \
         patch("astrapi_core.modules.settings.ui.render", return_value="ok"):
        _run(
            settings_save_module(
                "proxmox_client",
                _FakeRequest([("sources_0", "etc.pxar:/etc"), ("sources_1", "home.pxar:/home")]),
            )
        )

    saved = mock_set_many.call_args[0][0]
    assert saved["module.proxmox_client.sources"] == ["etc.pxar:/etc", "home.pxar:/home"]
