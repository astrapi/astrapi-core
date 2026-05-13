# DOM-Struktur – Haupt-Layout aller Module

## Ränder (padding / margin) – Desktop

| Selektor | padding | margin | gap |
|---|---|---|---|
| `.app-layout` | `12px` (rundum) | – | `12px` |
| `#sidebar` | – | – | – |
| `.sb-header` | `0 8px` (h: 47px) | – | – |
| `.nav-items` | `6px 8px` | – | `2px` |
| `.nav-item` | `10px 12px` | – | – |
| `.nav-divider` | – | `4px 8px` | – |
| `.sb-actions` | `4px 8px` | – | `6px` |
| `.sb-footer` | `6px 8px 10px` | – | – |
| `.sb-divider` | – | `0 8px` | – |
| `.main-content` | `0` | – | – |
| `.content-area` | `32px` (rundum) | – | – |
| `.content-header` | `12px 16px` | `0 0 24px 0` (unten) | – |
| `.content-footer` | `10px 16px` | `24px 0 0 0` (oben) | – |
| `.content-item` | `0` | – | – |
| `.card-body` | `16px` | – | `8px` |
| `.card-actions` | `12px 8px 10px` | – | `6px` |
| `.card-header` | `12px 16px 10px` | – | `8px` |
| `.card-footer` | `10px 16px` | – | – |
| `.card-run-info` | `6px 16px` | – | – |

### Mobile (`max-width: 768px`)

| Selektor | padding | margin |
|---|---|---|
| `.app-layout` | `0` | – |
| `.main-content` | `56px 16px 16px` | – |
| `.page-header` | `0 14px 0 58px` | `0 -14px 16px -14px` |

---

## Karten-Grid-Layouts (`.content-columns`)

Module die mehrere `content-item`-Karten nebeneinander anzeigen (kein Standard-`content-items`-Grid), verwenden die generischen Grid-Klassen:

| Klasse | Spalten | `align-items` | Verwendung |
|---|---|---|---|
| `.content-columns` | `1fr 1fr` | `start` | Basis: gleichbreite 2-Spalten |
| `.content-columns--stretch` | _(erbt)_ | `stretch` | gleiche Kartenhöhe – `notify` |
| `.content-columns--wide` | `minmax(0,1.3fr) minmax(0,1fr)` | _(erbt)_ | breite linke Karte – `system` |

**Responsive** (`max-width:900px`): `.content-columns`, `.content-columns--wide` → `grid-template-columns:1fr`

**Verwendung je Modul:**

| Modul | Klassen am Container |
|---|---|
| `notify` | `content-columns content-columns--stretch` |
| `system` | `content-columns content-columns--wide` |

---

## astrapi-core

### activity_log
```mermaid
flowchart TD
    layout["div.app-layout"]
    sidebar["aside#sidebar"]
    main["div#main-content"]
    c_area["div#mod-activity_log.content-area"]
    c_header["div.content-header<br>(Filter-Selects + Clear-Button)"]
    body["div#activity-log-body"]
    c_items["div.content-items.content-items--table"]
    table["table.ds-list-table"]
    c_footer["div.content-footer<br>(Pagination)"]

    layout --> sidebar
    layout --> main
    main --> c_area
    c_area --> c_header
    c_area --> body
    body --> c_items
    c_items --> table
    body --> c_footer
```

### notify
```mermaid
flowchart TD
    layout["div.app-layout"]
    sidebar["aside#sidebar"]
    main["div#main-content"]
    c_area["div#mod-notify.content-area"]
    c_header["div.content-header<br>(Neuer Kanal + Neuer Job)"]
    cols["div.content-columns.content-columns--stretch"]
    col1["div.content-item.on<br>Kanäle"]
    col2["div.content-item.on<br>Notify-Jobs"]
    t1["div.content-items--table<br>tbody#mod-notify-channels"]
    t2["div.content-items--table<br>tbody#mod-notify-jobs"]

    layout --> sidebar
    layout --> main
    main --> c_area
    c_area --> c_header
    c_area --> cols
    cols --> col1
    cols --> col2
    col1 --> t1
    col2 --> t2
```

### scheduler
```mermaid
flowchart TD
    layout["div.app-layout"]
    sidebar["aside#sidebar"]
    main["div#main-content"]
    c_area["div#mod-scheduler.content-area"]
    c_header["div.content-header<br>(Neu-Button)"]
    c_items["div.content-items.content-items--table"]
    table["table.ds-list-table<br>(Jobs)"]

    layout --> sidebar
    layout --> main
    main --> c_area
    c_area --> c_header
    c_area --> c_items
    c_items --> table
```

### settings
```mermaid
flowchart TD
    layout["div.app-layout"]
    sidebar["aside#sidebar"]
    main["div#main-content"]
    c_area["div#mod-settings.content-area"]
    c_header["div.content-header"]
    container["div#settings-container"]
    stack["div.section-stack"]
    card_g["div.content-item.on<br>Allgemein"]
    card_ssh["div.content-item.on<br>SSH-Key (optional)"]
    card_m["div.content-item.on<br>je Modul-Einstellungscard"]

    layout --> sidebar
    layout --> main
    main --> c_area
    c_area --> c_header
    c_area --> container
    container --> stack
    stack --> card_g
    stack -.-> card_ssh
    stack --> card_m
```

### system
```mermaid
flowchart TD
    layout["div.app-layout"]
    sidebar["aside#sidebar"]
    main["div#main-content"]
    c_area["div#mod-system.content-area"]
    c_header["div.content-header<br>(Aktualisieren-Button)"]
    metrics["div#system-metrics"]
    cols["div.content-columns.content-columns--wide"]
    info["div.content-item.on.sysinfo-info-card<br>(Versionstabelle)"]
    gauges["div.sysinfo-gauges-grid"]
    g1["div.content-item.on.sysinfo-gauge-card<br>CPU"]
    g2["div.content-item.on.sysinfo-gauge-card<br>RAM"]
    g3["div.content-item.on.sysinfo-gauge-card<br>Disk"]
    g4["div.content-item.on.sysinfo-gauge-card<br>Network"]

    layout --> sidebar
    layout --> main
    main --> c_area
    c_area --> c_header
    c_area --> metrics
    metrics --> cols
    cols --> info
    cols --> gauges
    gauges --> g1
    gauges --> g2
    gauges --> g3
    gauges --> g4
```

---

## astrapi-backup

> Alle Backup-Module (borg, rsync, proxmox_lxc, proxmox_hosts, proxmox_jobs, remotes) teilen dasselbe CRUD-Layout.

### borg / rsync / proxmox_lxc / proxmox_hosts / proxmox_jobs / remotes
```mermaid
flowchart TD
    layout["div.app-layout"]
    sidebar["aside#sidebar"]
    main["div#main-content"]
    c_area["div#mod-{key}.content-area"]
    c_header["div.content-header<br>(Neu-Button + optionale Aktionen)"]
    c_items["div.content-items--table"]
    table["table.ds-list-table<br>(list_header + list_row partials)"]
    c_footer["div.content-footer<br>(Pagination, optional)"]

    layout --> sidebar
    layout --> main
    main --> c_area
    c_area --> c_header
    c_area --> c_items
    c_items --> table
    c_area -.-> c_footer
```

---

## astrapi-packages

> docker und pakete teilen dasselbe CRUD-Layout.

### docker / pakete
```mermaid
flowchart TD
    layout["div.app-layout"]
    sidebar["aside#sidebar"]
    main["div#main-content"]
    c_area["div#mod-{key}.content-area"]
    c_header["div.content-header<br>(Neu-Button)"]
    c_items["div.content-items--table"]
    table["table.ds-list-table<br>(list_header + list_row partials)"]
    c_footer["div.content-footer<br>(Pagination, optional)"]

    layout --> sidebar
    layout --> main
    main --> c_area
    c_area --> c_header
    c_area --> c_items
    c_items --> table
    c_area -.-> c_footer
```

---

## astrapi-mirror

### debian
```mermaid
flowchart TD
    layout["div.app-layout"]
    sidebar["aside#sidebar"]
    main["div#main-content"]
    c_area["div#mod-debian.content-area"]
    c_header["div.content-header<br>(Neu-Button + Einstellungen)"]
    c_items["div.content-items--table"]
    table["table.ds-list-table<br>(list_header + list_row partials)"]
    c_footer["div.content-footer<br>(Pagination, optional)"]

    layout --> sidebar
    layout --> main
    main --> c_area
    c_area --> c_header
    c_area --> c_items
    c_items --> table
    c_area -.-> c_footer
```
