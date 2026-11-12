# Alpha Intel Desk: builds markets.json (closing soon + new markets) from public Polymarket and Kalshi data.
import json, time, urllib.request
from datetime import datetime, timezone, timedelta

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "AlphaIntelDesk/1.0", "Accept": "application/json"})
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
    import polyapi                                     # Nov 12: keyset list, old list as backup
    try:
        evs = polyapi.events({"start_date_min": since.strftime(f), "order": "volume24hr", "ascending": "false"},
                             max_events=200)
    except Exception:
        evs = polyapi.events({"start_date_min": since.strftime(f)}, max_events=200)
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

def alpha_from_api():
    key = os.environ.get("ALPHA_API_KEY")
    if not key:
        raise Exception("no ALPHA_API_KEY secret")
    req = urllib.request.Request("https://platform.alphaarcade.com/api/get-live-markets",
                                 headers={"x-api-key": key, "User-Agent": "curl/8.5.0", "Accept": "*/*"})
    import time, re
    for attempt in range(3):   # Alpha Arcade sometimes returns a 502 to GitHub: try 3 times
        try:
            d = json.load(urllib.request.urlopen(req, timeout=45)); break
        except Exception as err:
            body = ""
            if hasattr(err, "read"):
                try:
                    page = err.read().decode("utf-8", "replace")
                    ray = re.search(r"Ray ID:?\s*(?:<[^>]+>\s*)*([0-9a-f]{12,20})", page)
                    body = "Cloudflare Ray ID " + ray.group(1) if ray else page[:80].replace("\n", " ")
                except Exception: pass
            print("Alpha Arcade try", attempt + 1, "failed:", err, "|", body or "(no details)")
            if attempt == 2: raise
            time.sleep(15)
    return d if isinstance(d, list) else d.get("markets", [])

def alpha_from_bridge():
    """alpha_live.json is uploaded by the Chromebook bridge (alpha_bridge.py) when GitHub can't reach Alpha Arcade."""
    b = json.load(open("alpha_live.json"))
    age = (n - datetime.strptime(b["updated"], f).replace(tzinfo=timezone.utc)).total_seconds() / 3600
    if age > 36:
        raise Exception("alpha_live.json is %.0f hours old" % age)
    print("Alpha Arcade: using alpha_live.json from the Chromebook bridge (%.1f h old)" % age)
    return b["markets"]

# Alpha Arcade blocks GitHub's servers (Cloudflare 502), so the Chromebook bridge supplies the data.
# When Alpha Arcade fixes it, change False to True to call the API from GitHub again (bridge stays the backup).
USE_ALPHA_API = False

def alpha_markets():
    if USE_ALPHA_API:
        try:
            ms = alpha_from_api(); src = "API"
        except Exception as err:
            print("Alpha Arcade API failed:", err, "- trying the Chromebook bridge file")
            ms = alpha_from_bridge(); src = "bridge"
    else:
        ms = alpha_from_bridge(); src = "bridge"
    ms = [m for m in ms if not m.get("hidden")]
    def secs(v):
        v = float(v or 0)
        return v / 1000 if v > 1e11 else v
    def top(m):
        """(label, prob 0-1) of the leading outcome. Prices are in millionths: 1,000,000 = 100%."""
        opts = m.get("options") or []
        if not opts:
            return "", 0.0
        if len(opts) == 1 or all((o.get("label") or "").lower() in ("yes", "no") for o in opts):
            o = next((o for o in opts if (o.get("label") or "").lower() == "yes"), opts[0])
            return "", float(o.get("yesProb") or 0) / 1e6
        o = max(opts, key=lambda o: float(o.get("yesProb") or 0))
        return o.get("label") or "", float(o.get("yesProb") or 0) / 1e6
    av = lambda m: float(m.get("volume") or 0)
    url = lambda m: "https://www.alphaarcade.com/market/" + m["slug"] if m.get("slug") else "https://www.alphaarcade.com"
    priced = [m for m in ms if top(m)[1] > 0]          # skip markets with no price yet
    now = n.timestamp()
    def row(m, extra):
        label, p = top(m)
        r = {"event": m.get("title") or "", "market": label, "yes": round(p * 100),
             "volume": int(av(m)), "url": url(m)}
        r.update(extra)
        return r
    soon = [m for m in priced if now < secs(m.get("endTs")) <= now + 7 * 86400]
    soon = sorted(sorted(soon, key=av, reverse=True)[:3], key=lambda m: secs(m.get("endTs")))
    soon = [row(m, {"closes": datetime.fromtimestamp(secs(m["endTs"]), timezone.utc).strftime(f)}) for m in soon]
    made = lambda m: secs(m.get("createdAt") or 0)
    fresh = [m for m in priced if made(m) >= since.timestamp()]
    fresh = sorted(fresh, key=av, reverse=True)[:3]
    fresh = [row(m, {"opened": datetime.fromtimestamp(made(m), timezone.utc).strftime(f)}) for m in fresh]
    print("Alpha Arcade (%s): %d live, %d with a price" % (src, len(ms), len(priced)))
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
