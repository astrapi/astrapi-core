"""system/timezones.py -- T-321-ADMIN: Region/Stadt-Gruppierung fuer das
Zeitzone-Dropdown, ohne veraltete Alias-Namen ohne '/'."""
from astrapi_core.system.timezones import grouped_timezones


def test_grouped_timezones_enthaelt_bekannte_region():
    groups = grouped_timezones()
    assert "Europe/Berlin" in groups["Europe"]


def test_grouped_timezones_utc_eigene_pseudo_region():
    groups = grouped_timezones()
    assert groups["UTC"] == ["UTC"]


def test_grouped_timezones_keine_alias_namen_ohne_slash():
    groups = grouped_timezones()
    for region, zones in groups.items():
        if region == "UTC":
            continue
        for zone in zones:
            assert "/" in zone


def test_grouped_timezones_regionen_und_zonen_sortiert():
    groups = grouped_timezones()
    assert list(groups.keys()) == sorted(groups.keys())
    assert groups["Europe"] == sorted(groups["Europe"])


def test_grouped_timezones_mehrteilige_zone_landet_unter_erster_region():
    groups = grouped_timezones()
    assert "America/Argentina/Buenos_Aires" in groups["America"]
