"""ui/file_listing.py -- gemeinsamer Datei-Browser für astrapi-mirror/
-packages/-sync (Rendering optisch an die Admin-Oberfläche angelehnt,
siehe Modul-Docstring). Reines String-Rendering ohne Jinja2/TestClient
nötig -- die Funktionen sind pure Funktionen.

Zeilen kommen seit [[T-Files-Mobile]] als (Desktop-<tr>, Mobile-.m-card)-
Paare aus render_row()/render_row_pair() statt als fertiger HTML-String --
Tests pruefen entsprechend beide Haelften."""
from pathlib import Path

from astrapi_core.ui.file_listing import (
    Cell,
    ListingEntry,
    dir_link,
    file_link,
    list_dir_entries,
    render_link_row,
    render_page,
    render_row,
    render_row_pair,
    safe_child,
)


def test_render_page_laedt_app_css_und_enthaelt_titel():
    html = render_page("Mein Titel", "", [render_row_pair([Cell("x")])])
    assert '<link rel="stylesheet" href="/static/css/app.css">' in html
    assert '<div class="content-header-title">Mein Titel</div>' in html
    assert "<table>" in html


def test_render_page_ohne_back_zeigt_keinen_zurueck_link():
    html = render_page("T", "", [])
    assert 'class="btn-icon" href' not in html


def test_render_page_mit_back_zeigt_zurueck_link_mit_icon():
    html = render_page("T", "", [], back="/eltern/")
    assert 'class="btn-icon" href="/eltern/"' in html
    assert "<svg" in html.split('href="/eltern/"')[1].split("</a>")[0]


def test_render_page_ohne_hint_hat_keinen_leeren_hint_div():
    html = render_page("T", "", [])
    assert 'class="fb-hint"' not in html


def test_render_page_mit_hint_zeigt_ihn():
    html = render_page("T", "Ein Hinweis", [])
    assert '<div class="fb-hint">Ein Hinweis</div>' in html


def test_render_page_ohne_rows_und_ohne_empty_message_zeigt_keine_tabelle():
    """Reiner Hint-/Setup-Seiten-Fall (z.B. 'noch nicht synchronisiert') --
    keine leere Tabelle ohne Erklärung anzeigen."""
    html = render_page("T", "Hinweistext", [])
    assert "<table>" not in html


def test_render_page_mit_empty_message_zeigt_sie_in_beiden_ansichten():
    html = render_page("T", "", [], col_headers=("Name", "Größe"), empty_message="Nichts da.")
    assert "Nichts da." in html
    assert "<table>" in html
    assert 'class="empty-state"' in html


def test_render_page_zeigt_desktop_und_mobile_ansicht():
    html = render_page("T", "", [render_row_pair([Cell("Eintrag 1")])])
    assert 'class="fb-card desktop-view"' in html
    assert 'class="mobile-view"' in html
    assert 'class="m-card' in html


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


def test_render_row_pair_erste_zelle_wird_mobile_titel():
    tr_html, card_html = render_row_pair([Cell("Titel-HTML"), Cell("Wert", label="Label")])
    assert "Titel-HTML" in tr_html
    assert '<span class="m-card-title">Titel-HTML</span>' in card_html
    assert '<span class="m-card-meta-label">Label</span>' in card_html
    assert '<span class="m-card-meta-value">Wert</span>' in card_html


def test_render_row_pair_ohne_label_keine_mobile_meta_zeile():
    """Zellen ohne label (ausser der ersten) tauchen auf Mobile nicht als
    leere Meta-Zeile auf."""
    _, card_html = render_row_pair([Cell("Titel"), Cell("versteckt")])
    assert "versteckt" not in card_html


def test_render_link_row_baut_ordner_link_in_beiden_ansichten():
    tr_html, card_html = render_link_row("unterordner/", "/x/")
    assert "unterordner/" in tr_html
    assert "unterordner/" in card_html
    assert "#f5c211" in card_html


def test_render_row_ordner_bekommt_ordner_icon_und_trailing_slash():
    entry = ListingEntry(name="unterordner", href="/x/unterordner/", is_dir=True)
    tr_html, card_html = render_row(entry)
    assert "unterordner/" in tr_html
    assert "#f5c211" in tr_html
    assert "unterordner/" in card_html


def test_render_row_datei_bekommt_datei_icon_und_groesse():
    entry = ListingEntry(name="paket.deb", href="/x/paket.deb", is_dir=False, size_bytes=2048)
    tr_html, card_html = render_row(entry)
    assert "paket.deb</span>" in tr_html
    assert "#f5c211" not in tr_html
    assert "2" in tr_html  # Groessenformatierung (KB o.ae.)
    assert "Größe" in card_html
    assert "Geändert" in card_html


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
