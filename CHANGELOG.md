# Changelog

Alle nennenswerten Änderungen am Projekt werden hier dokumentiert.
Format: [Semantic Versioning](https://semver.org/)

---

## [0.1.0] – 2026-02-27

### Added
- Initiales Release
- Flask + HTMX + Alpine.js App-Shell
- Sidebar-Navigation mit YAML-Config
- Dark/Light Mode Toggle
- Zwei Beispielseiten: Übersicht (Karten) + Einstellungen (Formular)
- Core/App-Trennung für einfache Updates

## [0.2.0] – 2026-02-27

### Fixed
- `url_for('static', ...)` Fehler durch Flask-Subklasse mit `send_static_file()`-Override behoben
- Spuriösen `{core`-Ordner (Shell-Brace-Expansion-Artefakt) entfernt

### Added
- GitLab CI/CD Pipeline (`.gitlab-ci.yml`)
- Automatische Release-ZIPs bei `v*`-Tags via GitLab Generic Packages
- `INSTALL.md` mit Update-Anleitung für Folgeprojekte
- GitHub Actions entfernt (→ GitLab)
