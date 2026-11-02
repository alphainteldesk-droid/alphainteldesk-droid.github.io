# Alpha Intel Desk: builds markets.json (closing soon) from public Polymarket and Kalshi data.
import json, time, urllib.request
from datetime import datetime, timezone, timedelta

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "AlphaIntelDesk/1.0"})
    return json.load(urllib.request.urlopen(req, timeout=30))

def top_per_event(ms, key, vol):
    best = {}
    for m in ms:
        k = key(m)
        if k not in best or vol(m) > vol(best[k]):
            best[k] = m
    return list(best.values())

def pick3(ms, vol, close):
    return sorted(sorted(ms, key=vol, reverse=True)[:3], key=close)

n = datetime.now(timezone.utc)
f = "%Y-%m-%dT%H:%M:%SZ"

# --- Polymarket: closes within 7 days, $50k+ volume, no 5-minute crypto markets ---
pm = get("https://gamma-api.polymarket.com/markets?active=true&closed=false&limit=500&end_date_min="
         + n.strftime(f) + "&end_date_max=" + (n + timedelta(days=7)).strftime(f))
pv = lambda m: float(m.get("volumeNum") or 0)
pev = lambda m: (m.get("events") or [{}])[0]
pm = [m for m in pm if pv(m) >= 50000 and "Up or Down" not in m["question"]]
pm = pick3(top_per_event(pm, lambda m: pev(m).get("slug", m["slug"]), pv), pv, lambda m: m["endDate"])
poly = []
for m in pm:
    yes = float(json.loads(m.get("outcomePrices") or '["0"]')[0])
    poly.append({"event": pev(m).get("title", m["question"]), "market": m["question"],
                 "closes": m["endDate"], "yes": round(yes * 100), "volume": int(pv(m)),
                 "url": "https://polymarket.com/event/" + pev(m).get("slug", m["slug"])})

# --- Kalshi: closes within 7 days, 10k+ contracts, no combo markets ---
t = int(time.time())
ks, cur = [], ""
for _ in range(5):
    d = get("https://api.elections.kalshi.com/trade-api/v2/markets?status=open&mve_filter=exclude"
            f"&limit=1000&min_close_ts={t}&max_close_ts={t + 604800}&cursor={cur}")
    ks += d["markets"]
    cur = d.get("cursor") or ""
    if not cur:
        break
kv = lambda m: float(m.get("volume_fp") or 0)
ks = pick3(top_per_event([m for m in ks if kv(m) >= 10000], lambda m: m["event_ticker"], kv),
           kv, lambda m: m["close_time"])
kal = []
for m in ks:
    ev = get("https://api.elections.kalshi.com/trade-api/v2/events/" + m["event_ticker"])["event"]
    yes = m.get("last_price_dollars") or m.get("yes_bid_dollars") or "0"
    kal.append({"event": ev.get("title"), "market": m.get("yes_sub_title") or m["title"],
                "closes": m["close_time"], "yes": round(float(yes) * 100), "volume": int(kv(m)),
                "url": "https://kalshi.com/markets/" + ev.get("series_ticker", "").lower()})

out = {"updated": n.strftime(f), "closing_soon": {"polymarket": poly, "kalshi": kal}}
with open("markets.json", "w") as fh:
    json.dump(out, fh, indent=2)
print("Wrote markets.json:", len(poly), "Polymarket,", len(kal), "Kalshi")
