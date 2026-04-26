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

## Modul-Konvention

Jedes Modul unter `{app}/modules/<key>/` oder `core/modules/<key>/`:

| Datei | Inhalt |
|---|---|
| `__init__.py` | Erstellt `Module`-Instanz, registriert Scheduler-Actions |
| `modul.yaml` | `label`, `icon`, `nav_group`, `card_actions` |
| `settings.yaml` | Einstellungsfelder (Typ text/password/select, …) |
| `schema.yaml` | Formularfelder für CRUD-Modal |
| `api.py` | FastAPI-Router (`make_crud_router` o. manuell) |
| `ui.py` | FastAPI-Router (`make_crud_router` + Zusatz-Routen) |
| `engine.py` | Business-Logik |
| `storage.py` | `store = SqliteStorage(KEY)` |
| `templates/content.html` | Vollständiger Modul-Inhalt (page-header + Listenbereich) |
| `templates/partials/card_body.html` | Card-Body-Snippet (meta-grid), eingebunden per `content_template` |
| `templates/partials/list_header.html` | Tabellen-Header-Spalten (optional) |
| `templates/partials/list_row.html` | Tabellen-Zeilen-Spalten (optional) |
| `templates/partials/` | Weitere kleine HTMX-Fragmente (rows, metrics, …) |
| `templates/modals/` | Eigenständige Modal-Dialoge (edit.html, log.html, …) |

**Card-Action-Typen:** `run`, `run_debug`, `log`, `search`, `bar-chart`, `power-on`, `power-off`, `scan-host-key`, `preview`, `archives`, `stats`

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
