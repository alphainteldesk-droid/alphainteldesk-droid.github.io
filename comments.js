/* Comments (Nov 24, 2026, James): the conversation lives on X instead of an on-site comment box.
   On Market of the Week and Dossier pages: "Reply on X" (to our own X post about the piece, once its link is in
   x_posts.json), "Post your take on X" (pre-filled post with the page link, via @alphainteldesk) and
   "See what people are saying" (X search for posts linking the page).
   x_posts.json: {"dossier-<slug>": "https://x.com/alphainteldesk/status/<id>", "motw-<slug>": "..."} */
(function () {
  var box = document.getElementById("comments");
  if (!box) return;
  var SITE = "https://alphainteldesk.com";
  function show(id, path, title) {
    var page = SITE + path;
    var e = encodeURIComponent;
    var take = "https://x.com/intent/post?text=" + e("My take on “" + title + "”:") +
      "&url=" + e(page + "?utm_source=x&utm_medium=comment") + "&via=alphainteldesk";
    var see = "https://x.com/search?f=live&q=" + e("url:alphainteldesk.com" + path + " OR (@alphainteldesk \"" + title + "\")");
    box.innerHTML = '<h3>What do you think?</h3>' +
      '<p>Join the conversation on X. Reply to our post, or share your own take and tag <a href="https://x.com/alphainteldesk" target="_blank" rel="noopener">@alphainteldesk</a>.</p>' +
      '<div class="cmt-x">' +
      '<a class="chip" id="cmt-reply" hidden target="_blank" rel="noopener">Reply on X</a>' +
      '<a class="chip" href="' + take + '" target="_blank" rel="noopener">Post your take on X</a>' +
      '<a class="chip" href="' + see + '" target="_blank" rel="noopener">See what people are saying</a>' +
      '</div>';
    fetch("/x_posts.json", { cache: "no-store" }).then(function (r) { return r.json(); }).then(function (m) {
      var u = m[id], k = u && u.match(/status\/(\d+)/);
      if (!k) return;
      var a = document.getElementById("cmt-reply");
      a.href = "https://x.com/intent/post?in_reply_to=" + k[1];
      a.hidden = false;
    }).catch(function () {});
    box.hidden = false;
  }
  function pageTitle() { return document.title.split(" | ")[0]; }
  if (box.getAttribute("data-kind") === "dossier") {
    var slug = location.pathname.replace(/^.*\//, "").replace(/\.html$/, "");
    if (!slug || slug === "index") { box.hidden = true; return; }
    show("dossier-" + slug, "/dossier/" + slug + ".html", pageTitle());
    return;
  }
  var mslug = document.body.getAttribute("data-slug");
  if (mslug) { show("motw-" + mslug, "/motw/" + mslug + ".html", pageTitle()); return; }
  box.hidden = true;
  fetch("/motw.json", { cache: "no-store" }).then(function (r) { return r.json(); }).then(function (j) {
    var c = j.current;
    if (c && c.slug) show("motw-" + c.slug, "/motw/" + c.slug + ".html", c.title);
  }).catch(function () {});
})();
