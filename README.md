# astrapi-core

Full-stack Python-Framework, das **FastAPI** (JSON-APIs und HTML-UI) in einer ASGI-App kombiniert.
Basis für alle `ctl`-Apps (astrapi-backup, astrapi-packages, astrapi-mirror).

## Stack

| Komponente | Details |
|---|---|
| API | FastAPI (`/api/...`) |
| UI | FastAPI + HTMX + Jinja2 |
| Persistenz | SQLite (`SqliteStorage`) |
| Scheduler | APScheduler |
| Verschlüsselung | Fernet |
| Python | ≥ 3.11 |

## Setup (Entwicklung)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Projektstruktur

```
astrapi/core/
├── ui/                  # App-Factory, CRUD-Router, Storage, Templates
├── system/              # DB, Activity-Log, Secrets, Scheduler-Helpers
└── modules/             # Eingebaute Module (notify, scheduler, settings, sysinfo, activity_log)
```

## Tests

```bash
pytest
```

- httpx für FastAPI-Tests, playwright für E2E-Tests

## Versionsschema

CalVer: `YY.MM.patch` – Release-Automatisierung via `release.sh`.
