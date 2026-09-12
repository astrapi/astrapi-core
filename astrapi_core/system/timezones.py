# astrapi_core/system/timezones.py
"""IANA-Zeitzonen nach Region gruppiert -- fuer Region/Stadt-Dropdown-
Paare in Settings-Feldern (astrapi-admin T-321-ADMIN: Zeitzone als
globales Agent-Setting, ohne Freitext-Risiko)."""
from zoneinfo import available_timezones


def grouped_timezones() -> dict[str, list[str]]:
    """{Region: [voller IANA-Name, ...]}, Regionen und Zonen je
    alphabetisch sortiert. Nur der moderne Area/Location-Schema
    (z.B. "Europe/Berlin", "America/Argentina/Buenos_Aires") plus "UTC"
    -- veraltete Alias-Namen ohne "/" (z.B. "US/Eastern", "GMT",
    "Factory") werden ausgelassen, sie verweisen ohnehin nur auf
    denselben Zeitpunkt wie ein kanonischer Name und wuerden die Liste
    nur mit Duplikaten aufblaehen."""
    groups: dict[str, list[str]] = {"UTC": ["UTC"]}
    for tz in available_timezones():
        if tz == "UTC" or "/" not in tz:
            continue
        region = tz.split("/", 1)[0]
        groups.setdefault(region, []).append(tz)
    return {region: sorted(zones) for region, zones in sorted(groups.items())}
