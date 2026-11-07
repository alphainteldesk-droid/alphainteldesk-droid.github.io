# Alpha Intel Desk: builds desk.json for the "Live Intel Desk" screens on the homepage banner.
# Markets (delayed quotes), oil, DXY, 10-year, VIX, crypto, Google Trends (US + UK)
# and Conflict Radar (world conflict headlines from Google News, tagged by region).
# Public data only. Runs every hour from the Update markets workflow.
import json, re, urllib.request
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

# ---------- Conflict Radar ----------
CONFLICT_Q = ("(war OR military OR troops OR missile OR airstrike OR drone OR ceasefire OR invasion OR "
              "sanctions OR clashes OR insurgents OR shelling OR \"peace talks\" OR coup OR \"naval drills\" OR blockade) when:1d")
CONFLICT_WORDS = ("war", "military", "troops", "missile", "strike", "drone", "ceasefire", "invasion", "invade",
                  "sanction", "clash", "attack", "shelling", "peace", "coup", "army", "navy", "rebel", "militant",
                  "hostage", "nuclear", "border", "offensive", "bomb", "killed", "forces", "drill", "naval",
                  "warship", "tension", "blockade", "escalat", "retaliat", "occupation")
NOT_CONFLICT = ("nfl", "nba", "mlb", "nhl", "game", "season", "coach", "box office", "movie", "trailer",
                "video game", "star wars", "price war", "culture war", "bidding war", "recipe", "stock",
                "holy war", "rivalry", "podcast", "lifestyle", "fashion", "album", "byu", "playoff", "tournament")
REGIONS = [  # first match wins
    ("MDE", "israel gaza hamas hezbollah lebanon iran iraq syria yemen houthi saudi qatar jordan red sea "
            "west bank tehran tel aviv iranian israeli palestinian lebanese syrian yemeni iraqi saudi"),
    ("EUR", "ukraine russia kremlin kyiv moscow putin zelensky nato poland belarus moldova serbia kosovo "
            "baltic europe eu ukrainian russian polish belarusian serbian european"),
    ("ASIA", "china taiwan beijing korea pyongyang japan india pakistan kashmir afghanistan myanmar "
             "philippines south china sea thailand cambodia chinese taiwanese korean japanese indian pakistani afghan"),
    ("AFR", "sudan congo somalia ethiopia nigeria sahel mali niger libya burkina kenya chad sudanese somali "
            "ethiopian nigerian congolese libyan"),
    ("AMER", "venezuela cuba mexico cartel haiti colombia ecuador brazil panama canada pentagon "
             "venezuelan cuban mexican haitian colombian united states u.s. us "),
]


def conflict(n=12):
    url = ("https://news.google.com/rss/search?q=" + urllib.request.quote(CONFLICT_Q) +
           "&hl=en-US&gl=US&ceid=US:en")
    root = ET.fromstring(get(url, raw=True))
    out, seen = [], []
    for i in root.iter("item"):
        full = (i.findtext("title") or "").strip()
        title, _, source = full.rpartition(" - ")
        title = title or full
        low = " " + title.lower() + " "
        if not any(w in low for w in CONFLICT_WORDS) or any(w in low for w in NOT_CONFLICT):
            continue
        ws = set(re.findall(r"[a-z]{4,}", low))          # same story, different headline? skip it
        if any(len(ws & k) >= 0.5 * min(len(ws), len(k)) for k in seen):
            continue
        seen.append(ws)
        region = next((r for r, words in REGIONS if any(re.search(r"\b" + re.escape(w) + r"(?:\b|['\u2019]s)", low)
                                                         for w in words.split())), "WORLD")
        out.append({"region": region, "title": title, "source": source.strip(),
                    "url": (i.findtext("link") or "").strip(), "time": (i.findtext("pubDate") or "").strip()})
        if len(out) >= n:
            break
    return out


out = {"updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "quotes": {}}
for name, sym in QUOTES:
    q = quote(sym)
    if q:
        out["quotes"][name] = q
for key, fn in (("crypto", crypto), ("trends_us", lambda: trends("US", 5)), ("trends_uk", lambda: trends("GB", 5)),
                ("conflict", conflict)):
    try:
        out[key] = fn()
    except Exception as err:
        print(key, "failed:", err)
        out[key] = {} if key == "crypto" else []
if not out.get("conflict"):                     # keep the last good headlines if Google News fails
    try:
        out["conflict"] = json.load(open("desk.json")).get("conflict", [])
    except Exception:
        out["conflict"] = []

# Interleave US and UK trends: US, UK, US, UK...
out["trends"] = [t for pair in zip(out.pop("trends_us"), out.pop("trends_uk")) for t in pair]

with open("desk.json", "w") as fh:
    json.dump(out, fh, indent=1, ensure_ascii=False)
print("Wrote desk.json:", len(out["quotes"]), "of", len(QUOTES), "quotes |",
      len(out["crypto"]), "crypto |", len(out["trends"]), "trends |", len(out["conflict"]), "conflict headlines")
