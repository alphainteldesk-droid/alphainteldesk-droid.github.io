/* Nov 21, 2026: close the Tools menu when tapping elsewhere or pressing Escape */
document.addEventListener('click', function (e) {
  document.querySelectorAll('nav .nt[open]').forEach(function (d) { if (!d.contains(e.target)) d.removeAttribute('open'); });
});
document.addEventListener('keydown', function (e) { if (e.key === 'Escape') document.querySelectorAll('nav .nt[open]').forEach(function (d) { d.removeAttribute('open'); }); });
/* Nov 28, 2026 (James): every page's heading block (tag, title, intro lines) is centered on the page. Marks the
   elements at the top of <main class="wrap"> up to the first box, table or section heading; site.css centers them.
   Leading tag labels are grouped on one centered line. Runs again when a page fills itself in (Market of the Week). */
(function () {
  var m = document.querySelector('main.wrap'); if (!m) return;
  function center() {
    var k = m.firstElementChild;
    while (k && k.classList.contains('tabs')) k = k.nextElementSibling;   // Market of the Week tabs stay where they are
    if (k && k.tagName === 'SPAN') {                                       // tag labels -> one centered line
      var row = document.createElement('div'); row.className = 'pg-head pg-tags'; m.insertBefore(row, k);
      while (row.nextElementSibling && row.nextElementSibling.tagName === 'SPAN') row.appendChild(row.nextElementSibling);
      k = row;
    }
    for (; k; k = k.nextElementSibling) {
      var t = k.tagName;
      if (t === 'H1' || t === 'P' || k.classList.contains('howpay') || k.classList.contains('pg-tags')) k.classList.add('pg-head');
      else break;
    }
  }
  center();
  if (window.MutationObserver) { var mo = new MutationObserver(function () { mo.disconnect(); center(); mo.observe(m, { childList: true }); }); mo.observe(m, { childList: true }); }
})();
