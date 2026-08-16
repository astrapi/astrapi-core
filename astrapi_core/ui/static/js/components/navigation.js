function toggleMobileNav() {
  if (document.body.classList.contains('mobile-nav-open')) {
    closeMobileNav();
  } else {
    document.body.classList.add('mobile-nav-open');
    document.body.style.overflow = 'hidden';
  }
}

function closeMobileNav() {
  document.body.classList.remove('mobile-nav-open');
  document.body.style.overflow = '';
}

function _setMobileTitle(text) {
  var el = document.getElementById('mobile-title');
  if (el && text) el.textContent = text;
}

document.addEventListener('DOMContentLoaded', function() {
  var active = document.querySelector('.nav-item.active span');
  if (active) _setMobileTitle(active.textContent.trim());
});

document.addEventListener('htmx:afterSwap', function(e) {
  if (e.target?.id !== 'main-content') return;
  if (window.innerWidth < 769) closeMobileNav();
  var h = e.target.querySelector('.content-header-title') || e.target.querySelector('.page-title');
  if (h) _setMobileTitle(h.textContent.trim());
});

document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') closeMobileNav();
});

// ── Mobile Filter-Panel (Bottom-Sheet statt Inline-Selects im Header) ────────
function toggleFilterPanel() {
  if (document.body.classList.contains('filter-panel-open')) {
    closeFilterPanel();
  } else {
    document.body.classList.add('filter-panel-open');
    document.body.style.overflow = 'hidden';
  }
}

function closeFilterPanel() {
  document.body.classList.remove('filter-panel-open');
  document.body.style.overflow = '';
}

// Von den Filter-Buttons im Bottom-Sheet aufgerufen: setzt den Wert auf dem
// (weiterhin vorhandenen, nur visuell versteckten) <select> und feuert
// "change" – dadurch bleiben Cookie-Persistenz (moduleFilter) und der
// hx-include-Mechanismus fuer mehrere kombinierte Filter unveraendert, ohne
// die Logik hier zu duplizieren.
function _setFilterValue(btn) {
  var group = btn.closest('.m-filter-group');
  var select = group && group.querySelector('select.table-filter-select');
  if (!select) return;
  select.value = btn.dataset.value || '';
  select.dispatchEvent(new Event('change', {bubbles: true}));
  closeFilterPanel();
}

document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') closeFilterPanel();
});
