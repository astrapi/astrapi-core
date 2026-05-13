# astrapi-core – Projektkontext für GitHub Copilot

Wird im Repo versioniert und von VS Code Copilot automatisch geladen.

---

## Was ist astrapi-core?

Full-stack Python-Framework, das **FastAPI** (JSON-APIs und HTML-UI) in einer ASGI-App kombiniert.
Basis für alle `ctl`-Apps (packagectl, backupctl, …).
Stellt Modul-System, generisches CRUD, Storage, Scheduler, Notifications und Activity-Log bereit.

---

## Stack

| Komponente | Details |
|---|---|
| API | FastAPI (`/api/...`) |
| UI | FastAPI + HTMX + Jinja2 (`/`) – kein Flask mehr! |
| Persistenz | SQLite (`SqliteStorage`, direkte SQL-Helpers) |
| Scheduler | APScheduler |
| Verschlüsselung | Fernet (Secrets) |
| Python | ≥ 3.11 |

**Einstiegspunkt für Apps:** `astrapi.core.ui.create(api: FastAPI, app_root, config, extra_init, modules)`

> **Hinweis:** Flask und a2wsgi wurden entfernt. `create()` nimmt jetzt die FastAPI-Instanz als erstes Argument und konfiguriert sie in-place.

---

## Verzeichnisstruktur

```
astrapi/core/
├── ui/
│   ├── app.py               # Flask-Factory (Haupt-Entry-Point)
│   ├── _base.py             # Module-Dataclass
│   ├── module_registry.py   # Auto-Discovery & Registrierung
│   ├── module_loader.py     # Liest modul.yaml + settings.yaml
│   ├── crud_router.py       # Generischer FastAPI-CRUD-Router
│   ├── crud_blueprint.py    # Generischer Flask-CRUD-Blueprint
│   ├── storage.py           # SqliteStorage (ehem. YamlStorage)
│   ├── settings_registry.py # Settings (SQLite-backed, thread-safe)
│   ├── schema_loader.py     # Parst schema.yaml für Formulare
│   ├── field_resolver.py    # Dynamische Feldoptionen
│   ├── page_factory.py      # Auto-Routes /<key>, /ui/<key>/content
│   ├── static/              # CSS, JS, Icons
│   └── templates/           # Jinja2-Templates (index.html, partials/)
│
├── system/
│   ├── db.py                # SQLite-Verbindungspool, register_table, CRUD-Helpers
│   ├── activity_log.py      # Job-Run-Tracking (Runs + Log-Lines)
│   ├── secrets.py           # Fernet-Secrets (getrennt von Backup)
│   ├── version.py           # CalVer YY.MM.patch.devN
│   ├── cmd.py               # Subprocess-Helpers
│   ├── health.py            # Health-Check-Endpoints
│   ├── paths.py             # Runtime-Pfade
│   └── systemd.py           # sd_notify / Watchdog
│
└── modules/                 # Eingebaute Core-Module
    ├── activity_log/        # Job-History-Viewer
    ├── notify/              # Benachrichtigungen (Email, Webhook, …)
    ├── scheduler/           # APScheduler-UI + engine
    ├── settings/            # Globale Einstellungs-UI
    └── sysinfo/             # CPU/RAM/Disk (psutil)
```

---

## Key-API (Imports für Apps)

```python
from astrapi.core.ui import Module, create
from astrapi.core.ui.crud_router import make_crud_router
from astrapi.core.ui.crud_blueprint import make_crud_router  # UI-CRUD-Router (FastAPI)
from astrapi.core.ui.storage import SqliteStorage, YamlStorage  # YamlStorage = Alias
from astrapi.core.ui.settings_registry import get, set, get_module, set_module
from astrapi.core.system.db import register_table, load_config, get_item, create_item, update_item, delete_item
from astrapi.core.system.secrets import set_secret, get_secret, get_secret_safe
from astrapi.core.system.activity_log import add_log_entry, list_runs_for_item, get_log_lines
from astrapi.core.modules.notify import engine as notify_engine  # notify_engine.send(...)
from astrapi.core.modules.scheduler.engine import configure, init, register_action
from astrapi.core.ui.module_loader import load_modul
```

> **Hinweis:** `YamlStorage` ist ein Alias für `SqliteStorage`. Die alten YAML-Dateien werden beim ersten Zugriff automatisch migriert.

---

## Modul-Konvention (verbindlicher Standard)

Jedes Modul unter `{app}/modules/<key>/` oder `core/modules/<key>/` folgt exakt dieser Struktur:

```
modules/<key>/
├── __init__.py              # Pflicht
├── jobs.py                  # Pflicht
├── engine.py                # nur wenn Kernlogik umfangreich (z.B. Konfig-Generierung, Validierung)
├── config/
│   ├── modul.yaml           # Pflicht
│   ├── schema.yaml          # Pflicht (außer Static-Module ohne DB-Items)
│   └── settings.yaml        # wenn das Modul konfigurierbar ist
├── icons/
│   ├── icon.svg             # Pflicht – filled SVG, currentColor
│   └── icon-outline.svg     # Pflicht – outline SVG, currentColor
├── dialogs/                 # wenn eigene Dialoge nötig
│   └── <typ>/
│       └── modal.html       # ein Unterordner pro Dialog-Typ
└── ui/
    ├── __init__.py          # Pflicht – exportiert router
    └── crud.py              # Pflicht – UI-Router
```

### Regeln

**`__init__.py`**
- `_KEY = Path(__file__).parent.name` – Key immer aus dem Verzeichnisnamen ableiten
- `store = YamlStorage(_KEY)` – kein `register_table` + DDL-String
- `load_modul(Path(__file__).parent, _KEY, router, ui_router)`
- `register_action(f"{_KEY}.run", ...)` wenn das Modul ausführbar ist

**`config/modul.yaml`**
- `card_actions` ausschließlich als Type-Kürzel (`type: run`, `type: log`, `type: preview`, …)
- Kein HTMX-expliziter Stil (`hx_post`, `hx_target` direkt in modul.yaml)
- Verfügbare Typen: `run`, `run_debug`, `log`, `preview`, `archives`, `stats`, `power-on`, `power-off`, `scan-host-key`

**`ui/crud.py`**
- `make_crud_router(store, KEY, schema_path=..., ...)` aus `astrapi_core.ui.crud_blueprint`
- Kein getrenntes `api_router` + `ui_router` – ein UI-Router, ein JSON-Router

**`jobs.py`**
- Ausführbare Module: `run_single(item_id)`, `run()`, `preview(item_id)`
- Async-Pattern: `def fn_async(): threading.Thread(target=fn, daemon=True).start()`
- Umfangreiche Kernlogik → in `engine.py` auslagern

**Status-Felder** (alle ausführbaren Module)
- `last_status`: `"ok"` / `"error"` / `"running"` / `"neu"`
- `last_run`: ISO-Timestamp

---

## Template-Auflösung

Priorität: **App-Templates > Core-Templates > Modul-Templates**
Realisiert via `ChoiceLoader` – Apps können Core-Templates überschreiben.

---

## Datenbank

- `db.configure(path)` – muss vor jedem DB-Zugriff aufgerufen werden
- `register_table(key, ddl, list_fields, col_in, col_out)` – Tabelle deklarieren
- `create_all_registered_tables()` – alle registrierten Tabellen anlegen
- Generische CRUD-Helpers: `load_config`, `get_item`, `create_item`, `update_item`, `delete_item`
- Thread-lokale Verbindungen (`check_same_thread=False`)

---

## Settings

```python
# Global
from astrapi.core.ui.settings_registry import get, set
val = get("MY_KEY", default="fallback")
set("MY_KEY", "value")

# Modul-spezifisch
from astrapi.core.ui.settings_registry import get_module, set_module
val = get_module("mymod", "timeout", default="30")
```

---

## schema.yaml – Feld-Typen

`text`, `number`, `boolean`, `select` (mit `options`-Liste), `list` (Multi-Value), `password` (verschlüsselt in DB)

---

## Versionsschema

CalVer: `YY.MM.patch.devN` – monatlicher Reset des Patch-Counters.
Release-Automatisierung via `release.sh`.

---

## Tests

- pytest, httpx (FastAPI-Tests), playwright (E2E / Browser-Tests)
