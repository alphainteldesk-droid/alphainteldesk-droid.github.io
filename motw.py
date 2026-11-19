"""Market of the Week (Nov 19, 2026, James). Runs in every "Update markets" job.

- Picks one market a week by formula (staged Mondays from 4 AM ET, live once James approves the write-up), from matches.json:
  on 2+ sites (Alpha first, all three best), a real debate (30-70c), settles in 14-60 days,
  busy (24h volume), clear rules (A/B), no sports or daily price markets, not picked in the last 8 weeks.
- VERIFIED TWICE (James's rule): a new pick only goes live after two separate readings at least
  30 minutes apart agree (same top market, every site's price within 3c), and the sites' prices are within
  10c of each other (a bigger split means the markets may not be the same). Shown prices are only updated
  when the last two readings agree within 3c; otherwise the page keeps the last confirmed price.
- Both Sides text lives in motw_story.json (written with research each week). Any point with fewer than two
  independent sources is dropped here, before it can reach the page.
- Keeps an hourly price history per site from the publish time, and an archive scoring every past pick.
Writes motw.json for market-of-the-week.html and the homepage card.
"""
import json, math, time, os
from datetime import datetime, timezone, timedelta

NOW = time.time()
ET = timezone(timedelta(hours=-5))          # EST (EDT in summer: the pick hour moves 1 h, harmless)
SITES = ("alpha", "polymarket", "kalshi")
NAMES = {"alpha": "Alpha Arcade", "polymarket": "Polymarket", "kalshi": "Kalshi"}
LO, HI = 30, 70                              # a real debate
MIN_DAYS, MAX_DAYS = 14, 60                  # settles in about 2-8 weeks
AGREE = 3.0                                  # two readings of the same site must agree within 3c
SPLIT = 10.0                                 # sites more than 10c apart = maybe not the same market
CONFIRM_GAP = 30 * 60                        # second reading at least 30 min after the first
NO_REPEAT = 8 * 7 * 86400
SPORTY = ("sport", "soccer", "football", "basketball", "baseball", "hockey", "nfl", "nba", "nhl", "mlb", "ufc",
          "tennis", "golf", "cricket", "f1", "esports")
DAILY = ("daily", "hit price", "price on", "up or down", "weekly", "# tweets", "traffic through")


def load(p, d):
    try:
        return json.load(open(p))
    except Exception:
        return d


def ts(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def price(site, x, outcome):
    o = x.get("outcomes") or {}
    if outcome in o:
        return o[outcome]
    if "Yes" in o and len(o) == 1:
        return o["Yes"]
    return next(iter(o.values())) if len(o) == 1 else None


def rules_ok(row):
    """A/B rules: every graded site says 'match' or 'similar'. Ungraded or 'differ' anywhere = not clear."""
    src = [x["fine"]["src"] for s, x in row["sites"].items() if x.get("fine")]
    if not src or any(s not in ("match", "similar") for s in src):
        return None
    return "A" if all(s == "match" for s in src) else "B"


def snapshot(row):
    """{site: price} for the row's matched outcome, plus totals."""
    out = row.get("outcome") or "Yes"
    ps = {}
    for s in SITES:
        x = row["sites"].get(s)
        if x:
            p = price(s, x, x.get("matched_outcome") if s != "alpha" else out)
            if p is None:
                p = price(s, x, out)
            if p is not None:
                ps[s] = round(float(p), 1)
    return ps


def candidates(matches, archive):
    recent = {a["key"] for a in archive if NOW - a.get("picked", 0) < NO_REPEAT}
    out = []
    for row in matches:
        cats = " ".join(row.get("categories") or []).lower()
        title = (row.get("title") or "").lower()
        if any(w in cats for w in SPORTY) or any(w in title for w in DAILY):
            continue
        c = ts(row.get("close"))
        if not c:
            continue
        days = (c - NOW) / 86400
        if not MIN_DAYS <= days <= MAX_DAYS:
            continue
        ps = snapshot(row)
        if len(ps) < 2:
            continue
        if max(ps.values()) - min(ps.values()) > SPLIT:
            continue                                         # sites disagree too much: maybe not the same market
        mid = sum(ps.values()) / len(ps)
        if not LO <= mid <= HI:
            continue
        grade = rules_ok(row)
        if not grade:
            continue
        key = row["title"] + "|" + (row.get("outcome") or "")
        if key in recent:
            continue
        vol = sum(float((row["sites"][s] or {}).get("volume24h") or 0) for s in ps)
        if vol < 1000:
            continue
        score = math.log10(vol + 10) * (1.5 if "alpha" in ps else 1) * (1.3 if len(ps) == 3 else 1) \
            * (1 - abs(mid - 50) / 100) * (1.05 if grade == "A" else 1)
        out.append({"key": key, "title": row["title"], "outcome": row.get("outcome") or "Yes", "close": row["close"],
                    "days": round(days), "prices": ps, "mid": round(mid, 1), "vol24": round(vol), "grade": grade,
                    "urls": {s: row["sites"][s]["url"] for s in row["sites"]}, "score": round(score, 3)})
    out.sort(key=lambda r: -r["score"])
    return out


def agree(a, b):
    return set(a) == set(b) and all(abs(a[s] - b[s]) <= AGREE for s in a)


def pick_time():
    """True from Monday 4 AM ET on: a new week's pick is due (staged, then approved)."""
    d = datetime.fromtimestamp(NOW, ET)
    return d.weekday() == 0 and d.hour >= 4


def week_start():
    d = datetime.fromtimestamp(NOW, ET)
    m = (d - timedelta(days=d.weekday())).replace(hour=4, minute=0, second=0, microsecond=0)
    return m.timestamp()


def find(matches, key):
    for row in matches:
        if row["title"] + "|" + (row.get("outcome") or "") == key:
            return row
    return None


def story_for(key):
    """Both Sides points with at least 2 independent sources each (different websites)."""
    st = load("motw_story.json", {})
    s = st.get(key)
    if not s:
        return None
    def ok(pt):
        hosts = {u.split("/")[2].replace("www.", "") for u in pt.get("sources", []) if u.startswith("http")}
        return len(hosts) >= 2
    clean = dict(s)
    dropped = 0
    for side in ("yes", "no"):
        pts = s.get(side) or []
        clean[side] = [p for p in pts if ok(p)]
        dropped += len(pts) - len(clean[side])
    clean["clock"] = [c for c in s.get("clock") or [] if ok(c)]
    clean["dropped"] = dropped
    print("Market of the Week: story has %d YES / %d NO points (%d dropped for fewer than 2 sources)"
          % (len(clean["yes"]), len(clean["no"]), dropped))
    return clean


def settle(entry, row):
    """Result once the close date has passed: YES/NO when every site is at 97c+ / 3c- on TWO readings in a row.
    If the market has dropped out of the feeds, the last confirmed prices are used."""
    if entry.get("result") or ts(entry["close"]) is None or NOW < ts(entry["close"]):
        return
    ps = (snapshot(row) if row else {}) or entry.get("now") or {}
    r = "YES" if ps and all(p >= 97 for p in ps.values()) else "NO" if ps and all(p <= 3 for p in ps.values()) else None
    if r and entry.get("settle_seen") == r:
        entry["result"] = r
        entry["resolved"] = round(NOW)
        print("Market of the Week: #%s settled %s (checked twice): %s" % (entry.get("n"), r, entry["title"]))
    else:
        entry["settle_seen"] = r
        if not r:
            print("Market of the Week: #%s closed, result not clear yet: %s %s" % (entry.get("n"), entry["title"], ps))


def slugify(t):
    import re
    s = re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")
    return s[:70].rstrip("-")


def write_page(e):
    """motw/<slug>.html: the main page's look, with the write-up written into the HTML for search engines;
    motw.js then fills in live prices. Rewritten each run, so it always matches motw.json."""
    import html as H, re
    try:
        tpl = open("market-of-the-week.html").read()
    except Exception:
        return
    st = e.get("story") or {}
    title = e["title"]
    desc = (st.get("hook") or ("Market of the Week: " + title + " Both sides, live prices on each site and the key dates.")).replace('"', "'")
    url = "https://alphainteldesk.com/motw/%s.html" % e["slug"]
    pg = re.sub(r"<title>.*?</title>", "<title>%s Odds, Both Sides and Key Dates | Market of the Week | Alpha Intel Desk</title>" % H.escape(title.rstrip("?")), tpl, count=1, flags=re.S)
    pg = re.sub(r'<meta name="description" content="[^"]*">', '<meta name="description" content="%s">' % H.escape(desc[:300]), pg, count=1)
    pg = pg.replace("https://alphainteldesk.com/market-of-the-week.html", url)
    pg = pg.replace('content="Market of the Week by Alpha Intel Desk"', 'content="%s | Market of the Week"' % H.escape(title))
    pg = pg.replace("<body>", '<body data-slug="%s">' % e["slug"], 1)
    li = lambda pts: "".join("<li>%s</li>" % H.escape(p["t"]) for p in pts)
    static = ('<p class="crumb"><a href="/market-of-the-week.html">&larr; Market of the Week</a></p>'
              '<span class="tag">Market of the Week #%s &middot; picked %s</span><h1>%s</h1>%s'
              '<h2>The case for YES</h2><ul>%s</ul><h2>The case for NO</h2><ul>%s</ul>%s'
              % (e.get("n", ""), datetime.fromtimestamp(e["picked"], ET).strftime("%b %-d, %Y"), H.escape(title),
                 '<p class="why">%s</p>' % H.escape(st["hook"]) if st.get("hook") else "", li(st.get("yes") or []), li(st.get("no") or []),
                 '<p>%s</p><p>%s</p>' % (H.escape(st.get("pay_yes", "")), H.escape(st.get("pay_no", ""))) if st.get("pay_yes") else ""))
    pg = re.sub(r'(<main class="wrap" id="mw">).*?(</main>)', lambda m: m.group(1) + static + m.group(2), pg, count=1, flags=re.S)
    os.makedirs("motw", exist_ok=True)
    path = "motw/%s.html" % e["slug"]
    old = open(path).read() if os.path.exists(path) else None
    if old != pg:
        open(path, "w").write(pg)
    try:                                                          # list it in the sitemap once
        sm = open("sitemap.xml").read()
        if url not in sm:
            sm = sm.replace("</urlset>", "  <url><loc>%s</loc><lastmod>%s</lastmod><changefreq>daily</changefreq><priority>0.7</priority></url>\n</urlset>"
                            % (url, datetime.now(timezone.utc).strftime("%Y-%m-%d")))
            open("sitemap.xml", "w").write(sm)
    except Exception:
        pass


def main():
    matches = load("matches.json", {}).get("matches", [])
    st = load("motw.json", {})
    cur, arch, pend = st.get("current"), st.get("archive", []), st.get("pending")
    if not matches:
        print("Market of the Week: no matches.json, nothing changed")
        return

    # 1) Nov 19 (James): Monday's pick is STAGED first (from 4 AM ET), then goes live only once James approves it.
    #    A scheduled task writes Both Sides at 5:47 AM ET and sends it to him; his OK sets "approved": true for that
    #    market in motw_story.json. Until then last week's pick stays live. (A pick made mid-week, like the first one
    #    on a Thursday, runs through the following Monday: 6+ days old.)
    nxt = st.get("next")
    due = nxt is None and (cur is None or (pick_time() and cur["picked"] < week_start() and NOW - cur["picked"] >= 6 * 86400))
    if due:
        cands = candidates(matches, arch + ([cur] if cur else []))
        top = cands[0] if cands else None
        if not top:
            print("Market of the Week: no market passes the formula this run")
        elif pend and pend["key"] == top["key"] and NOW - pend["seen"] >= CONFIRM_GAP and agree(pend["prices"], top["prices"]):
            nxt = dict(top, staged=round(NOW))
            pend = None
            print("Market of the Week: next pick STAGED (verified twice), waiting for James's OK: %s %s" % (nxt["title"], nxt["prices"]))
        else:
            if not pend or pend["key"] != top["key"] or not agree(pend["prices"], top["prices"]):
                pend = {"key": top["key"], "prices": top["prices"], "seen": round(NOW)}
            print("Market of the Week: candidate %s %s, waiting for a second matching reading" % (top["title"], top["prices"]))
    if nxt:
        if (load("motw_story.json", {}).get(nxt["key"]) or {}).get("approved") is True:
            row = find(matches, nxt["key"])
            ps = snapshot(row) if row else {}
            if not (ps and agree(nxt["prices"], ps)):
                ps = nxt["prices"]                                      # keep the verified staged prices
            if cur:                                                     # archive last week's pick
                cur["ended"] = round(NOW)
                arch.insert(0, cur)
            cur = dict(nxt, prices=ps, picked=round(NOW), picked_prices=ps, confirmed=ps, last_read=ps,
                       series=[[round(NOW)] + [ps.get(s) for s in SITES]], n=len(arch) + 1, slug=slugify(nxt["title"]))
            cur.pop("staged", None)
            nxt = None
            print("Market of the Week: NEW PICK LIVE (approved): %s %s" % (cur["title"], ps))
        else:
            print("Market of the Week: next pick %s staged, waiting for approval in motw_story.json" % nxt["title"])

    # 2) update the live pick: prices shown only when two readings agree
    if cur:
        row = find(matches, cur["key"])
        if row:
            ps = snapshot(row)
            last = cur.get("last_read") or {}
            if ps and agree(last, ps):
                cur["confirmed"] = ps
                cur["checked"] = round(NOW)
            cur["last_read"] = ps
            cur["vol24"] = round(sum(float((row["sites"][s] or {}).get("volume24h") or 0) for s in ps))
            if NOW - cur["series"][-1][0] >= 3300:                       # about hourly
                cur["series"].append([round(NOW)] + [cur["confirmed"].get(s) for s in SITES])
                cur["series"] = cur["series"][-24 * 60:]
        else:
            print("Market of the Week: current pick not in today's matches (kept, prices not updated)")
        cur["story"] = story_for(cur["key"])

    # 3) previous picks keep updating until they settle (same verify-twice rule for prices and results)
    for a in arch:
        if a.get("result"):
            continue
        row = find(matches, a["key"])
        if row:
            ps = snapshot(row)
            if ps and agree(a.get("last_read") or {}, ps):
                a["now"] = ps
                if NOW - (a.get("series") or [[0]])[-1][0] >= 3300:
                    a.setdefault("series", []).append([round(NOW)] + [ps.get(s) for s in SITES])
                    a["series"] = a["series"][-24 * 90:]
            a["last_read"] = ps
        settle(a, row)

    # 4) a permanent page per pick (Nov 19, James: look back at every Market of the Week)
    for e in ([cur] if cur else []) + arch:
        if not e.get("slug"):
            e["slug"] = slugify(e["title"])
        write_page(e)

    st = {"updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "current": cur,
          "pending": pend, "next": nxt, "archive": arch[:60], "sites": NAMES,
          "rule": "Every price shown was read twice and agreed within 3c. Every Both Sides point has 2+ independent sources."}
    json.dump(st, open("motw.json", "w"), separators=(",", ":"))


if __name__ == "__main__":
    main()
