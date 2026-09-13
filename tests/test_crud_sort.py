"""crud_blueprint.py::apply_sort() -- serverseitiges Sortieren per
?sort=<key>&dir=asc|desc (T-323-CORE), ersetzt fuer Col.sortable-Spalten
den bisherigen rein clientseitigen DOM-Sort."""
from starlette.requests import Request

from astrapi_core.ui.crud_blueprint import apply_sort


def _request(query_string: str = "") -> Request:
    return Request(scope={"type": "http", "query_string": query_string.encode(), "headers": []})


ITEMS = {
    "3": {"name": "Charlie"},
    "1": {"name": "alice"},
    "2": {"name": "Bob"},
}


def test_ohne_sort_param_unveraendert():
    assert apply_sort(_request(), ITEMS) == ITEMS


def test_sort_asc_case_insensitive():
    result = apply_sort(_request("sort=name"), ITEMS)
    assert list(result.keys()) == ["1", "2", "3"]


def test_sort_desc():
    result = apply_sort(_request("sort=name&dir=desc"), ITEMS)
    assert list(result.keys()) == ["3", "2", "1"]


def test_leere_werte_landen_am_ende():
    items = {**ITEMS, "4": {"name": ""}}
    result = apply_sort(_request("sort=name"), items)
    assert list(result.keys())[-1] == "4"


def test_unbekanntes_feld_keine_exception():
    result = apply_sort(_request("sort=nicht_vorhanden"), ITEMS)
    assert set(result.keys()) == set(ITEMS.keys())


def test_gemischte_typen_kein_500():
    items = {"1": {"n": 5}, "2": {"n": "zehn"}, "3": {"n": None}}
    result = apply_sort(_request("sort=n"), items)
    assert set(result.keys()) == {"1", "2", "3"}
