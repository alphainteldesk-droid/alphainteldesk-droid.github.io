"""War Room (Nov 24, 2026, James): connect the dots between independent signals per hotspot and score them 0-100.

Signals per hotspot (each scored against its own normal, learned in warroom_hist.json):
  flights  - military aircraft near the region (adsb.lol + adsb.fi, open data); notable types count extra
  news     - GDELT 2.0: conflict stories about the region in the last 24 h vs its 4-week daily average
  trends   - Google Trends daily searches in the region's countries that are about conflict (multi-language)
  radar    - our Conflict Radar headlines (desk.json) about the region
  markets  - the biggest 24 h price move on the region's prediction markets (movers.json + Alpha history)
  ships    - IMF PortWatch transit calls through the region's chokepoints vs their 30-day normal (a drop = stress)
Heat = half "how much is going on" (level, compared across hotspots) + half "how unusual is it" (vs its own normal).
Also writes the Chokepoint Watch (PortWatch, incl. the 7-day average the Alpha Hormuz market settles on) and
the USDC-on-Algorand tracker (issued supply as defined in the Alpha market's own rules).
Writes warroom.json (page) + warroom_hist.json (baselines). Runs inside "Update markets"; does the slow feeds
(GDELT, PortWatch, USDC) at most once an hour. Never fails the job: every feed is optional."""
import json, math, os, re, sys, time, urllib.parse, urllib.request
from datetime import datetime, timezone

NOW = time.time()
UA = {"User-Agent": "AlphaIntelDesk/1.0 (+https://alphainteldesk.com)", "Accept": "application/json"}
OUT, HIST = "warroom.json", "warroom_hist.json"


def get(url, timeout=30, raw=False, tries=2, wait=6):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                b = r.read()
                return b if raw else json.loads(b.decode("utf-8", "replace"))
        except Exception as e:
            err = e
            time.sleep(wait)
    print("  WR feed failed:", url[:90], str(err)[:80])
    return None


def load(p, d):
    try:
        return json.load(open(p))
    except Exception:
        return d


prev = load(OUT, {})
hist = load(HIST, {"v": 1, "obs": {}})
SLOW = NOW - (prev.get("slow_at") or 0) > 55 * 60 or "--all" in sys.argv

# ---------------------------------------------------------------- hotspots
# boxes = (lat_min, lat_max, lon_min, lon_max) watched for military aircraft
# geos = Google Trends countries; terms = words that tie a story / search / market to the hotspot
HOTSPOTS = [
    {"id": "gulf", "name": "Iran & the Gulf", "lat": 27.5, "lon": 54,
     "boxes": [(22, 39, 44, 63)], "geos": ["IR", "AE", "SA", "IL"],
     "gdelt": '(Iran OR Tehran OR Hormuz OR "Persian Gulf" OR IRGC)',
     "terms": "iran iranian tehran hormuz persian gulf irgc khamenei blockade", "choke": ["Strait of Hormuz"]},
    {"id": "levant", "name": "Israel, Gaza & Lebanon", "lat": 32, "lon": 35.2,
     "boxes": [(29, 34.8, 33, 37)], "geos": ["IL", "LB"],
     "gdelt": '(Israel OR Gaza OR Hezbollah OR Lebanon OR "West Bank")',
     "terms": "israel israeli gaza hamas hezbollah lebanon lebanese netanyahu west bank idf", "choke": []},
    {"id": "redsea", "name": "Red Sea & Yemen", "lat": 15, "lon": 43,
     "boxes": [(10, 22, 36, 52)], "geos": ["YE", "SA"],
     "gdelt": '(Houthi OR Houthis OR Yemen OR "Red Sea" OR "Bab el-Mandeb")',
     "terms": "houthi houthis yemen yemeni red sea bab el-mandeb", "choke": ["Bab el-Mandeb Strait", "Suez Canal"]},
    {"id": "ukraine", "name": "Ukraine & Russia", "lat": 49, "lon": 34,
     "boxes": [(44, 57, 22, 45), (53.5, 60, 18, 30)], "geos": ["UA", "RU", "PL"],
     "gdelt": '(Ukraine OR Kyiv OR Kremlin OR Crimea OR Donbas)',
     "terms": "ukraine ukrainian kyiv russia russian kremlin putin zelensky crimea donbas nato", "choke": []},
    {"id": "taiwan", "name": "Taiwan Strait & South China Sea", "lat": 22, "lon": 119,
     "boxes": [(5, 28, 105, 125)], "geos": ["TW", "PH", "JP"],
     "gdelt": '(Taiwan OR "South China Sea" OR "Taiwan Strait" OR PLA)',
     "terms": "taiwan taiwanese south china sea pla beijing china invade", "choke": []},
    {"id": "korea", "name": "Korean Peninsula", "lat": 38.5, "lon": 127.5,
     "boxes": [(33, 43, 124, 132)], "geos": ["KR", "JP"],
     "gdelt": '("North Korea" OR Pyongyang OR "Kim Jong Un")',
     "terms": "north korea pyongyang kim jong", "choke": []},
    {"id": "southasia", "name": "India & Pakistan", "lat": 31, "lon": 72,
     "boxes": [(23, 37, 66, 80)], "geos": ["IN", "PK"],
     "gdelt": '(Kashmir OR "India Pakistan" OR "Pakistan India" OR "Line of Control")',
     "terms": "kashmir pakistan india pakistani line of control", "choke": []},
    {"id": "caribbean", "name": "Venezuela & the Caribbean", "lat": 12, "lon": -68,
     "boxes": [(5, 27, -85, -58)], "geos": ["VE", "CO"],
     "gdelt": '(Venezuela OR Maduro OR Caracas OR Cuba)',
     "terms": "venezuela venezuelan maduro caracas cuba cuban", "choke": ["Panama Canal"]},
]
GDELT_CONFLICT = "(military OR strike OR missile OR attack OR troops OR drone OR warship OR invasion OR airstrike OR ceasefire)"
# conflict words in the languages of the watched countries (Trends titles come in local scripts)
CONFLICT_WORDS = [
    "war", "attack", "missile", "strike", "airstrike", "drone", "bomb", "explosion", "army", "military", "troops",
    "invasion", "ceasefire", "sirens", "rocket", "nuclear", "navy", "warship", "mine", "killed", "shelling", "evacuation",
    "מלחמה", "טיל", "טילים", "אזעקה", "צבע אדום", "פיגוע", "תקיפה", "צה\"ל", "חיזבאללה", "חמאס",          # Hebrew
    "حرب", "صاروخ", "صواريخ", "غارة", "قصف", "هجوم", "انفجار", "مسيرة", "الحوثي", "جيش",                  # Arabic
    "جنگ", "موشک", "حمله", "انفجار", "پهپاد", "مین", "سپاه", "آژیر",                                      # Persian
    "война", "войны", "ракета", "ракеты", "обстрел", "атака", "дрон", "взрыв", "тревога", "мобилизация",   # Russian
    "війна", "ракета", "обстріл", "атака", "дрон", "вибух", "тривога", "загиблий", "мобілізація",          # Ukrainian
    "戰爭", "飛彈", "导弹", "解放軍", "解放军", "軍演", "军演", "共軍", "空襲",                               # Chinese
    "전쟁", "미사일", "북한", "도발", "공습",                                                                 # Korean
    "ミサイル", "戦争", "北朝鮮", "空襲",                                                                     # Japanese
    "जंग", "युद्ध", "मिसाइल", "हमला", "ड्रोन", "سرحد",                                                          # Hindi / Urdu
    "guerra", "ataque", "misil", "bombardeo", "militar", "ejército", "invasión",                           # Spanish
    "wojna", "atak", "rakieta", "dron",                                                                    # Polish
]
NOTABLE = {  # aircraft types that matter to analysts (weight 3), ICAO type codes
    "K35R": "tanker", "K35E": "tanker", "KC10": "tanker", "KC46": "tanker", "K46": "tanker", "A332": "tanker", "MRTT": "tanker",
    "R135": "spy plane", "E3TF": "AWACS", "E3CF": "AWACS", "E737": "AWACS", "E6": "command plane", "E4": "command plane",
    "P8": "sub hunter", "Q4": "drone", "RQ4": "drone", "MQ9": "drone", "Q9": "drone", "U2": "spy plane",
    "B52": "bomber", "B1": "bomber", "B2": "bomber", "C17": "airlifter", "C5M": "airlifter", "A400": "airlifter",
}


def matches(text, terms):
    low = " " + (text or "").lower() + " "
    return any(re.search(r"(?<![a-z])" + re.escape(w) + r"(?![a-z])", low) for w in terms.split())


def is_conflict(text):
    low = (text or "").lower()
    return any((w in low) if not w.isascii() else re.search(r"(?<![a-z])" + re.escape(w) + r"(?![a-z])", low) for w in CONFLICT_WORDS)


def remember(key, value, keep_days=35):
    s = hist["obs"].setdefault(key, [])
    s.append([round(NOW), value])
    hist["obs"][key] = [x for x in s if NOW - x[0] < keep_days * 86400][-1500:]


def normal(key, min_points=12):
    """Median of the stored readings older than 2 h (the 'normal' level). None until there's enough history."""
    xs = sorted(v for t, v in hist["obs"].get(key, []) if NOW - t > 7200)
    if len(xs) < min_points:
        return None
    return xs[len(xs) // 2]


def unusual(cur, base, floor=1.0):
    """0..1: how far above normal. 1x -> 0, 3x -> 1 (log scale). floor keeps tiny baselines from exploding."""
    if base is None:
        return None
    r = (cur + floor) / (base + floor)
    return max(0.0, min(1.0, math.log2(r) / math.log2(3))) if r > 1 else 0.0


# ---------------------------------------------------------------- 1. military flights (every run, ~1 s)
ac, seen = [], set()
for u in ("https://api.adsb.lol/v2/mil", "https://opendata.adsb.fi/api/v2/mil"):
    d = get(u, 25, tries=1)
    for a in (d or {}).get("ac") or []:
        if a.get("lat") is None or a.get("hex") in seen:
            continue
        seen.add(a.get("hex")); ac.append(a)
print("WR flights:", len(ac), "military aircraft with a position")
flights = {}
for h in HOTSPOTS:
    near = [a for a in ac if any(b[0] <= a["lat"] <= b[1] and b[2] <= a["lon"] <= b[3] for b in h["boxes"])]
    note = [(NOTABLE[a.get("t")], a.get("t")) for a in near if a.get("t") in NOTABLE]
    w = len(near) + 2 * len(note)
    kinds = {}
    for k, _ in note:
        kinds[k] = kinds.get(k, 0) + 1
    flights[h["id"]] = {"n": len(near), "notable": kinds, "w": w}

# ---------------------------------------------------------------- 2. news surge (GDELT, hourly)
news = prev.get("news_raw") or {}
if SLOW:
    for h in HOTSPOTS:
        q = h["gdelt"] + " " + GDELT_CONFLICT + " sourcelang:english"
        d = get("https://api.gdeltproject.org/api/v2/doc/doc?" + urllib.parse.urlencode(
            {"query": q, "mode": "timelinevolraw", "format": "json", "timespan": "30d"}), 45, tries=2, wait=7)
        time.sleep(5.5)                                   # GDELT asks for one request every 5 s
        try:
            pts = [p["value"] for p in d["timeline"][0]["data"]]
        except Exception:
            continue
        if len(pts) < 8:
            continue
        # last full day + today so far (scaled to a full day) vs the 4 weeks before
        frac = max(0.25, (NOW % 86400) / 86400)
        last = max(pts[-2], pts[-1] / frac)
        base = sorted(pts[:-2])[len(pts[:-2]) // 2]
        news[h["id"]] = {"day": round(last), "normal": base, "series": pts[-14:]}
    print("WR news:", {k: (v["day"], v["normal"]) for k, v in news.items()})

# ---------------------------------------------------------------- 3. Google Trends (hourly)
trends = prev.get("trends_raw") or {}
if SLOW:
    import xml.etree.ElementTree as ET
    geos = sorted({g for h in HOTSPOTS for g in h["geos"]} | {"US", "GB"})
    per = {}
    for g in geos:
        b = get("https://trends.google.com/trending/rss?geo=" + g, 20, raw=True, tries=1)
        if not b:
            continue
        try:
            root = ET.fromstring(b)
        except Exception:
            continue
        items = []
        for it in root.iter("item"):
            t = (it.findtext("title") or "").strip()
            news_t = " ".join((n.text or "") for n in it.iter() if n.tag.endswith("news_item_title"))
            items.append((t, news_t))
        per[g] = items
        time.sleep(0.4)
    trends = {}
    for h in HOTSPOTS:
        hits = []
        for g in h["geos"]:
            for t, nt in per.get(g, []):
                if is_conflict(t) or (is_conflict(nt) and matches(nt, h["terms"])):
                    hits.append({"geo": g, "q": t})
        for g in ("US", "GB"):                           # the world's biggest audiences searching about the region
            for t, nt in per.get(g, []):
                if matches(t + " " + nt, h["terms"]) and is_conflict(t + " " + nt):
                    hits.append({"geo": g, "q": t})
        trends[h["id"]] = hits[:6]
    print("WR trends:", {k: len(v) for k, v in trends.items()})

# ---------------------------------------------------------------- 4. Conflict Radar headlines (every run)
radar_items = (load("desk.json", {}) or {}).get("conflict") or []
radar = {h["id"]: [c for c in radar_items if matches(c.get("title"), h["terms"])] for h in HOTSPOTS}

# ---------------------------------------------------------------- 5. markets (every run)
movers = (load("movers.json", {}) or {}).get("movers") or []
alpha = (load("alpha_live.json", {}) or {}).get("markets") or []
matches_ = (load("matches.json", {}) or {}).get("matches") or []
ahist = load("alpha_hist.json", [])


def alpha_prices(m):
    out = {}
    for o in m.get("options") or []:
        p = o.get("yesProb")
        if isinstance(p, (int, float)):
            out[o.get("title") or "Yes"] = round(p / 10000, 1)
    return out


def alpha_move(mid):
    """Biggest 24 h move (cents) across a market's options, from alpha_hist.json snapshots."""
    if not isinstance(ahist, list) or not ahist:
        return 0, None
    old = min(ahist, key=lambda s: abs(NOW - 86400 - s.get("t", 0)))
    new = ahist[-1]
    a, b = (old.get("p") or {}).get(mid) or {}, (new.get("p") or {}).get(mid) or {}
    best, lab = 0, None
    for k, v in b.items():
        if k in a and isinstance(v, (int, float)) and isinstance(a[k], (int, float)) and abs(v - a[k]) > abs(best):
            best, lab = v - a[k], k
    return round(best, 1), lab


mk = {}
for h in HOTSPOTS:
    rows = []
    for m in alpha:
        if m.get("hidden") or not matches(m.get("title"), h["terms"]):
            continue
        mv, lab = alpha_move(m.get("id"))
        pr = alpha_prices(m)
        rows.append({"site": "alpha", "title": m["title"], "vol": round(m.get("volume") or 0),
                     "url": "https://www.alphaarcade.com/market/" + (m.get("slug") or ""),
                     "price": (list(pr.values())[0] if len(pr) == 1 else None), "move": mv, "move_opt": lab})
    rows.sort(key=lambda r: -r["vol"])
    other = []
    for x in movers:
        if matches(x.get("title"), h["terms"]) and x.get("site") in ("polymarket", "kalshi"):
            other.append({"site": x["site"], "title": x["title"] + ("" if x.get("outcome") in (None, "Yes") else " · " + x["outcome"]),
                          "price": x.get("price"), "move": round(x.get("change") or 0, 1), "url": x.get("url"), "vol": x.get("vol24") or 0})
    other.sort(key=lambda r: -abs(r["move"]))
    allm = rows + other
    big = max(allm, key=lambda r: abs(r.get("move") or 0), default=None)
    mk[h["id"]] = {"alpha": rows[:4], "other": other[:3], "big": big if big and abs(big.get("move") or 0) >= 3 else None}

# ---------------------------------------------------------------- 6. chokepoints (IMF PortWatch, hourly)
choke = prev.get("chokepoints") or {}
if SLOW:
    base = "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/Daily_Chokepoints_Data/FeatureServer/0/query?"
    for nm in ("Strait of Hormuz", "Bab el-Mandeb Strait", "Suez Canal", "Panama Canal"):
        d = get(base + urllib.parse.urlencode({"where": "portname='%s'" % nm, "outFields": "date,n_total,n_tanker",
                                               "orderByFields": "date DESC", "resultRecordCount": 120, "f": "json"}), 60)
        try:
            rows = sorted(({"d": time.strftime("%Y-%m-%d", time.gmtime(f["attributes"]["date"] / 1000)),
                            "n": f["attributes"]["n_total"], "tk": f["attributes"].get("n_tanker")} for f in d["features"]),
                          key=lambda r: r["d"])
        except Exception:
            continue
        if not rows:
            continue
        ma7 = [round(sum(r["n"] for r in rows[max(0, i - 6):i + 1]) / len(rows[max(0, i - 6):i + 1]), 1) for i in range(len(rows))]
        n30 = sorted(r["n"] for r in rows[-37:-7]) or [rows[-1]["n"]]
        n90 = sorted(r["n"] for r in rows[-97:-7]) or n30
        choke[nm] = {"latest": rows[-1]["d"], "day": rows[-1]["n"], "ma7": ma7[-1], "normal30": n30[len(n30) // 2],
                     "normal90": n90[len(n90) // 2], "series": [[r["d"], r["n"], m] for r, m in zip(rows[-60:], ma7[-60:])]}
    print("WR chokepoints:", {k: (v["latest"], v["ma7"]) for k, v in choke.items()})

# Alpha's Hormuz market: settles on the PortWatch 7-day average reaching the target
hormuz_mkts = []
for m in alpha:
    if "hormuz" in m["title"].lower() and not m.get("hidden"):
        tgt = re.search(r"equal to or above (\d+)", m.get("rules") or "")
        hormuz_mkts.append({"title": m["title"], "url": "https://www.alphaarcade.com/market/" + m["slug"], "vol": round(m.get("volume") or 0),
                            "target": int(tgt.group(1)) if tgt else None, "options": alpha_prices(m)})
hormuz_mkts.sort(key=lambda r: -r["vol"])

# ---------------------------------------------------------------- 7. USDC on Algorand (hourly)
usdc = prev.get("usdc") or {}
if SLOW:
    um = next((m for m in alpha if "USDC" in m["title"] and "Algorand" in m["title"] and not m.get("hidden")), None)
    excl = sorted(set(re.findall(r"\b[A-Z2-7]{58}\b", (um or {}).get("rules") or "")))
    idx = "https://mainnet-idx.algonode.cloud/v2"
    a = get(idx + "/assets/31566704", 20)
    try:
        total = a["asset"]["params"]["total"]
        reserve = a["asset"]["params"]["reserve"]
        if reserve not in excl:
            excl.append(reserve)
        held = 0
        for ad in excl:
            r = get(idx + "/accounts/%s/assets?asset-id=31566704" % ad, 20) or {}
            held += sum(x.get("amount", 0) for x in r.get("assets") or [] if x.get("asset-id") == 31566704)
        supply = (total - held) / 1e6
        s = usdc.get("series") or []
        if not s or s[-1][0] != time.strftime("%Y-%m-%d"):
            s.append([time.strftime("%Y-%m-%d"), round(supply)])
        else:
            s[-1][1] = round(supply)
        usdc = {"supply": round(supply), "target": 200_000_000, "excluded": len(excl), "series": s[-120:],
                "market": {"title": um["title"], "url": "https://www.alphaarcade.com/market/" + um["slug"], "options": alpha_prices(um),
                           "vol": round(um.get("volume") or 0)} if um else None}
        print("WR USDC on Algorand: $%.1fM (excluding %d addresses)" % (supply / 1e6, len(excl)))
    except Exception as e:
        print("  WR USDC failed:", str(e)[:80])

# ---------------------------------------------------------------- score
SIG = ("flights", "news", "trends", "radar", "markets", "ships")
cur = {}
for h in HOTSPOTS:
    i = h["id"]
    c = {"flights": flights[i]["w"], "radar": len(radar[i]), "trends": len(trends.get(i) or []),
         "markets": abs((mk[i]["big"] or {}).get("move") or 0)}
    if i in news:
        c["news"] = news[i]["day"]
    drops = [1 - choke[n]["ma7"] / choke[n]["normal90"] for n in h["choke"] if n in choke and choke[n]["normal90"]]
    if drops:
        c["ships"] = round(max(0, max(drops)) * 100)         # % below the 90-day normal
    cur[i] = c
    for k in ("flights", "radar", "trends"):
        remember(i + ":" + k, c[k])

hot = []
maxv = {k: max([cur[i].get(k, 0) for i in cur] + [1]) for k in SIG}
for h in HOTSPOTS:
    i, c = h["id"], cur[h["id"]]
    parts, why, calib = {}, [], []
    for k in SIG:
        if k not in c:
            continue
        level = min(1.0, c[k] / maxv[k]) if maxv[k] else 0          # compared with the other hotspots
        if k == "news":
            u = unusual(news[i]["day"], news[i]["normal"], floor=5)
        elif k == "markets":
            u = max(0.0, min(1.0, (c[k] - 3) / 12))                    # 3c move = 0, 15c+ = 1
        elif k == "ships":
            u = max(0.0, min(1.0, c[k] / 60))                          # traffic 60%+ below normal = 1
        else:
            u = unusual(c[k], normal(i + ":" + k))
            if u is None:
                calib.append(k); u = level * 0.5                       # until we know "normal", lean on the level
        parts[k] = round(100 * (0.5 * level + 0.5 * u))
    score = round(sum(parts.values()) / len(parts)) if parts else 0
    f = flights[i]
    if f["n"]:
        nt = ", ".join("%d %s%s" % (v, k, "s" if v > 1 else "") for k, v in sorted(f["notable"].items(), key=lambda kv: -kv[1]))
        why.append({"k": "flights", "t": "%d military aircraft broadcasting near the region%s" % (f["n"], (" incl. " + nt) if nt else "")})
    if i in news:
        r = (news[i]["day"] + 5) / (news[i]["normal"] + 5)
        why.append({"k": "news", "t": "%s conflict stories in the last day, %s" % (format(news[i]["day"], ","),
                    ("%.1f× normal" % r) if r >= 1.3 else ("about normal" if r > 0.77 else "below normal"))})
    if trends.get(i):
        why.append({"k": "trends", "t": "Trending searches: " + " · ".join("“%s” (%s)" % (t["q"], t["geo"]) for t in trends[i][:3])})
    if radar[i]:
        why.append({"k": "radar", "t": "%d of our latest Conflict Radar headlines: “%s”" % (len(radar[i]), radar[i][0]["title"])})
    if mk[i]["big"]:
        b = mk[i]["big"]
        why.append({"k": "markets", "t": "Market move: “%s” %+.0f¢ in 24 h (%s)" % (b["title"], b["move"],
                    {"alpha": "Alpha Arcade", "polymarket": "Polymarket", "kalshi": "Kalshi"}[b["site"]])})
    for n in h["choke"]:
        if n in choke:
            ch = choke[n]
            why.append({"k": "ships", "t": "%s: %s ships/day (7-day avg) vs %s normal, data through %s" % (
                n, ch["ma7"], ch["normal90"], datetime.strptime(ch["latest"], "%Y-%m-%d").strftime("%b %-d"))})
    lvl = "HOT" if score >= 75 else "ELEVATED" if score >= 50 else "ACTIVE" if score >= 25 else "CALM"
    hot.append({"id": i, "name": h["name"], "lat": h["lat"], "lon": h["lon"], "score": score, "level": lvl, "parts": parts,
                "why": why, "calibrating": calib, "markets": mk[i], "flights": f, "news": news.get(i), "trends": trends.get(i) or [],
                "radar": radar[i][:3]})
hot.sort(key=lambda x: -x["score"])

out = {"updated": datetime.fromtimestamp(NOW, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
       "slow_at": NOW if SLOW else prev.get("slow_at"),
       "hotspots": hot, "chokepoints": choke, "hormuz_markets": hormuz_mkts, "usdc": usdc,
       "news_raw": news, "trends_raw": trends, "aircraft": len(ac),
       "sources": "Military aircraft: adsb.lol + adsb.fi (open data, ODbL) · News: GDELT Project · Searches: Google Trends · "
                  "Shipping: IMF PortWatch · USDC: Algorand blockchain · Markets: Alpha Arcade, Polymarket, Kalshi"}
json.dump(out, open(OUT, "w"), ensure_ascii=False, separators=(",", ":"))
json.dump(hist, open(HIST, "w"), separators=(",", ":"))
print("WR heat:", [(x["id"], x["score"], x["level"]) for x in hot])
