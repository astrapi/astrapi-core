# AstrapiFlaskUi – Installation & Update

## Neues Projekt starten

```bash
# 1. Template klonen
git clone https://gitlab.com/<dein-user>/AstrapiFlaskUi.git meinprojekt
cd meinprojekt

# 2. Venv anlegen
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 3. App anpassen
#    → app/config.py          Name, Version, Logo
#    → app/templates/navigation/items.yaml   Seiten definieren
#    → app/templates/partials/lists/         Seiten anlegen

# 4. Starten
python main.py
# → http://localhost:5000
```

---

## Core-Framework updaten

Der `core/`-Ordner ist das Framework – er wird **nie manuell bearbeitet**.  
Eigener Code liegt ausschließlich in `app/`.

### Per Release-ZIP (empfohlen)

```bash
# 1. Gewünschte Version von GitLab Releases herunterladen
#    https://gitlab.com/<dein-user>/AstrapiFlaskUi/-/releases

# 2. ZIP entpacken
unzip AstrapiFlaskUi-v1.2.0.zip

# 3. core/ ins Projekt kopieren (überschreibt den alten core/)
cp -r AstrapiFlaskUi-core/core/ /pfad/zu/meinprojekt/

# 4. Testen
cd /pfad/zu/meinprojekt
python main.py
```

### Per git remote (alternativ)

```bash
cd meinprojekt
git remote add upstream https://gitlab.com/<dein-user>/AstrapiFlaskUi.git
git fetch upstream
git checkout upstream/main -- core/
git add core/
git commit -m "chore: update AstrapiFlaskUi core to vX.Y.Z"
```

---

## Was ist im Release-ZIP?

```
AstrapiFlaskUi-core/
├── core/
│   ├── static/
│   │   ├── css/app.css          # Design-System
│   │   └── js/                  # Dark Mode, Navigation
│   ├── templates/
│   │   ├── base.html
│   │   ├── index.html
│   │   ├── navigation/
│   │   └── partials/
│   └── ui/
│       ├── app.py               # Flask App-Factory
│       ├── navigation.py
│       └── page_factory.py
└── INSTALL.md                   # Diese Datei
```

**Nicht im ZIP** (gehört zum Projekt, nicht zum Framework):
- `app/` – deine Seiten, Config, eigene Assets
- `main.py` – Einstiegspunkt
- `requirements.txt`

---

## Neue Seite hinzufügen

**1.** Eintrag in `app/templates/navigation/items.yaml`:
```yaml
- key: meine_seite
  label: Meine Seite
  url: /api/ui/meine_seite/tab
  icon: list
```

**2.** Partial anlegen unter `app/templates/partials/lists/meine_seite.html` – fertig.

---

## Release erstellen (Maintainer)

```bash
git tag v1.2.0
git push origin v1.2.0
# → GitLab CI baut automatisch das ZIP und erstellt den Release
```
