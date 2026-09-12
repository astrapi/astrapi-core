"""ui/file_listing.py -- gemeinsamer Datei-Browser für astrapi-mirror/
-packages/-sync (Rendering optisch an die Admin-Oberfläche angelehnt,
siehe Modul-Docstring). Reines String-Rendering ohne Jinja2/TestClient
nötig -- die Funktionen sind pure Funktionen."""
from pathlib import Path

from astrapi_core.ui.file_listing import (
    ListingEntry,
    dir_link,
    file_link,
    list_dir_entries,
    render_page,
    render_row,
    safe_child,
)


def test_render_page_laedt_app_css_und_enthaelt_titel():
    html = render_page("Mein Titel", "", "<tr><td>x</td></tr>")
    assert '<link rel="stylesheet" href="/static/css/app.css">' in html
    assert "<h1>Mein Titel</h1>" in html
    assert "<table>" in html


def test_render_page_ohne_back_zeigt_keinen_zurueck_link():
    html = render_page("T", "", "")
    assert 'class="fb-back"' not in html


def test_render_page_mit_back_zeigt_zurueck_link_mit_icon():
    html = render_page("T", "", "", back="/eltern/")
    assert 'class="fb-back" href="/eltern/"' in html
    assert "<svg" in html.split('class="fb-back"')[1].split("</a>")[0]


def test_render_page_ohne_hint_hat_keinen_leeren_hint_div():
    html = render_page("T", "", "")
    assert 'class="fb-hint"' not in html


def test_render_page_mit_hint_zeigt_ihn():
    html = render_page("T", "Ein Hinweis", "")
    assert '<div class="fb-hint">Ein Hinweis</div>' in html


def test_dir_link_escaped_und_hat_ordner_icon():
    html = dir_link('<script>alert(1)</script>', "/x/")
    assert "&lt;script&gt;" in html
    assert "<script>" not in html
    assert 'href="/x/"' in html
    assert "#f5c211" in html  # gelbes Ordner-Icon


def test_file_link_hat_datei_icon_nicht_ordner_icon():
    html = file_link("readme.txt", "/x/readme.txt")
    assert "#f5c211" not in html
    assert "var(--text-3)" in html


def test_render_row_ordner_bekommt_ordner_icon_und_trailing_slash():
    entry = ListingEntry(name="unterordner", href="/x/unterordner/", is_dir=True)
    row = render_row(entry)
    assert "unterordner/" in row
    assert "#f5c211" in row


def test_render_row_datei_bekommt_datei_icon_und_groesse():
    entry = ListingEntry(name="paket.deb", href="/x/paket.deb", is_dir=False, size_bytes=2048)
    row = render_row(entry)
    assert "paket.deb</span>" in row
    assert "#f5c211" not in row
    assert "2" in row  # Groessenformatierung (KB o.ae.)


def test_copy_button_enthaelt_textarea_und_check_icon():
    from astrapi_core.ui.file_listing import copy_button

    html = copy_button("uid-1", "curl -X GET http://example")
    assert 'id="uid-1"' in html
    assert "curl -X GET http://example" in html
    assert 'class="ci"' in html
    assert 'class="ck"' in html


def test_list_dir_entries_sortiert_ordner_vor_dateien(tmp_path: Path):
    (tmp_path / "b_datei.txt").write_text("x")
    (tmp_path / "a_ordner").mkdir()
    entries = list_dir_entries(tmp_path, lambda name, is_dir: f"/{name}")
    assert [e.name for e in entries] == ["a_ordner", "b_datei.txt"]
    assert entries[0].is_dir is True
    assert entries[1].is_dir is False


def test_safe_child_blockt_pfad_traversal_mit_zahlen_praefix_kollision(tmp_path: Path):
    """Regressions-Check T-213-SYNC-Fehlerklasse: '1' ist ein String-Präfix
    von '18', aber '18' ist kein Kindverzeichnis von '1'."""
    import pytest
    from fastapi import HTTPException

    base = tmp_path / "1"
    base.mkdir()
    sibling = tmp_path / "18"
    sibling.mkdir()
    (sibling / "geheim.txt").write_text("secret")

    with pytest.raises(HTTPException):
        safe_child(base, "..", "18", "geheim.txt")

    # legitimer Zugriff funktioniert weiterhin
    (base / "erlaubt.txt").write_text("ok")
    assert safe_child(base, "erlaubt.txt").name == "erlaubt.txt"
