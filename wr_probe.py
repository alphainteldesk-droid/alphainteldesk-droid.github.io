import json, time, urllib.parse, urllib.request
UA = {"User-Agent": "AlphaIntelDesk/1.0 (+https://alphainteldesk.com)"}
def get(u, t=40):
    t0 = time.time()
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=t) as r:
            b = r.read(); return r.status, b, round(time.time() - t0, 1)
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:300], round(time.time() - t0, 1)
    except Exception as e:
        return 0, str(e).encode(), round(time.time() - t0, 1)
# 1. military flights
for src in ("https://api.adsb.lol/v2/mil", "https://api.airplanes.live/v2/mil", "https://opendata.adsb.fi/api/v2/mil"):
    s, b, dt = get(src)
    try:
        ac = json.loads(b).get("ac") or []
    except Exception:
        ac = []
    print("MIL", src, s, dt, "s", len(ac), "aircraft")
    if ac:
        from collections import Counter
        print("  types", Counter(a.get("t") for a in ac).most_common(40))
        print("  with pos", sum(1 for a in ac if a.get("lat") is not None))
        BOX = {"Gulf": (22, 38, 44, 63), "Levant": (29, 34.5, 33, 37.5), "RedSea": (10, 22, 36, 52), "UkrRus": (44, 57, 22, 45),
               "Taiwan": (5, 28, 105, 125), "Korea": (33, 43, 124, 132), "Carib": (5, 27, -85, -58), "SAsia": (23, 37, 66, 80)}
        for k, (a1, a2, o1, o2) in BOX.items():
            inb = [a for a in ac if a.get("lat") is not None and a1 <= a["lat"] <= a2 and o1 <= a["lon"] <= o2]
            print("  ", k, len(inb), Counter(a.get("t") for a in inb).most_common(8), [ (a.get("flight") or "").strip() for a in inb][:8])
        print("  sample", json.dumps(ac[0])[:400])
    time.sleep(2)
# 2. GDELT
for q in ('(Iran OR Tehran OR Hormuz) (strike OR missile OR attack OR military OR navy)', '(Taiwan OR "South China Sea") (military OR drills OR warships OR invasion)'):
    u = "https://api.gdeltproject.org/api/v2/doc/doc?" + urllib.parse.urlencode({"query": q + " sourcelang:english", "mode": "timelinevolraw", "format": "json", "timespan": "30d"})
    s, b, dt = get(u, 60)
    print("GDELT", s, dt, b[:200])
    try:
        j = json.loads(b); tl = j["timeline"][0]["data"]; print("  points", len(tl), tl[:2], tl[-3:])
    except Exception as e:
        print("  parse", e)
    time.sleep(6)
# 3. Google Trends RSS per country
for geo in ("US", "GB", "IL", "UA", "RU", "TW", "KR", "IN", "PK", "TR", "AE", "SA", "PH", "JP", "VE", "CO", "IR", "LB", "YE"):
    s, b, dt = get("https://trends.google.com/trending/rss?geo=" + geo)
    n = b.count(b"<item>")
    import re
    titles = re.findall(rb"<title>([^<]+)</title>", b)[1:6]
    print("TRENDS", geo, s, n, [t.decode("utf-8", "replace") for t in titles])
    time.sleep(0.5)
# 4. PortWatch latest for Hormuz + Bab el-Mandeb
base = "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/Daily_Chokepoints_Data/FeatureServer/0/query?"
for nm in ("Strait of Hormuz", "Bab el-Mandeb Strait", "Suez Canal", "Panama Canal"):
    u = base + urllib.parse.urlencode({"where": "portname='%s'" % nm, "outFields": "date,portid,portname,n_total,n_tanker,capacity", "orderByFields": "date DESC", "resultRecordCount": 10, "f": "json"})
    s, b, dt = get(u, 60)
    try:
        fs = [f["attributes"] for f in json.loads(b)["features"]]
        print("PORTWATCH", nm, s, dt, [(time.strftime("%Y-%m-%d", time.gmtime(f["date"] / 1000)) if isinstance(f["date"], (int, float)) else f["date"], f["n_total"]) for f in fs][:10], fs[0].get("portid") if fs else None)
    except Exception as e:
        print("PORTWATCH", nm, s, b[:300], e)
# 5. USDC on Algorand
IDX = "https://mainnet-idx.algonode.cloud/v2"
s, b, dt = get(IDX + "/assets/31566704")
a = json.loads(b)["asset"]["params"]; print("USDC asset", a.get("total"), a.get("decimals"), a.get("reserve"))
s, b, dt = get(IDX + "/accounts/" + a["reserve"] + "/assets?asset-id=31566704")
print("reserve holding", b[:300])
print("DONE")
