// Dark Mode – Fallback: localStorage nur wenn JS-Toggle benötigt wird
// (Server setzt .light-mode per class-Attribut; diese Funktion bleibt
// für Rückwärtskompatibilität und sofortigen Effekt nach Settings-Save)
function applyLightMode(value) {
    document.documentElement.classList.toggle('light-mode', value === '1' || value === true);
}

function _updateThemeIcon() {
    var use = document.getElementById('theme-toggle-icon');
    if (use) use.setAttribute('href', document.documentElement.classList.contains('light-mode') ? '#icon-sun' : '#icon-moon');
}

window.toggleDarkMode = function () {
    document.documentElement.classList.toggle('light-mode');
    localStorage.setItem('lightMode', document.documentElement.classList.contains('light-mode') ? '1' : '0');
    _updateThemeIcon();
};

// ── Aktive Navigation + Icon-Update ──────────────────────────────────────────
function updateActiveNav() {
    const path = window.location.pathname.replace(/^\/+/, "") || "overview";
    document.querySelectorAll(".nav-item").forEach(btn => {
        const key = btn.id.replace("nav-", "");
        const active = !!key && path === key;
        btn.classList.toggle("active", active);
        const svg = btn.querySelector(".nav-icon");
        const use = svg && svg.querySelector("use");
        if (use && svg.dataset.icon) {
            use.setAttribute("href", active ? "#icon-" + svg.dataset.icon : "#icon-" + svg.dataset.icon + "-outline");
        }
    });
}

document.getElementById("sidebar")?.addEventListener("click", function (e) {
    const navItem = e.target.closest(".nav-item");
    if (!navItem) return;
    const mobileTitle = document.getElementById("mobile-title");
    if (mobileTitle) mobileTitle.textContent = navItem.querySelector("span")?.textContent?.trim() || "";
});

document.addEventListener('DOMContentLoaded', function() {
    _updateThemeIcon();
    updateActiveNav();
});

document.body.addEventListener("htmx:afterSwap", (evt) => {
    if (evt.detail.target.id === "main-content") {
        updateActiveNav();
    }
});

document.body.addEventListener("htmx:pushedIntoHistory", () => {
    updateActiveNav();
});

// ── Spalteneinstellungen zurücksetzen ─────────────────────────────────────────
function resetColSettings(module) {
    fetch(`/ui/preferences/col-widths/${module}`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({widths: {}}),
    });
    localStorage.removeItem(`sort:${module}`);
    const table = document.querySelector(`.ds-list-table[data-module="${module}"]`);
    if (table) {
        table.querySelectorAll('thead th').forEach(th => {
            th.style.width = '';
            th.classList.remove('sort-asc', 'sort-desc');
        });
    }
}

// ── Spaltenbreiten-Resize ─────────────────────────────────────────────────────
function initColResize(table) {
    const module = table.dataset.module;
    if (!module) return;
    const saved = JSON.parse(table.dataset.colWidths || '{}');
    const headers = Array.from(table.querySelectorAll('thead th'));
    const last = headers.length - 1;

    headers.forEach((th, i) => {
        if (i === 0 || i === last || i === last - 1) return;
        if (saved[i] !== undefined) th.style.width = saved[i] + 'px';

        const handle = document.createElement('span');
        handle.className = 'col-resize-handle';
        th.appendChild(handle);

        handle.addEventListener('mousedown', e => {
            e.preventDefault();
            const startX = e.clientX;
            const startW = th.offsetWidth;
            handle.classList.add('resizing');

            const onMove = e => {
                th.style.width = Math.max(40, startW + e.clientX - startX) + 'px';
            };
            const onUp = () => {
                handle.classList.remove('resizing');
                document.removeEventListener('mousemove', onMove);
                document.removeEventListener('mouseup', onUp);
                const widths = {};
                headers.forEach((h, idx) => {
                    if (idx === 0 || idx === last || idx === last - 1) return;
                    widths[idx] = h.offsetWidth;
                });
                fetch(`/ui/preferences/col-widths/${module}`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({widths}),
                });
            };
            document.addEventListener('mousemove', onMove);
            document.addEventListener('mouseup', onUp);
        });
    });
}

function initAllColResize(root) {
    (root || document).querySelectorAll('.ds-list-table[data-module]').forEach(initColResize);
}

document.addEventListener('DOMContentLoaded', () => initAllColResize());
document.body.addEventListener('htmx:afterSwap', e => initAllColResize(e.detail.target));

// ── Tabellen-Sortierung ───────────────────────────────────────────────────────
function initTableSort(table) {
    const module = table.dataset.module;
    const storageKey = module ? `sort:${module}` : null;
    let saved = {};
    if (storageKey) {
        try { saved = JSON.parse(localStorage.getItem(storageKey) || '{}'); } catch {}
    }

    const headers = Array.from(table.querySelectorAll('thead th.sortable'));
    if (!headers.length) return;

    function applySort(th, dir, save) {
        headers.forEach(h => h.classList.remove('sort-asc', 'sort-desc'));
        th.classList.add(dir === 'asc' ? 'sort-asc' : 'sort-desc');

        const col = th.cellIndex;
        const tbody = table.querySelector('tbody');
        const rows = Array.from(tbody.querySelectorAll('tr'));
        rows.sort((a, b) => {
            const av = (a.cells[col]?.textContent || '').trim();
            const bv = (b.cells[col]?.textContent || '').trim();
            const cmp = av.localeCompare(bv, undefined, {numeric: true, sensitivity: 'base'});
            return dir === 'asc' ? cmp : -cmp;
        });
        rows.forEach(r => tbody.appendChild(r));
        if (save && storageKey) {
            localStorage.setItem(storageKey, JSON.stringify({col, dir}));
        }
    }

    if (saved.col !== undefined) {
        const th = headers.find(h => h.cellIndex === saved.col);
        if (th) applySort(th, saved.dir || 'asc', false);
    }

    headers.forEach(th => {
        th.addEventListener('click', () => {
            applySort(th, th.classList.contains('sort-asc') ? 'desc' : 'asc', true);
        });
    });
}

function initAllTableSort(root) {
    (root || document).querySelectorAll('.ds-list-table[data-module]').forEach(initTableSort);
}

document.addEventListener('DOMContentLoaded', () => initAllTableSort());
document.body.addEventListener('htmx:afterSwap', e => initAllTableSort(e.detail.target));

// ── Modal öffnen/schließen: Fokus-Management ─────────────────────────────
// Fokus-Rueckgabe: merkt sich beim Oeffnen eines Modals (hx-target="body"
// hx-swap="beforeend") das ausloesende Element und gibt beim Schliessen den
// Fokus dorthin zurueck -- ohne das verlieren Tastatur-/Screenreader-Nutzer
// ihre Position in der Liste dahinter.
// Autofokus: das erste fokussierbare Feld im Modal bekommt beim Oeffnen den
// Fokus (nicht den Schliessen-Button oben rechts).
function _focusableEls(container) {
    return Array.from(container.querySelectorAll(
        'a[href], button:not([disabled]), textarea:not([disabled]), ' +
        'input:not([disabled]):not([type="hidden"]), select:not([disabled]), ' +
        '[tabindex]:not([tabindex="-1"])'
    )).filter((el) => el.offsetParent !== null); // nur sichtbare Elemente
}

document.body.addEventListener('htmx:afterSwap', (evt) => {
    if (evt.detail.target !== document.body) return;
    const backdrop = document.body.querySelector('.ds-modal-backdrop:last-of-type');
    if (!backdrop) return;
    if (evt.detail.elt) backdrop._triggerEl = evt.detail.elt;

    const focusable = _focusableEls(backdrop);
    const firstField = focusable.find((el) => !el.classList.contains('ds-modal-close'));
    (firstField || focusable[0])?.focus();
});

function closeModalEl(backdrop) {
    if (!backdrop) return;
    const trigger = backdrop._triggerEl;
    backdrop.remove();
    if (trigger && document.body.contains(trigger) && typeof trigger.focus === 'function') {
        trigger.focus();
    }
}

function closeModal(el) {
    closeModalEl(el.closest('.ds-modal-backdrop'));
}

// Fokus-Trap: Tab/Umschalt+Tab bleiben innerhalb des obersten Modals, statt
// in die Seite dahinter zu wandern.
document.addEventListener('keydown', (evt) => {
    if (evt.key !== 'Tab') return;
    const modals = document.querySelectorAll('.ds-modal-backdrop');
    if (!modals.length) return;
    const backdrop = modals[modals.length - 1];
    if (!backdrop.contains(document.activeElement)) return;

    const focusable = _focusableEls(backdrop);
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (evt.shiftKey && document.activeElement === first) {
        evt.preventDefault();
        last.focus();
    } else if (!evt.shiftKey && document.activeElement === last) {
        evt.preventDefault();
        first.focus();
    }
});

// ── Zwischenablage mit Fallback ─────────────────────────────────────────
// navigator.clipboard existiert nur in "sicheren Kontexten" (HTTPS oder
// localhost) - viele Instanzen laufen intern per HTTP auf Hostname/IP,
// wo navigator.clipboard schlicht undefined ist und der Kopieren-Button
// sonst kommentarlos nichts tut. Fallback: klassisches execCommand('copy')
// über ein verstecktes Textarea.
function copyToClipboardFallback(text) {
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    try {
        document.execCommand('copy');
    } finally {
        document.body.removeChild(ta);
    }
}

window.copyToClipboard = function (text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).catch(function () {
            copyToClipboardFallback(text);
        });
    } else {
        copyToClipboardFallback(text);
    }
};

// Escape-Taste: siehe x-on:keydown.escape.window="closeModalEl($el)" in
// dialog_core.html -- war hier zusaetzlich als globaler Handler dupliziert
// (document-Listener feuert vor window-Listenern in der Bubble-Phase, hat
// das Modal also direkt per .remove() entfernt, BEVOR Alpine's Handler mit
// der Fokus-Rueckgabe drankam). Entfernt statt der zwei parallelen Pfade.

// ── Modul-Filter (Cookie-persistent, überlebt Browser-Reload) ────────────────
// Verwendung: x-data="moduleFilter('modulname__feldname')"
// Der Cookie wird beim HTMX-Request mitgesendet → Server kann ihn beim
// initialen Render lesen und die korrekte Option vorauswählen.
function moduleFilter(key) {
    const _cn = 'mf_' + key.replace(/[^a-zA-Z0-9]/g, '_');
    return {
        save(val) {
            if (val)
                document.cookie = _cn + '=' + encodeURIComponent(val) + '; path=/; SameSite=Lax; max-age=2592000';
            else
                document.cookie = _cn + '=; path=/; max-age=0';
        },
    };
}
