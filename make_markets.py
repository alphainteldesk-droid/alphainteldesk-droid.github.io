# Alpha Intel Desk: builds markets.json (closing soon + new markets) from public Polymarket and Kalshi data.
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

# ================= NEW MARKETS (listed in the last 48 hours) =================
since = n - timedelta(hours=48)

def new_poly():
    base = ("https://gamma-api.polymarket.com/events?active=true&closed=false&limit=200"
            "&start_date_min=" + since.strftime(f))
    try:
        evs = get(base + "&order=volume24hr&ascending=false")
    except Exception:
        evs = get(base)
    v24 = lambda e: float(e.get("volume24hr") or 0)
    evs = [e for e in evs if v24(e) >= 1000 and "Up or Down" not in e.get("title", "")
           and e.get("markets")]
    evs = sorted(evs, key=v24, reverse=True)[:3]
    res = []
    for e in evs:
        m = max(e["markets"], key=lambda m: float(m.get("volumeNum") or m.get("volume") or 0))
        yes = float(json.loads(m.get("outcomePrices") or '["0"]')[0])
        res.append({"event": e["title"], "market": m.get("question", ""),
                    "opened": e.get("startDate") or e.get("createdAt"), "yes": round(yes * 100),
                    "volume": int(v24(e)), "url": "https://polymarket.com/event/" + e["slug"]})
    return res

def new_kalshi():
    ms, cur = [], ""
    for _ in range(5):
        d = get("https://api.elections.kalshi.com/trade-api/v2/markets?status=open&mve_filter=exclude"
                f"&limit=1000&min_created_ts={int(since.timestamp())}&cursor={cur}")
        ms += d["markets"]
        cur = d.get("cursor") or ""
        if not cur:
            break
    ms = [m for m in ms if kv(m) >= 100]
    ms = sorted(top_per_event(ms, lambda m: m["event_ticker"], kv), key=kv, reverse=True)[:3]
    res = []
    for m in ms:
        ev = get("https://api.elections.kalshi.com/trade-api/v2/events/" + m["event_ticker"])["event"]
        yes = m.get("last_price_dollars") or m.get("yes_bid_dollars") or "0"
        res.append({"event": ev.get("title"), "market": m.get("yes_sub_title") or m["title"],
                    "opened": m.get("open_time") or m.get("created_time"), "yes": round(float(yes) * 100),
                    "volume": int(kv(m)),
                    "url": "https://kalshi.com/markets/" + ev.get("series_ticker", "").lower()})
    return res

new = {}
for name, fn in (("polymarket", new_poly), ("kalshi", new_kalshi)):
    try:
        new[name] = fn()
    except Exception as err:
        print("New markets", name, "failed:", err)
        new[name] = []

# ================= ALPHA ARCADE (public market list via the Alpha Partners API) =================
# Needs the GitHub secret ALPHA_API_KEY. Public market data only: no wallet, no orders.
import os

def alpha_markets():
    key = os.environ.get("ALPHA_API_KEY")
    if not key:
        print("Alpha Arcade skipped: no ALPHA_API_KEY secret")
        return [], []
    req = urllib.request.Request("https://platform.alphaarcade.com/api/get-live-markets",
                                 headers={"x-api-key": key, "User-Agent": "AlphaIntelDesk/1.0"})
    import time
    for attempt in range(3):   # Alpha Arcade sometimes returns a brief 502: try up to 3 times
        try:
            d = json.load(urllib.request.urlopen(req, timeout=30)); break
        except Exception as err:
            if attempt == 2: raise
            print("Alpha Arcade try", attempt + 1, "failed:", err, "- retrying in 10 s")
            time.sleep(10)
    ms = d if isinstance(d, list) else d.get("markets", [])
    ms = [m for m in ms if not m.get("hidden")]
    if ms:   # first runs: show which fields exist, so the boxes can be finished
        print("Alpha Arcade:", len(ms), "live markets. Fields:", sorted(ms[0].keys()))
        print("Alpha Arcade sample:", json.dumps({k: ms[0].get(k) for k in sorted(ms[0].keys())
              if not isinstance(ms[0].get(k), (list, dict))})[:900])
        wo = next((m for m in ms if m.get("options") and float(m.get("volume") or 0) > 0), None)
        if wo:
            o = wo["options"][0]
            print("Alpha Arcade options:", len(wo["options"]), "in", wo.get("slug"), "| option fields:", sorted(o.keys()))
            print("Alpha Arcade option sample:", json.dumps({k: o.get(k) for k in sorted(o.keys())
                  if not isinstance(o.get(k), (list, dict))})[:700])
    def secs(v):
        v = float(v or 0)
        return v / 1000 if v > 1e11 else v
    def prob(m):
        p = m.get("yesProb")
        if p is None and m.get("options"):
            p = max((o.get("yesProb") or 0) for o in m["options"])
        p = float(p or 0)
        return p / 1e6 if p > 100 else (p / 100 if p > 1 else p)
    av = lambda m: float(m.get("volume") or 0)
    url = lambda m: "https://www.alphaarcade.com/market/" + m["slug"] if m.get("slug") else "https://www.alphaarcade.com"
    now = n.timestamp()
    def row(m, extra):
        r = {"event": m.get("title") or m.get("topic") or "", "market": "", "yes": round(prob(m) * 100),
             "volume": int(av(m)), "url": url(m)}
        r.update(extra)
        return r
    soon = [m for m in ms if now < secs(m.get("endTs")) <= now + 7 * 86400]
    soon = sorted(sorted(soon, key=av, reverse=True)[:3], key=lambda m: secs(m.get("endTs")))
    soon = [row(m, {"closes": datetime.fromtimestamp(secs(m["endTs"]), timezone.utc).strftime(f)}) for m in soon]
    made = lambda m: secs(m.get("createdAt") or m.get("created_at") or m.get("createdTs") or 0)
    fresh = [m for m in ms if made(m) >= since.timestamp()]
    fresh = sorted(fresh, key=av, reverse=True)[:3]
    fresh = [row(m, {"opened": datetime.fromtimestamp(made(m), timezone.utc).strftime(f)}) for m in fresh]
    return soon, fresh

try:
    alpha_soon, alpha_new = alpha_markets()
except Exception as err:
    print("Alpha Arcade failed:", err, "- keeping the last good Alpha Arcade data")
    try:
        old = json.load(open("markets.json"))
        alpha_soon = old.get("closing_soon", {}).get("alpha", [])
        alpha_new = old.get("new_markets", {}).get("alpha", [])
    except Exception:
        alpha_soon, alpha_new = [], []

out = {"updated": n.strftime(f), "closing_soon": {"polymarket": poly, "kalshi": kal, "alpha": alpha_soon},
       "new_markets": dict(new, alpha=alpha_new)}
with open("markets.json", "w") as fh:
    json.dump(out, fh, indent=2)
print("Wrote markets.json:", len(poly), "Polymarket,", len(kal), "Kalshi closing soon |",
      len(new["polymarket"]), "Polymarket,", len(new["kalshi"]), "Kalshi new |",
      len(alpha_soon), "Alpha closing,", len(alpha_new), "Alpha new")
