# Alpha Intel Desk: builds desk.json for the "Live Intel Desk" screens on the homepage banner.
# Markets (delayed quotes), oil, DXY, 10-year, VIX, crypto and Google Trends (US + UK).
# Public data only. Runs every hour from the Update markets workflow.
import json, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

UA = {"User-Agent": "Mozilla/5.0 (AlphaIntelDesk/1.0)"}

def get(url, raw=False):
    req = urllib.request.Request(url, headers=UA)
    data = urllib.request.urlopen(req, timeout=30).read()
    return data if raw else json.loads(data)

# name shown on the desk -> Yahoo Finance symbol
QUOTES = [("dow", "^DJI"), ("sp500", "^GSPC"), ("nasdaq", "^IXIC"), ("vix", "^VIX"), ("brent", "BZ=F"),
          ("wti", "CL=F"), ("dxy", "DX-Y.NYB"), ("tnx", "^TNX")]

def quote(sym):
    s = urllib.request.quote(sym)
    for host in ("query1", "query2"):
        try:
            m = get(f"https://{host}.finance.yahoo.com/v8/finance/chart/{s}?range=1d&interval=5m")
            m = m["chart"]["result"][0]["meta"]
            price = float(m["regularMarketPrice"])
            prev = float(m.get("chartPreviousClose") or m.get("previousClose") or price)
            if sym == "^TNX" and price > 20:   # older feeds give yield x10
                price, prev = price / 10, prev / 10
            return {"price": round(price, 4), "change": round((price - prev) / prev * 100, 2) if prev else 0,
                    "time": datetime.fromtimestamp(m["regularMarketTime"], timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        except Exception as err:
            last = err
    print("Quote", sym, "failed:", last)
    return None

def crypto():
    d = get("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,algorand"
            "&vs_currencies=usd&include_24hr_change=true")
    out = {}
    for key, cid in (("btc", "bitcoin"), ("eth", "ethereum"), ("algo", "algorand")):
        c = d.get(cid) or {}
        if "usd" in c:
            out[key] = {"price": c["usd"], "change": round(c.get("usd_24h_change") or 0, 2)}
    return out

def trends(geo, n=3):
    root = ET.fromstring(get(f"https://trends.google.com/trending/rss?geo={geo}", raw=True))
    return [{"geo": "UK" if geo == "GB" else geo, "title": (i.findtext("title") or "").strip()}
            for i in root.iter("item")][:n]

out = {"updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "quotes": {}}
for name, sym in QUOTES:
    q = quote(sym)
    if q:
        out["quotes"][name] = q
for key, fn in (("crypto", crypto), ("trends_us", lambda: trends("US", 5)), ("trends_uk", lambda: trends("GB", 5))):
    try:
        out[key] = fn()
    except Exception as err:
        print(key, "failed:", err)
        out[key] = {} if key == "crypto" else []

# Interleave US and UK trends: US, UK, US, UK...
out["trends"] = [t for pair in zip(out.pop("trends_us"), out.pop("trends_uk")) for t in pair]

with open("desk.json", "w") as fh:
    json.dump(out, fh, indent=1, ensure_ascii=False)
print("Wrote desk.json:", len(out["quotes"]), "of", len(QUOTES), "quotes |",
      len(out["crypto"]), "crypto |", len(out["trends"]), "trends")
