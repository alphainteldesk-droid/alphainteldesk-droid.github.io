"""The Dossier (Nov 22, 2026): builds dossier/<slug>.html from a body file + dossier/index.html (list + Receipts).

Usage: python3 make_dossier.py [slug body.html charts.json]   (no args = rebuild the index only)
Page shell (head, menu, footer) is copied from guides.html so every dossier matches the rest of the site.
Charts are SVG drawn once from publish-day data and baked in (a dossier is a receipt: it never changes silently).
"""
import html, json, re, sys

SITE = "https://alphainteldesk.com"


FOLLOW = '''<section class="follow" aria-label="Follow Alpha Intel Desk">
  <div><h3>Get this every morning</h3>
  <p>Free 7 AM desk brief on Telegram: the biggest price gaps, Danger Zone picks and today's market-moving events. Follow on X for the best finds during the day.</p></div>
  <div class="follow-b"><a class="chip on" href="https://t.me/alphainteldesk" rel="noopener">Join on Telegram</a>
  <a class="chip" href="https://x.com/alphainteldesk" rel="noopener">Follow on X</a></div>
</section>
'''


COMMENTS = '''<section class="cmt" id="comments" data-kind="dossier" aria-label="Comments">
  <h3>What do you think?</h3>
  <p>Leave your take below. No sign-up needed. Comments are checked before they appear, so keep it civil and on topic (no spam or promo links).</p>
  <div id="cusdis_thread"></div>
</section>
'''
COMMENTS_JS = '<script src="/comments.js?v=1" defer></script>\n'


def shell():
    g = open("guides.html").read()
    head = g[:g.index("<title>")]
    head_tail = g[g.index("<meta property=\"og:type\""):g.index("</head>")]
    head_tail = re.sub(r'<meta property="og:(url|type)"[^>]*>\n?', "", head_tail)
    header = g[g.index("<header>"):g.index("</header>") + 9].replace(' class="on" href="/guides.html"', ' href="/guides.html"')
    header = header.replace('<a href="/dossier/">Dossier</a>', '<a class="on" href="/dossier/">Dossier</a>')
    footer = g[g.index("<footer>"):]
    fonts = g[g.index('<link rel="preconnect"'):g.index("<style>")]
    style = g[g.index("<style>"):g.index("</style>") + 8]
    return head, fonts, style, head_tail, header, footer


def page(title, desc, url, body, og_type="article", img=SITE + "/banner.png"):
    head, fonts, style, head_tail, header, footer = shell()
    meta = ('<title>%s | The Dossier | Alpha Intel Desk</title>\n<meta name="description" content="%s">\n'
            '<link rel="canonical" href="%s">\n<link rel="icon" type="image/svg+xml" href="/logo.svg">\n'
            '<meta property="og:title" content="%s">\n<meta property="og:description" content="%s">\n'
            '<meta property="og:image" content="%s">\n<meta property="og:url" content="%s">\n<meta property="og:type" content="%s">\n'
            '<meta name="twitter:card" content="summary_large_image">\n<meta name="twitter:site" content="@alphainteldesk">\n'
            % (html.escape(title), html.escape(desc), url, html.escape(title), html.escape(desc), img, url, og_type))
    tail = head_tail.replace('href="/site.css', 'href="/site.css')
    return (head + meta + fonts + style + "\n" + tail + '<link rel="stylesheet" href="/dossier.css?v=1">\n</head>\n<body>\n\n'
            + header.replace('src="logo.svg"', 'src="/logo.svg"') + '\n\n<main class="wrap">\n' + body + '\n' + FOLLOW + COMMENTS + '</main>\n' + COMMENTS_JS + '\n' + footer)


def build_one(slug, body_path, charts_path):
    d = json.load(open("dossier.json"))
    it = next(x for x in d["items"] if x["slug"] == slug)
    body = open(body_path).read()
    ch = json.load(open(charts_path)) if charts_path else {}
    for k, v in ch.items():
        body = body.replace("{{%s}}" % k.upper(), v)
    url = "%s/dossier/%s.html" % (SITE, slug)
    open("dossier/%s.html" % slug, "w").write(page(it["title"], it["dek"], url, body))
    print("Dossier: wrote dossier/%s.html" % slug)


def sitemap(urls):
    """List dossier pages in sitemap.xml once (indexnow.py pings everything in it daily)."""
    import datetime
    sm = open("sitemap.xml").read()
    for u in urls:
        if "<loc>%s</loc>" % u not in sm:
            sm = sm.replace("</urlset>", "  <url><loc>%s</loc><lastmod>%s</lastmod><changefreq>weekly</changefreq><priority>0.8</priority></url>\n</urlset>"
                            % (u, datetime.date.today().isoformat()))
    open("sitemap.xml", "w").write(sm)


def build_index():
    d = json.load(open("dossier.json"))
    items = sorted(d["items"], key=lambda x: -x["n"])
    when = lambda s: __import__("datetime").date.fromisoformat(s).strftime("%b %-d, %Y")
    cards = "".join(
        '<a class="card" href="/dossier/%s.html"><span class="kind">No. %d · %s · %s</span><h3>%s</h3><p>%s</p><span class="go">Read the dossier &rarr;</span></a>'
        % (x["slug"], x["n"], when(x["published"]), html.escape(x["topic"]), html.escape(x["title"]), html.escape(x["dek"])) for x in items)
    st = {"pending": ("p", "⏳ Pending"), "won": ("w", "✓ Called it"), "lost": ("l", "✗ Missed")}
    rows = "".join(
        '<tr><td>%s</td><td><a href="/dossier/%s.html">%s</a></td><td>%s<br><small>Market: &ldquo;%s&rdquo; &rarr; %s</small></td><td>%s</td><td class="st %s">%s</td></tr>'
        % (when(x["published"]), x["slug"], html.escape(x["title"]), html.escape(x["call"]), html.escape(x["market"]), x["side"],
           " · ".join("%s %s¢" % ({"polymarket": "Polymarket", "kalshi": "Kalshi", "alpha": "Alpha Arcade"}[k], v) for k, v in x["price_on_publish"].items()),
           st[x["status"]][0], st[x["status"]][1] + ("" if x["status"] != "pending" else "<br><small>checks %s</small>" % when(x["check"])))
        for x in items)
    won = sum(x["status"] == "won" for x in items); lost = sum(x["status"] == "lost" for x in items)
    body = ('<span class="tag">The Dossier · Opinion</span>\n<h1>The Dossier</h1>\n<p class="dos-dek">Opinion and analysis: our calls on the stories moving prediction markets.</p>\n'
            '<p>Each one gives the facts with sources, live prices from Polymarket, Kalshi and Alpha Arcade, '
            'both sides of the argument, then our own view and one dated call. Every call goes on the record below, hit or miss.</p>\n'
            '<div class="gl dos-list">' + cards + '</div>\n'
            '<h2 id="receipts">Receipts</h2>\n<p>Every call we have made, with the market price on the day we published. '
            'Calls are scored when the market settles. Misses stay up. Record so far: <b>%d called it · %d missed · %d pending</b>.</p>\n'
            '<div class="tw"><table class="rc"><thead><tr><th>Published</th><th>Dossier</th><th>The call</th><th>Price that day</th><th>Status</th></tr></thead><tbody>'
            % (won, lost, sum(x["status"] == "pending" for x in items)) + rows + '</tbody></table></div>\n'
            '<p class="note" style="margin-top:24px">The Dossier is opinion, not financial advice. The author may hold positions in markets discussed. '
            'Read our <a href="/disclosures.html">disclosures</a>.</p>')
    css = '<style>.gl .card{display:block;color:inherit;text-decoration:none}.gl .card h3{color:var(--text);margin:6px 0}.gl .kind{font-size:.74rem;letter-spacing:.06em;color:var(--amber)}.gl .go{display:inline-block;margin-top:8px;color:var(--cyan);font-weight:700;font-size:.9rem}</style>'
    out = page("The Dossier: our calls on the stories moving prediction markets",
               "Opinion reports from Alpha Intel Desk: the facts, live prices on Polymarket, Kalshi and Alpha Arcade, our view and a dated call, with every call tracked in Receipts.",
               SITE + "/dossier/", body, og_type="website").replace("</head>", css + "\n</head>")
    open("dossier/index.html", "w").write(out)
    sitemap([SITE + "/dossier/"] + ["%s/dossier/%s.html" % (SITE, x["slug"]) for x in items])
    print("Dossier: index with %d dossier(s)" % len(items))


if __name__ == "__main__":
    import os
    os.makedirs("dossier", exist_ok=True)
    if len(sys.argv) > 2:
        build_one(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    build_index()
