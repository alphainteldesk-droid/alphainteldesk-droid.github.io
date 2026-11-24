"""Most traded today (Nov 24, 2026, James): the 10 busiest non-sports markets on Polymarket and Kalshi by 24 h volume.
Alpha Arcade's list is built on the page from alpha_live.json. Writes most_traded.json; refreshes at most every 50 min."""
import json, re, time, urllib.parse, urllib.request
from datetime import datetime, timezone

NOW = time.time()
UA = {"User-Agent": "Mozilla/5.0 (compatible; AlphaIntelDesk/1.0; +https://alphainteldesk.com)"}
SPORTS = re.compile(r"\b(nfl|nba|wnba|nhl|mlb|mls|ncaa\w*|ufc|epl|premier league|champions league|la liga|serie a|bundesliga|"
                    r"ligue 1|fifa|world cup|super bowl|stanley cup|world series|grand prix|f1|nascar|pga|golf|tennis|atp|wta|"
                    r"cricket|ipl|t20|boxing|esports|dota|cs2|valorant|league of legends|olympic|heisman|mvp|vs\.?|@)\b", re.I)


def get(url, timeout=30):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as e:
        print("  MT feed failed:", url[:90], str(e)[:80])
        return None


try:
    prev = json.load(open("most_traded.json"))
except Exception:
    prev = {}
if NOW - prev.get("at", 0) < 50 * 60:
    print("Most traded: fresh, skipped")
    raise SystemExit
out = {"at": NOW, "polymarket": prev.get("polymarket") or [], "kalshi": prev.get("kalshi") or []}

# Polymarket: events sorted by 24 h volume (sports tags and titles left out)
d = None
for q in ({"active": "true", "closed": "false", "order": "volume24hr", "ascending": "false", "limit": 80},
          {"closed": "false", "order": "volume24hr", "ascending": "false", "limit": 80},
          {"closed": "false", "order": "volume24hr", "limit": 80}):
    d = get("https://gamma-api.polymarket.com/events?" + urllib.parse.urlencode(q))
    if d:
        break
if not d:                                          # fallback: busiest markets, grouped into their events
    ms = get("https://gamma-api.polymarket.com/markets?" + urllib.parse.urlencode(
        {"closed": "false", "order": "volume24hr", "ascending": "false", "limit": 200})) or []
    by = {}
    for m in ms:
        ev = (m.get("events") or [{}])[0]
        e = by.setdefault(ev.get("slug") or m.get("slug"), {"title": ev.get("title") or m.get("question"), "slug": ev.get("slug") or m.get("slug"),
                                                            "tags": ev.get("tags") or [], "volume24hr": 0, "markets": []})
        e["volume24hr"] += float(m.get("volume24hr") or 0); e["markets"].append(m)
    d = sorted(by.values(), key=lambda e: -e["volume24hr"]) or None
    print("  Polymarket via markets fallback:", len(by))
if d:
    rows = []
    for ev in d:
        tags = " ".join((t.get("slug") or "") + " " + (t.get("label") or "") for t in ev.get("tags") or [])
        if re.search(r"sport|soccer|football|basketball|baseball|hockey|tennis|golf|esports|mma|cricket|nfl|nba|mlb|nhl", tags, re.I) \
                or SPORTS.search(ev.get("title") or ""):
            continue
        best, bp = None, -1
        for m in ev.get("markets") or []:
            if m.get("closed"):
                continue
            try:
                yes = float(json.loads(m.get("outcomePrices") or "[]")[0]) * 100
            except Exception:
                continue
            if yes > bp:
                best, bp = m, yes
        if not best:
            continue
        multi = len([m for m in ev.get("markets") or [] if not m.get("closed")]) > 1
        rows.append({"title": ev.get("title"), "lead": (best.get("groupItemTitle") or "Yes") if multi else "Yes", "price": round(bp, 1),
                     "vol24": round(float(ev.get("volume24hr") or 0)), "url": "https://polymarket.com/event/" + (ev.get("slug") or "")})
        if len(rows) == 10:
            break
    if rows:
        out["polymarket"] = rows

# Kalshi: open events with their markets, grouped, non-sports categories, by 24 h volume
evs, cur = [], None
for _ in range(70):
    q = {"status": "open", "with_nested_markets": "true", "limit": 200}
    if cur:
        q["cursor"] = cur
    d = get("https://api.elections.kalshi.com/trade-api/v2/events?" + urllib.parse.urlencode(q))
    if not d:
        break
    evs += d.get("events") or []
    cur = d.get("cursor")
    if not cur:
        break
print("Kalshi events read:", len(evs))


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


rows = []
for ev in evs:
    if re.search(r"sport", ev.get("category") or "", re.I) or SPORTS.search(ev.get("title") or ""):
        continue
    ms = ev.get("markets") or []
    vol = sum(num(m.get("volume_24h_fp") or m.get("volume_24h")) for m in ms)
    if vol <= 0:
        continue
    def px(m):
        for k in ("last_price_dollars", "yes_bid_dollars"):
            if num(m.get(k)) > 0:
                return num(m[k]) * 100
        return num(m.get("last_price"))
    best = max(ms, key=px)
    rows.append({"title": ev.get("title"), "lead": (best.get("yes_sub_title") or "Yes") if len(ms) > 1 else "Yes", "price": round(px(best), 1),
                 "vol24": round(vol), "url": "https://kalshi.com/markets/" + (ev.get("series_ticker") or "").lower()})
rows.sort(key=lambda r: -r["vol24"])
if rows:
    out["kalshi"] = rows[:10]

out["updated"] = datetime.fromtimestamp(NOW, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
print("Most traded:", {k: len(out[k]) for k in ("polymarket", "kalshi")}, [r["title"][:40] for r in out["kalshi"][:3]])
json.dump(out, open("most_traded.json", "w"), separators=(",", ":"))
