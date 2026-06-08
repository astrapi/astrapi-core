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
