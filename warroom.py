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
     "terms": "iran, iranian, tehran, hormuz, persian gulf, irgc, khamenei, iranian blockade", "choke": ["Strait of Hormuz"]},
    {"id": "levant", "name": "Israel, Gaza & Lebanon", "lat": 32, "lon": 35.2,
     "boxes": [(29, 34.8, 33, 37)], "geos": ["IL", "LB"],
     "gdelt": '(Israel OR Gaza OR Hezbollah OR Lebanon OR "West Bank")',
     "terms": "israel, israeli, gaza, hamas, hezbollah, lebanon, lebanese, netanyahu, west bank, idf", "choke": []},
    {"id": "redsea", "name": "Red Sea & Yemen", "lat": 15, "lon": 43,
     "boxes": [(10, 22, 36, 52)], "geos": ["YE", "SA"],
     "gdelt": '(Houthi OR Houthis OR Yemen OR "Red Sea" OR "Bab el-Mandeb")',
     "terms": "houthi, houthis, yemen, yemeni, red sea, bab el-mandeb", "choke": ["Bab el-Mandeb Strait", "Suez Canal"]},
    {"id": "ukraine", "name": "Ukraine & Russia", "lat": 49, "lon": 34,
     "boxes": [(44, 57, 22, 45), (53.5, 60, 18, 30)], "geos": ["UA", "RU", "PL"],
     "gdelt": '(Ukraine OR Kyiv OR Kremlin OR Crimea OR Donbas)',
     "terms": "ukraine, ukrainian, kyiv, russia, russian, kremlin, putin, zelensky, crimea, donbas", "choke": []},
    {"id": "taiwan", "name": "Taiwan Strait & South China Sea", "lat": 22, "lon": 119,
     "boxes": [(5, 28, 105, 125)], "geos": ["TW", "PH", "JP"],
     "gdelt": '(Taiwan OR "South China Sea" OR "Taiwan Strait" OR PLA)',
     "terms": "taiwan, taiwanese, south china sea, pla, china invade, invade taiwan", "choke": []},
    {"id": "korea", "name": "Korean Peninsula", "lat": 38.5, "lon": 127.5,
     "boxes": [(33, 43, 124, 132)], "geos": ["KR", "JP"],
     "gdelt": '("North Korea" OR Pyongyang OR "Kim Jong Un")',
     "terms": "north korea, north korean, pyongyang, kim jong", "choke": []},
    {"id": "southasia", "name": "India & Pakistan", "lat": 31, "lon": 72,
     "boxes": [(23, 37, 66, 80)], "geos": ["IN", "PK"],
     "gdelt": '(Kashmir OR "India Pakistan" OR "Pakistan India" OR "Line of Control")',
     "terms": "kashmir, pakistan, pakistani, india pakistan, line of control", "choke": []},
    {"id": "caribbean", "name": "Venezuela & the Caribbean", "lat": 12, "lon": -68,
     "boxes": [(5, 27, -85, -58)], "geos": ["VE", "CO"],
     "gdelt": '(Venezuela OR Maduro OR Caracas OR Cuba)',
     "terms": "venezuela, venezuelan, maduro, caracas, cuba, cuban", "choke": ["Panama Canal"]},
]
GDELT_CONFLICT = ("(military OR strike OR missile OR attack OR troops OR drone OR warship OR invasion OR airstrike OR ceasefire "
                  "OR cyberattack OR \"cyber attack\" OR hackers OR ransomware)")   # Nov 25 (James): cyber incidents count too
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
    # Nov 25 (James): cyber incidents and hacks add to the heat like any other conflict signal
    "cyberattack", "cyberattacks", "cyber attack", "cyber attacks", "cyber-attack", "cyber-attacks", "cyberwar",
    "hacker", "hackers", "hacked", "hacking", "ransomware", "malware", "ddos", "breach", "breached", "cyber", "cyber espionage",
    "סייבר", "האקרים", "سيبراني", "قراصنة", "سایبری", "هکر", "هکرها", "кибератака", "кибератаки", "хакеры",
    "хакер", "кібератака", "хакери", "网络攻击", "網路攻擊", "黑客", "駭客", "해킹", "사이버공격", "サイバー攻撃",
    "ハッカー", "साइबर", "ciberataque", "hackeo", "cyberatak",
]
NOTABLE = {  # aircraft types that matter to analysts (weight 3), ICAO type codes
    "K35R": "tanker", "K35E": "tanker", "KC10": "tanker", "KC46": "tanker", "K46": "tanker", "A332": "tanker", "MRTT": "tanker",
    "R135": "spy plane", "E3TF": "AWACS", "E3CF": "AWACS", "E737": "AWACS", "E6": "command plane", "E4": "command plane",
    "P8": "sub hunter", "Q4": "drone", "RQ4": "drone", "MQ9": "drone", "Q9": "drone", "U2": "spy plane",
    "B52": "bomber", "B1": "bomber", "B2": "bomber", "C17": "airlifter", "C5M": "airlifter", "A400": "airlifter",
}


# Nov 24 (James): the War Room must keep learning. warroom_config.json adds words, filters and hotspots without
# touching this code: {"hotspots": {"gulf": {"add_terms": "...", "exclude": "...", "oil": 1}}, "new_hotspots": [...],
#  "add_conflict_words": [...], "ignore": "words that never count anywhere", "weights": {"news": 1.5}, "floor": {...}}
CFG = load("warroom_config.json", {})
OIL_LINK = {"gulf": 1, "redsea": 1, "levant": 0.6, "ukraine": 0.5, "caribbean": 0.5}   # how much oil prices speak for a region
HOTSPOTS += CFG.get("new_hotspots") or []
for h in HOTSPOTS:
    x = (CFG.get("hotspots") or {}).get(h["id"]) or {}
    if x.get("add_terms"):
        h["terms"] += ", " + x["add_terms"]
    h["exclude"] = x.get("exclude", "")
    h["oil"] = x.get("oil", h.get("oil", OIL_LINK.get(h["id"], 0)))
    h.setdefault("choke", []); h.setdefault("geos", []); h.setdefault("boxes", [])
CONFLICT_WORDS += CFG.get("add_conflict_words") or []
# Nov 24 (James): dots appear wherever signals converge, not only on the 8 watched hotspots. Places outside them
# (lat, lon, words); warroom_config.json "places" adds more. Iran, Israel, Ukraine etc. stay with their hotspots.
PLACES = [
    ("Sudan", 15.5, 32.5, "sudan, sudanese, khartoum, darfur, el fasher, rapid support forces"),
    ("DR Congo", -2, 28, "congo, congolese, kinshasa, goma, m23, drc"),
    ("The Sahel", 15, 0, "mali, bamako, niger, niamey, burkina faso, sahel, jnim"),
    ("Nigeria", 9, 8, "nigeria, nigerian, abuja, boko haram"),
    ("Somalia", 5, 46, "somalia, somali, mogadishu, al-shabaab, puntland"),
    ("Ethiopia & Eritrea", 12, 39, "ethiopia, ethiopian, eritrea, eritrean, tigray, amhara"),
    ("Libya", 27, 17, "libya, libyan, tripoli, benghazi"),
    ("Egypt & Sinai", 28, 31, "egypt, egyptian, cairo, sinai"),
    ("Syria", 35, 38.5, "syria, syrian, damascus, aleppo, idlib"),
    ("Iraq", 33, 43.5, "iraq, iraqi, baghdad, erbil, kurdistan"),
    ("Turkey", 39, 35, "turkey, turkish, ankara, erdogan, pkk"),
    ("Caucasus", 40.5, 45.5, "armenia, armenian, azerbaijan, azerbaijani, karabakh, baku, yerevan, georgia's"),
    ("The Baltics", 57, 24, "estonia, estonian, latvia, latvian, lithuania, lithuanian, baltic, kaliningrad"),
    ("Belarus", 53.5, 28, "belarus, belarusian, minsk, lukashenko"),
    ("Moldova", 47, 28.8, "moldova, moldovan, transnistria"),
    ("The Balkans", 43.5, 20.5, "serbia, serbian, kosovo, bosnia, republika srpska"),
    ("Greenland & the Arctic", 72, -40, "greenland, nuuk, arctic"),
    ("Afghanistan", 34, 66, "afghanistan, afghan, taliban, kabul"),
    ("Myanmar", 21, 96, "myanmar, burma, burmese"),
    ("Philippines", 13, 122, "philippines, philippine, filipino, manila, scarborough shoal, second thomas shoal"),
    ("Japan", 36, 138, "japan, japanese, senkaku, okinawa"),
    ("Thailand & Cambodia", 13.5, 103, "thailand, thai, cambodia, cambodian"),
    ("Haiti", 19, -72.5, "haiti, haitian, port-au-prince"),
    ("Mexico", 23, -102, "mexico, mexican, cartel, cartels, sinaloa, cjng"),
    ("Colombia & Ecuador", 2, -76, "colombia, colombian, ecuador, ecuadorian, farc"),
] + [tuple(x) for x in CFG.get("places") or []]
IGNORE = CFG.get("ignore", "")
WEIGHTS = dict({"flights": 1, "news": 1, "trends": 1, "radar": 1, "markets": 1, "ships": 1, "oil": 1}, **(CFG.get("weights") or {}))


def matches(text, terms):
    """terms = comma-separated words or phrases, matched as whole words."""
    low = " " + (text or "").lower() + " "
    return any(re.search(r"(?<![a-z])" + re.escape(w.strip()) + r"(?![a-z])", low) for w in terms.split(",") if w.strip())


def hit(text, h):
    """Text is about hotspot h: one of its terms, none of its exclude words, nothing on the global ignore list."""
    return matches(text, h["terms"]) and not matches(text, h["exclude"]) and not matches(text, IGNORE)


CJK = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]")


def is_conflict(text):
    """Latin words: whole words. Chinese/Japanese/Korean: substring (no spaces). Other scripts (Hebrew, Arabic,
    Persian, Cyrillic, Devanagari): whole tokens, or a token starting with the word when the word is 4+ letters
    (so Persian "مین" (mine) no longer matches inside the name "امین")."""
    low = (text or "").lower()
    toks = re.findall(r"[^\s\-\u2013\u2014.,:;!?()\"'\u00ab\u00bb]+", low)
    for w in CONFLICT_WORDS:
        if w.isascii():
            if re.search(r"(?<![a-z])" + re.escape(w) + r"(?![a-z])", low):
                return True
        elif CJK.search(w):
            if w in low:
                return True
        elif any(t == w or (len(w) >= 4 and t.startswith(w)) for t in toks):
            return True
    return False


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
# GDELT limits shared servers hard, so each run refreshes ONE hotspot (the stalest); its data is daily anyway.
todo = sorted(HOTSPOTS, key=lambda h: (news.get(h["id"]) or {}).get("at", 0))[:1 if "--all" not in sys.argv else 8]
for h in todo:
    if (news.get(h["id"]) or {}).get("at", 0) > NOW - 40 * 60:
        continue
    q = h["gdelt"] + " " + GDELT_CONFLICT + " sourcelang:english"
    d = get("https://api.gdeltproject.org/api/v2/doc/doc?" + urllib.parse.urlencode(
        {"query": q, "mode": "timelinevolraw", "format": "json", "timespan": "30d"}), 45, tries=2, wait=25)
    try:
        pts = [p["value"] for p in d["timeline"][0]["data"]]
    except Exception:
        continue
    if len(pts) < 8:
        continue
    frac = max(0.25, (NOW % 86400) / 86400)               # last full day, or today so far scaled to a full day
    last = max(pts[-2], pts[-1] / frac)
    base = sorted(pts[:-2])[len(pts[:-2]) // 2]           # median day of the 4 weeks before
    news[h["id"]] = {"day": round(last), "normal": base, "series": pts[-14:], "at": NOW}
    if "--all" in sys.argv:
        time.sleep(12)
news = {k: v for k, v in news.items() if NOW - v.get("at", NOW) < 2 * 86400}     # drop stale readings
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
                if not matches(t, IGNORE) and not matches(t, h["exclude"]) and (is_conflict(t) or (is_conflict(nt) and hit(nt, h))):
                    hits.append({"geo": g, "q": t})
        for g in ("US", "GB"):                           # the world's biggest audiences searching about the region
            for t, nt in per.get(g, []):
                if hit(t + " " + nt, h) and is_conflict(t + " " + nt):
                    hits.append({"geo": g, "q": t})
        trends[h["id"]] = hits[:6]
    print("WR trends:", {k: len(v) for k, v in trends.items()})

# ---------------------------------------------------------------- 4. Conflict Radar headlines (every run)
radar_items = (load("desk.json", {}) or {}).get("conflict") or []
radar = {h["id"]: [c for c in radar_items if hit(c.get("title"), h)] for h in HOTSPOTS}

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
        if m.get("hidden") or not hit(m.get("title"), h):
            continue
        mv, lab = alpha_move(m.get("id"))
        pr = alpha_prices(m)
        rows.append({"site": "alpha", "title": m["title"], "vol": round(m.get("volume") or 0),
                     "url": "https://www.alphaarcade.com/market/" + (m.get("slug") or ""),
                     "price": (list(pr.values())[0] if len(pr) == 1 else None), "move": mv, "move_opt": lab})
    rows.sort(key=lambda r: -r["vol"])
    other = []
    for x in movers:
        if hit(x.get("title"), h) and x.get("site") in ("polymarket", "kalshi"):
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
        d = get(base + urllib.parse.urlencode({"where": "portname='%s'" % nm, "outFields": "date,portid,portname,n_total,n_tanker",
                                               "orderByFields": "date DESC", "resultRecordCount": 100, "f": "json"}), 60)
        if not d or "features" not in d:
            print("  WR PortWatch", nm, str(d)[:200])
            continue
        try:
            day = lambda v: v[:10].replace("/", "-") if isinstance(v, str) else time.strftime("%Y-%m-%d", time.gmtime(v / 1000))
            rows = sorted(({"d": day(f["attributes"]["date"]),
                            "n": f["attributes"]["n_total"], "tk": f["attributes"].get("n_tanker")} for f in d["features"]),
                          key=lambda r: r["d"])
        except Exception as e:
            print("  WR PortWatch parse", nm, e, str(d["features"][:1])[:200])
            continue
        if not rows:
            continue
        ma7 = [round(sum(r["n"] for r in rows[max(0, i - 6):i + 1]) / len(rows[max(0, i - 6):i + 1]), 1) for i in range(len(rows))]
        n30 = sorted(r["n"] for r in rows[-37:-7]) or [rows[-1]["n"]]
        n90 = sorted(r["n"] for r in rows[-97:-7]) or n30
        choke[nm] = {"latest": rows[-1]["d"], "day": rows[-1]["n"], "ma7": ma7[-1], "normal30": n30[len(n30) // 2],
                     "normal90": n90[len(n90) // 2], "series": [[r["d"], r["n"], m] for r, m in zip(rows[-60:], ma7[-60:])]}
    print("WR chokepoints:", {k: (v["latest"], v["ma7"]) for k, v in choke.items()})

# ---------------------------------------------------------------- 6b. live ships (aisstream.io, hourly, needs AISSTREAM_KEY)
# Counts the ships inside each chokepoint box during a ~70 s listen: a live "how busy is it right now" reading,
# days ahead of PortWatch. Coverage depends on shore receivers, so it's compared only with its own history.
LIVE_BOXES = {"Strait of Hormuz": [[25.85, 55.9], [26.95, 57.1]], "Persian Gulf (waiting area)": [[24.0, 48.5], [29.8, 55.8]],
              "Bab el-Mandeb Strait": [[12.35, 43.05], [13.05, 43.65]], "Suez Canal": [[29.85, 32.2], [31.35, 32.65]],
              "Panama Canal": [[8.85, -79.98], [9.42, -79.48]]}
live = prev.get("live_ships") or {}
KEY = os.environ.get("AISSTREAM_KEY")
if SLOW and KEY:
    try:
        import asyncio, websockets

        async def listen(secs=70):
            seen = {k: {} for k in LIVE_BOXES}
            names = list(LIVE_BOXES)
            async with websockets.connect("wss://stream.aisstream.io/v0/stream", open_timeout=20) as ws:
                await ws.send(json.dumps({"APIKey": KEY, "BoundingBoxes": [LIVE_BOXES[n] for n in names],
                                          "FilterMessageTypes": ["PositionReport"]}))
                end = time.time() + secs
                while time.time() < end:
                    try:
                        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=max(1, end - time.time())))
                    except asyncio.TimeoutError:
                        break
                    md = msg.get("MetaData") or {}
                    pr = (msg.get("Message") or {}).get("PositionReport") or {}
                    la, lo = md.get("latitude", pr.get("Latitude")), md.get("longitude", pr.get("Longitude"))
                    if la is None or lo is None:
                        continue
                    for n in names:
                        (a1, o1), (a2, o2) = LIVE_BOXES[n]
                        if a1 <= la <= a2 and o1 <= lo <= o2:
                            seen[n][md.get("MMSI")] = pr.get("Sog") or 0
            return seen

        seen = asyncio.run(listen())
        for n, ships in seen.items():
            moving = sum(1 for v in ships.values() if (v or 0) >= 3)
            remember("ships:" + n, len(ships), keep_days=60)
            live[n] = {"now": len(ships), "moving": moving, "normal": normal("ships:" + n, min_points=24), "at": NOW}
        print("WR live ships:", {k: (v["now"], v["moving"], v["normal"]) for k, v in live.items()})
    except Exception as e:
        print("  WR live ships failed:", str(e)[:120])

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

# ---------------------------------------------------------------- 7. oil, VIX, gold (desk.json quotes, every run)
# Nov 24 (James): money moves before headlines. Oil speaks for the oil regions; VIX (fear) and gold (safe haven) are
# world-wide, so together they make a "fear gauge" that lifts every hotspot already showing activity.
Q = (load("desk.json", {}) or {}).get("quotes") or {}
def qv(k, f="price"):
    return (Q.get(k) or {}).get(f)
clamp = lambda x: max(0.0, min(1.0, x))
oilchg = max([v for v in (qv("brent", "change"), qv("wti", "change")) if v is not None], key=abs, default=None)
macro, fear = {"oil": {"brent": qv("brent"), "wti": qv("wti"), "change": oilchg}}, []
vix, gold = qv("vix"), qv("gold")
if vix:
    nv = normal("g:vix", 12); remember("g:vix", vix)
    p_ = 0.5 * clamp((vix - 15) / 20) + 0.5 * (clamp((vix / nv - 1) / 0.5) if nv else clamp((vix - 15) / 20))   # VIX 15 calm, 35 panic
    macro["vix"] = {"price": vix, "change": qv("vix", "change"), "normal": nv, "part": round(100 * p_)}; fear.append(p_)
if gold:
    ng = normal("g:gold", 12); remember("g:gold", gold)
    p_ = 0.5 * clamp((qv("gold", "change") or 0) / 2.5) + 0.5 * (clamp((gold / ng - 1) / 0.05) if ng else 0)   # +2.5% day / +5% vs normal = 1
    macro["gold"] = {"price": gold, "change": qv("gold", "change"), "normal": ng, "part": round(100 * p_)}; fear.append(p_)
gasj = load("gas.json", {}) or {}
if (gasj.get("rbob") or {}).get("chg5d") is not None:      # gasoline futures up 10¢+ in 5 days = full marks (a fall counts as calm)
    p_ = clamp(gasj["rbob"]["chg5d"] / 10)
    macro["gasoline"] = {"price": gasj["rbob"]["price"], "chg5d": gasj["rbob"]["chg5d"], "part": round(100 * p_)}; fear.append(p_)
stress = sum(fear) / len(fear) if fear else 0
macro["fear"] = round(100 * stress)
print("WR macro:", {k: (v.get("part") if isinstance(v, dict) else v) for k, v in macro.items()}, "oil", oilchg)

# ---------------------------------------------------------------- 8. dates: anniversaries + scheduled events
# Anniversaries live in warroom_config.json ("dates", editable); scheduled events come from our Catalyst Calendar.
TODAY = datetime.fromtimestamp(NOW, timezone.utc).date()
def days_to(md):
    m, d = map(int, md.split("-"))
    best = None
    for y in (TODAY.year - 1, TODAY.year, TODAY.year + 1):
        try:
            k = (datetime(y, m, d).date() - TODAY).days
        except ValueError:
            continue
        if best is None or abs(k) < abs(best):
            best = k
    return best
cats = (load("catalysts.json", {}) or {})
cats = cats.get("events", cats) if isinstance(cats, dict) else cats
dates = {}
for h in HOTSPOTS:
    rows = []
    for x in (CFG.get("dates") or {}).get(h["id"], []):
        k, w = days_to(x["md"]), x.get("window", 3)
        if k is not None and abs(k) <= w:
            rows.append({"kind": "anniversary", "days": k, "what": x["what"], "close": round(1 - abs(k) / (w + 1), 2)})
    for e in cats if isinstance(cats, list) else []:
        try:
            k = (datetime.strptime(str(e.get("date") or e.get("when"))[:10], "%Y-%m-%d").date() - TODAY).days
        except Exception:
            continue
        if 0 <= k <= 7 and hit(" ".join(str(e.get(f) or "") for f in ("title", "name", "what", "note")), h):
            rows.append({"kind": "scheduled", "days": k, "what": e.get("title") or e.get("name"), "close": round(1 - k / 8, 2)})
    for x in CFG.get("black_swans") or []:                 # past shocks tied to this region
        k = days_to(x["md"])
        if x.get("hotspot") == h["id"] and k is not None and abs(k) <= 3:
            rows.append({"kind": "black swan", "days": k, "what": "%s (%s)" % (x["what"], x["year"]), "close": round(1 - abs(k) / 4, 2)})
    rows.sort(key=lambda r: -r["close"])
    dates[h["id"]] = rows
# "This week in history": every past shock within 7 days of today, shown for context (only region-tied ones nudge a score)
this_week = sorted([{"days": days_to(x["md"]), "year": x["year"], "what": x["what"], "hotspot": x.get("hotspot")}
                    for x in CFG.get("black_swans") or [] if days_to(x["md"]) is not None and abs(days_to(x["md"])) <= 7],
                   key=lambda r: r["days"])
print("WR dates:", {k: len(v) for k, v in dates.items() if v})

# ---------------------------------------------------------------- score
SIG = ("flights", "news", "trends", "radar", "markets", "ships", "oil")
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
    if h["oil"] and oilchg is not None:
        c["oil"] = max(0.0, oilchg)                          # oil up today, % (a fall counts as calm)
    cur[i] = c
    for k in ("flights", "radar", "trends"):
        remember(i + ":" + k, c[k])

hot = []
FLOOR = dict({"flights": 12, "news": 300, "trends": 4, "radar": 4, "markets": 15, "ships": 60, "oil": 4}, **(CFG.get("floor") or {}))   # "a lot" for each signal
maxv = {k: max([cur[i].get(k, 0) for i in cur] + [FLOOR[k]]) for k in SIG}
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
        elif k == "oil":
            level, u = clamp(c[k] / FLOOR["oil"]), clamp((c[k] - 1) / 4)  # +1% = 0, +5% = 1
        else:
            u = unusual(c[k], normal(i + ":" + k))
            if u is None:
                calib.append(k); u = level * 0.5                       # until we know "normal", lean on the level
        parts[k] = round(100 * (0.5 * level + 0.5 * u))
    wt = {k: WEIGHTS.get(k, 1) * (h["oil"] if k == "oil" else 1) for k in parts}
    score = round(sum(parts[k] * wt[k] for k in parts) / sum(wt.values())) if parts and sum(wt.values()) else 0
    # dots that amplify, not create: the fear gauge and a key date lift a hotspot that already shows activity
    act = min(1.0, score / 40)
    lift_fear = round(stress * 12 * act)
    dclose = max([r["close"] for r in dates[i]], default=0)
    lift_date = round(dclose * 10 * act)
    score = min(100, score + lift_fear + lift_date)
    f = flights[i]
    if f["n"]:
        nt = ", ".join("%d %s%s" % (v, k, "s" if v > 1 else "") for k, v in sorted(f["notable"].items(), key=lambda kv: -kv[1]))
        why.append({"k": "flights", "t": "%d military aircraft broadcasting near the region%s" % (f["n"], (" incl. " + nt) if nt else ""),
                    "u": "https://globe.adsb.lol/?lat=%s&lon=%s&zoom=5&mil=1" % (h["lat"], h["lon"])})
    if i in news:
        r = (news[i]["day"] + 5) / (news[i]["normal"] + 5)
        why.append({"k": "news", "t": "%s conflict stories in the last day, %s" % (format(news[i]["day"], ","),
                    ("%.1f× normal" % r) if r >= 1.3 else ("about normal" if r > 0.77 else "below normal"))})
    if trends.get(i):
        why.append({"k": "trends", "t": "Trending searches: " + " · ".join("“%s” (%s)" % (t["q"], t["geo"]) for t in trends[i][:3]),
                    "u": "https://trends.google.com/trending?geo=" + trends[i][0]["geo"]})
    if radar[i]:
        why.append({"k": "radar", "t": "%d of our latest Conflict Radar headlines: “%s”" % (len(radar[i]), radar[i][0]["title"]), "u": radar[i][0].get("url")})
    if mk[i]["big"]:
        b = mk[i]["big"]
        why.append({"k": "markets", "t": "Market move: “%s” %+.0f¢ in 24 h (%s)" % (b["title"], b["move"],
                    {"alpha": "Alpha Arcade", "polymarket": "Polymarket", "kalshi": "Kalshi"}[b["site"]]), "u": b.get("url")})
    for n in h["choke"]:
        lv = live.get(n)
        if lv and lv.get("normal") is not None:
            why.append({"k": "ships", "t": "Live: %d ships in the %s right now (normally ~%d)" % (lv["now"], n, lv["normal"])})
        if n in choke:
            ch = choke[n]
            why.append({"k": "ships", "t": "%s: %s ships/day (7-day avg) vs %s normal, data through %s" % (
                n, ch["ma7"], ch["normal90"], datetime.strptime(ch["latest"], "%Y-%m-%d").strftime("%b %-d")), "u": "https://portwatch.imf.org/"})
    if "oil" in c:
        why.append({"k": "oil", "t": "Oil %+.1f%% today (Brent $%s)" % (oilchg, qv("brent"))})
    if lift_fear:
        why.append({"k": "fear", "t": "Fear gauge %d/100 (VIX %s, gold %+.1f%%): +%d" % (macro["fear"], vix, qv("gold", "change") or 0, lift_fear)})
    for r in dates[i][:2]:
        when = "today" if r["days"] == 0 else ("in %d day%s" % (r["days"], "s" * (r["days"] != 1)) if r["days"] > 0 else "%d day%s ago" % (-r["days"], "s" * (r["days"] != -1)))
        why.append({"k": "date", "t": {"anniversary": "Anniversary: ", "scheduled": "Scheduled: ", "black swan": "Black swan on this date: "}[r["kind"]] + "%s, %s" % (r["what"], when)})
    lvl = "HOT" if score >= 75 else "ELEVATED" if score >= 50 else "ACTIVE" if score >= 25 else "CALM"
    hot.append({"id": i, "name": h["name"], "lat": h["lat"], "lon": h["lon"], "score": score, "level": lvl, "parts": parts,
                "why": why, "calibrating": calib, "markets": mk[i], "flights": f, "news": news.get(i), "trends": trends.get(i) or [],
                "radar": radar[i][:3], "dates": dates[i], "lift": {"fear": lift_fear, "date": lift_date}})
hot.sort(key=lambda x: -x["score"])

# ---------------------------------------------------------------- 9. emerging dots: signals converging outside the hotspots
def in_hotspot(lat, lon):
    return any(b[0] <= lat <= b[1] and b[2] <= lon <= b[3] for h in HOTSPOTS for b in h["boxes"])
cells = {}
for a in ac:                                            # military aircraft in 5° squares outside the hotspots
    if not in_hotspot(a["lat"], a["lon"]):
        k = (int(a["lat"] // 5), int(a["lon"] // 5))
        cells[k] = cells.get(k, 0) + 1 + 2 * (a.get("t") in NOTABLE)
air = {}
for (cy, cx), v in cells.items():
    key = "cell:%d:%d" % (cy, cx)
    u = unusual(v, normal(key), floor=2)
    remember(key, v)
    if u and v >= 4:
        lat, lon = cy * 5 + 2.5, cx * 5 + 2.5
        near = min(PLACES, key=lambda p: (p[1] - lat) ** 2 + (p[2] - lon) ** 2)
        if (near[1] - lat) ** 2 + (near[2] - lon) ** 2 <= 100:
            air[near[0]] = max(air.get(near[0], 0), u)
em_trends = prev.get("em_trends") or {}
if SLOW and "per" in dir():
    em_trends = {}
    for p_ in PLACES:
        em_trends[p_[0]] = [{"geo": g, "q": t} for g in ("US", "GB") for t, nt in per.get(g, [])
                            if matches(t + " " + nt, p_[3]) and is_conflict(t + " " + nt)][:3]
emerging = []
for name, lat, lon, terms in PLACES:
    if matches(name, IGNORE):
        continue
    rad = [c for c in radar_items if matches(c.get("title"), terms) and not matches(c.get("title"), IGNORE)]
    mks = [x for x in movers if matches(x.get("title"), terms) and abs(x.get("change") or 0) >= 5 and x.get("site") in ("polymarket", "kalshi")]
    mks += [{"site": "alpha", "title": m["title"], "change": alpha_move(m.get("id"))[0] or 0, "url": "https://www.alphaarcade.com/market/" + (m.get("slug") or "")}
            for m in alpha if not m.get("hidden") and matches(m.get("title"), terms)]
    mks = [x for x in mks if abs(x.get("change") or 0) >= 5] + [x for x in mks if abs(x.get("change") or 0) < 5 and x.get("site") == "alpha"]
    tr = em_trends.get(name) or []
    parts = {"radar": min(1, len(rad) / 3), "markets": min(1, max([abs(x.get("change") or 0) for x in mks] + [0]) / 15),
             "trends": min(1, len(tr) / 2), "flights": air.get(name, 0)}
    kinds = [k for k, v in parts.items() if v > 0]
    score = round(100 * sum(parts.values()) / 2.5)
    if len(kinds) < 2 or score < 20:                     # a dot needs at least two independent signals agreeing
        continue
    why = []
    if rad:
        why.append({"k": "radar", "t": "%d Conflict Radar headline%s: “%s”" % (len(rad), "s" * (len(rad) > 1), rad[0]["title"]), "u": rad[0].get("url")})
    if air.get(name):
        why.append({"k": "flights", "t": "Unusual military air activity nearby", "u": "https://globe.adsb.lol/?lat=%s&lon=%s&zoom=5&mil=1" % (lat, lon)})
    if tr:
        why.append({"k": "trends", "t": "Trending searches: " + " · ".join("“%s” (%s)" % (t["q"], t["geo"]) for t in tr), "u": "https://trends.google.com/trending?geo=" + tr[0]["geo"]})
    big = max(mks, key=lambda x: abs(x.get("change") or 0), default=None)
    if big and abs(big.get("change") or 0) >= 5:
        why.append({"k": "markets", "t": "Market move: “%s” %+.0f¢" % (big["title"], big["change"]), "u": big.get("url")})
    emerging.append({"id": "em-" + re.sub(r"\W+", "-", name.lower()), "name": name, "lat": lat, "lon": lon, "score": min(100, score),
                     "level": "EMERGING", "parts": {k: round(100 * v) for k, v in parts.items()}, "why": why,
                     "markets": [{"site": x["site"], "title": x["title"], "url": x.get("url"), "move": round(x.get("change") or 0, 1)} for x in mks[:5]]})
    remember("em:" + name, score)
emerging.sort(key=lambda x: -x["score"])
print("WR emerging:", [(x["name"], x["score"]) for x in emerging])

out = {"updated": datetime.fromtimestamp(NOW, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
       "slow_at": NOW if SLOW else prev.get("slow_at"),
       "hotspots": hot, "chokepoints": choke, "live_ships": live, "hormuz_markets": hormuz_mkts, "usdc": usdc, "macro": macro, "this_week": this_week, "emerging": emerging, "em_trends": em_trends,
       "news_raw": news, "trends_raw": trends, "aircraft": len(ac),
       "sources": "Military aircraft: adsb.lol + adsb.fi (open data, ODbL) · News: GDELT Project · Searches: Google Trends · "
                  "Shipping: IMF PortWatch · Oil, VIX, gold, gasoline futures: Yahoo Finance (delayed) · USDC: Algorand blockchain · Markets: Alpha Arcade, Polymarket, Kalshi"}
json.dump(out, open(OUT, "w"), ensure_ascii=False, separators=(",", ":"))
json.dump(hist, open(HIST, "w"), separators=(",", ":"))
print("WR heat:", [(x["id"], x["score"], x["level"]) for x in hot])
