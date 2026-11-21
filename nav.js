/* Nov 21, 2026: close the Tools menu when tapping elsewhere or pressing Escape */
document.addEventListener('click', function (e) {
  document.querySelectorAll('nav .nt[open]').forEach(function (d) { if (!d.contains(e.target)) d.removeAttribute('open'); });
});
document.addEventListener('keydown', function (e) { if (e.key === 'Escape') document.querySelectorAll('nav .nt[open]').forEach(function (d) { d.removeAttribute('open'); }); });
