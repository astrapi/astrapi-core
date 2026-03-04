"""
core/ui/navigation.py  –  Navigation aus YAML laden

Unterstützte YAML-Felder je Eintrag:
  key:      eindeutiger Bezeichner (wird auch als URL-Segment genutzt)
  label:    Anzeigename (default: key.title())
  url:      HTMX-Lade-URL (default: /api/ui/<key>/tab)
  icon:     Icon-Name (home | list | chart | clock | alert | settings |
            database | users | server | shield | monitor | archive | search)
  default:  true = dieses Item ist die Startseite (max. eines)
  separator: true = Trennlinie (kein Nav-Item)
  group:    (optional, nur bei separator) Gruppenbezeichnung
"""

import yaml
from pathlib import Path


def load_nav(path: Path) -> list[dict]:
    """Lädt und validiert die Navigation aus einer YAML-Datei."""
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or []

    items:    list[dict] = []
    defaults: list[dict] = []

    for entry in raw:
        # ── Separator / Gruppentrennlinie ──────────────────────────────────
        if entry.get("separator"):
            items.append({
                "separator": True,
                "group":     entry.get("group", ""),
            })
            continue

        k = entry.get("key")
        if not k:
            continue                        # Einträge ohne key überspringen

        item = {
            "key":       k,
            "label":     entry.get("label",   k.replace("_", " ").title()),
            "url":       entry.get("url",     f"/api/ui/{k}/tab"),
            "icon":      entry.get("icon",    "home"),
            "default":   bool(entry.get("default", False)),
            "separator": False,
        }

        if item["default"]:
            defaults.append(item)

        items.append(item)

    # ── Validierung: Nur ein Default ───────────────────────────────────────
    if len(defaults) > 1:
        raise RuntimeError(
            f"Mehrere default-Nav-Items in {path}: "
            f"{[d['key'] for d in defaults]}"
        )

    # ── Kein explizites Default → erstes Nav-Item übernimmt die Rolle ──────
    if not defaults:
        for item in items:
            if not item["separator"]:
                item["default"] = True
                break

    return items
