/* Comments (Nov 24, 2026): Cusdis comment box on Market of the Week and Dossier pages.
   Every comment waits for James's approval before it shows.
   One thread per market / per Dossier: /market-of-the-week.html and /motw/<slug>.html share the same thread.
   The box stays hidden until APP (the Cusdis "App ID") is filled in. */
(function () {
  var APP = "";
  var box = document.getElementById("comments");
  if (!box) return;
  if (!APP) { box.hidden = true; return; }
  var SITE = "https://alphainteldesk.com";
  function go(id, url, title) {
    var d = document.getElementById("cusdis_thread");
    d.setAttribute("data-host", "https://cusdis.com");
    d.setAttribute("data-app-id", APP);
    d.setAttribute("data-page-id", id);
    d.setAttribute("data-page-url", url);
    d.setAttribute("data-page-title", title);
    d.setAttribute("data-theme", "dark");
    var s = document.createElement("script");
    s.async = true; s.defer = true;
    s.src = "https://cusdis.com/js/cusdis.es.js";
    document.body.appendChild(s);
  }
  function pageTitle() { return document.title.split(" | ")[0]; }
  if (box.getAttribute("data-kind") === "dossier") {
    var slug = location.pathname.replace(/^.*\//, "").replace(/\.html$/, "");
    if (!slug) { box.hidden = true; return; }
    go("dossier-" + slug, SITE + "/dossier/" + slug + ".html", pageTitle());
    return;
  }
  var mslug = document.body.getAttribute("data-slug");
  if (mslug) { go("motw-" + mslug, SITE + "/motw/" + mslug + ".html", pageTitle()); return; }
  fetch("/motw.json", { cache: "no-store" }).then(function (r) { return r.json(); }).then(function (j) {
    var c = j.current;
    if (!c || !c.slug) { box.hidden = true; return; }
    go("motw-" + c.slug, SITE + "/motw/" + c.slug + ".html", c.title);
  }).catch(function () { box.hidden = true; });
})();
