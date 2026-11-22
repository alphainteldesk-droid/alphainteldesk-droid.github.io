"""Nov 21 (James): Live Gap Chart. Real price history for every gap on the Gap Scanner (gaps.json order;
[0] = today's biggest, shown on the homepage first screen and the top of the Gap Scanner page).

Writes gap_chart.json for the animated chart on the Gap Scanner page:
  - Polymarket: CLOB prices-history for the gap's outcome token (hourly, last 7 days)
  - Kalshi: hourly candlesticks for the gap's market (midpoint of yes bid/ask, else last trade)
  - Alpha Arcade: no public history, so our own snapshots: alpha_hist.json (last ~26 h, feed prices)
    plus gap_chart_hist.json (the Gap Scanner's own Alpha price every run, kept 8 days)
Never raises: if a site's history can't be read, its line is just the points we have.
"""
import json, time, urllib.request
from datetime import datetime, timezone

DAYS = 7
NOW = time.time()
START = NOW - DAYS * 86400
KEEP = 8 * 86400


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "alphainteldesk/1.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def load(path, default):
    try:
        return json.load(open(path))
    except Exception:
        return default


def poly_hist(token):
    d = get("https://clob.polymarket.com/prices-history?market=%s&startTs=%d&endTs=%d&fidelity=60"
            % (token, START, NOW))
    return [[int(x["t"]), round(float(x["p"]) * 100, 2)] for x in d.get("history") or []]


def _norm(x):
    return "".join(ch for ch in (x or "").lower() if ch.isalnum())


def poly_token(url, outcome):
    """Polymarket only stores one outcome's token in matches.json: find the others from the event page's markets."""
    slug = (url or "").rstrip("/").split("?")[0].split("/")[-1]
    if not slug:
        return None
    ev = get("https://gamma-api.polymarket.com/events?slug=" + slug)
    ev = ev[0] if isinstance(ev, list) and ev else ev
    want = _norm(outcome)
    for m in (ev or {}).get("markets") or []:
        names = [m.get("groupItemTitle"), m.get("question")]
        if any(_norm(n) == want for n in names if n) or (len(ev.get("markets")) == 1 and want == "yes"):
            ids = m.get("clobTokenIds")
            ids = json.loads(ids) if isinstance(ids, str) else ids
            return ids[0] if ids else None
    return None


def _c(o, key):
    """Kalshi candle value in cents: newer API gives *_dollars strings, older gives cents."""
    if not isinstance(o, dict):
        return None
    if o.get(key + "_dollars") not in (None, ""):
        return float(o[key + "_dollars"]) * 100
    if o.get(key) is not None:
        return float(o[key])
    return None


def kalshi_hist(ticker):
    series = ticker.split("-")[0]
    try:
        d = get("https://api.elections.kalshi.com/trade-api/v2/series/%s/markets/%s/candlesticks"
                "?start_ts=%d&end_ts=%d&period_interval=60" % (series, ticker, START, NOW))
    except Exception:                                  # series ticker not the prefix: look it up
        ev = get("https://api.elections.kalshi.com/trade-api/v2/markets/" + ticker)["market"]["event_ticker"]
        series = get("https://api.elections.kalshi.com/trade-api/v2/events/" + ev)["event"]["series_ticker"]
        d = get("https://api.elections.kalshi.com/trade-api/v2/series/%s/markets/%s/candlesticks"
                "?start_ts=%d&end_ts=%d&period_interval=60" % (series, ticker, START, NOW))
    out = []
    for c in d.get("candlesticks") or []:
        b, a = _c(c.get("yes_bid"), "close"), _c(c.get("yes_ask"), "close")
        p = (a + b) / 2 if (a is not None and b is not None and 0 < b <= a < 100 and a - b <= 10) else _c(c.get("price"), "close")
        if p is not None and 0 < p < 100:
            out.append([int(c["end_period_ts"]), round(p, 2)])
    return out


def key(g):
    return g["title"] + "|" + g["outcome"]


def main():
    gaps = load("gaps.json", {}).get("gaps") or []
    if not gaps:
        print("Gap chart: no gaps, nothing to draw")
        return
    rows = {(m["title"], m.get("close")): m for m in load("matches.json", {}).get("matches") or []}

    # 1. our own record of every listed gap's prices (this is the only history Alpha Arcade has)
    hist = load("gap_chart_hist.json", {})
    for g in gaps:
        hist.setdefault(key(g), []).append([int(NOW)] + [g["prices"].get(s) for s in ("polymarket", "kalshi", "alpha")])
    hist = {k: [p for p in v if NOW - p[0] <= KEEP] for k, v in hist.items()}
    hist = {k: v for k, v in hist.items() if v}
    json.dump(hist, open("gap_chart_hist.json", "w"), separators=(",", ":"))

    alive = {}
    try:
        al = load("alpha_live.json", {}).get("markets") or []
        alive = {m.get("slug"): m["id"] for m in al if m.get("id")}
    except Exception:
        pass
    ahist = load("alpha_hist.json", [])
    out_gaps = []
    for g in gaps:
        if time.time() - NOW > 90:                                  # never hold up the update run
            print("  Gap chart: time budget used, %d of %d gaps charted" % (len(out_gaps), len(gaps)))
            break
        out_gaps.append(chart_one(g, rows, hist, alive, ahist))
    out = {"updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "days": DAYS, "gaps": out_gaps}
    json.dump(out, open("gap_chart.json", "w"), separators=(",", ":"))
    print("Gap chart: %d gaps charted | top: %s | %s" % (len(out_gaps), gaps[0]["title"][:50], gaps[0]["outcome"][:20]))


def chart_one(g, rows, hist, alive, ahist):
    row = rows.get((g["title"], g.get("close"))) or {}
    sites = row.get("sites") or {}
    series = {}
    for s in ("polymarket", "kalshi", "alpha"):
        if g["prices"].get(s) is None:
            continue
        pts = []
        try:
            if s == "polymarket":
                tok = (sites.get(s, {}).get("book") or {}).get(g["outcome"]) or \
                    poly_token((g.get("urls") or {}).get(s) or sites.get(s, {}).get("url"), g["outcome"])
                pts = poly_hist(tok) if tok else []
            elif s == "kalshi":
                tk = (sites.get(s, {}).get("book") or {}).get(g["outcome"])
                pts = kalshi_hist(tk) if tk else []
            else:
                slug = (sites.get(s, {}).get("url") or "").rstrip("/").split("/")[-1]
                aid = alive.get(slug)
                if aid:
                    for h in ahist:
                        v = (h.get("p", {}).get(aid) or {}).get(g["outcome"])
                        if v is not None:
                            pts.append([int(h["t"]), round(float(v), 2)])
        except Exception as err:
            print("  Gap chart: %s history failed | %s | %s" % (s, g["title"][:40], err))
        i = ("polymarket", "kalshi", "alpha").index(s)          # + the Gap Scanner's own checks (Alpha = book mid)
        own = [[p[0], p[1 + i]] for p in hist.get(key(g), []) if p[1 + i] is not None]
        if s == "alpha" or len(pts) < 2:
            pts += own
        pts = sorted({int(t): v for t, v in pts if t >= START}.items())
        pts = [[t, v] for t, v in pts]
        if not pts or pts[-1][0] < NOW - 600:
            pts.append([int(NOW), g["prices"][s]])                # end every line at the price the Gap Scanner shows now
        else:
            pts[-1][1] = g["prices"][s]
        series[s] = pts
    print("  Gap chart: %s | %s | %s" % (g["title"][:40], g["outcome"][:16], ", ".join("%s %d" % (k, len(v)) for k, v in series.items())))
    return {"title": g["title"], "outcome": g["outcome"], "close": g.get("close"),
            "prices": g["prices"], "low": g["low"], "high": g["high"],
            "raw": g.get("raw"), "fees": g.get("fees"), "net": g.get("net"), "grade": g.get("grade"),
            "all3": g.get("all3"), "series": series}


if __name__ == "__main__":
    main()
