# Alpha Intel Desk: builds desk.json for the "Live Intel Desk" screens on the homepage banner.
# Markets (delayed quotes), oil, DXY, 10-year, VIX, crypto, Google Trends (US + UK)
# and Conflict Radar (world conflict headlines from Google News, tagged by region).
# Public data only. Runs every hour from the Update markets workflow.
import json, re, urllib.parse, urllib.request
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
# Paywalled outlets: their links make visitors pay, so the radar only shows free-to-read sources.
PAYWALLED = ("wsj.com", "washingtonpost.com", "nytimes.com", "bloomberg.com", "ft.com", "economist.com",
             "theatlantic.com", "barrons.com", "thetimes.co.uk", "thetimes.com", "telegraph.co.uk", "haaretz.com",
             "newyorker.com", "foreignaffairs.com", "foreignpolicy.com", "businessinsider.com", "theinformation.com",
             "latimes.com", "bostonglobe.com", "wired.com", "spectator.co.uk", "asia.nikkei.com", "scmp.com",
             "japantimes.co.jp", "seekingalpha.com", "marketwatch.com", "thetimes.co.uk", "newstatesman.com",
             "nationalreview.com", "thediplomat.com", "stratfor.com", "janes.com")
PAYWALLED_NAMES = ("wsj", "wall street journal", "washington post", "new york times", "nytimes", "bloomberg",
                   "financial times", "the economist", "the atlantic", "barron", "the times", "telegraph",
                   "haaretz", "new yorker", "foreign affairs", "foreign policy", "business insider",
                   "the information", "los angeles times", "boston globe", "wired", "the spectator",
                   "nikkei", "south china morning post", "japan times", "seeking alpha", "marketwatch")


def paywalled(domain, name):
    d, nm = (domain or "").lower(), (name or "").lower().strip()
    return any(d == p or d.endswith("." + p) for p in PAYWALLED) or any(nm == p or nm.startswith(p) for p in PAYWALLED_NAMES)


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
    q = CONFLICT_Q + "".join(" -site:" + s for s in ("wsj.com", "washingtonpost.com", "nytimes.com", "bloomberg.com", "ft.com"))
    url = ("https://news.google.com/rss/search?q=" + urllib.request.quote(q) +
           "&hl=en-US&gl=US&ceid=US:en")
    root = ET.fromstring(get(url, raw=True))
    out, seen = [], []
    for i in root.iter("item"):
        full = (i.findtext("title") or "").strip()
        title, _, source = full.rpartition(" - ")
        title = title or full
        src = i.find("source")
        domain = urllib.parse.urlparse(src.get("url") or "").netloc if src is not None else ""
        if src is not None and (src.text or "").strip():
            source = src.text
        if paywalled(domain, source):
            continue                                     # skip paywalled outlets: links must be free to read
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


# LATEST news line (Nov 10): several free-to-read sources merged, newest first, market-relevant only.
NEWS_FEEDS = [
    ("BBC", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("BBC", "https://feeds.bbci.co.uk/news/world/us_and_canada/rss.xml"),
    ("BBC", "https://feeds.bbci.co.uk/news/business/rss.xml"),
    ("CNBC", "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
    ("CNBC", "https://www.cnbc.com/id/10000664/device/rss/rss.html"),
    ("CNBC", "https://www.cnbc.com/id/10000113/device/rss/rss.html"),
    ("The Hill", "https://thehill.com/news/feed/"),
    ("NPR", "https://feeds.npr.org/1001/rss.xml"),
    ("NPR", "https://feeds.npr.org/1014/rss.xml"),
]
NEWS_SKIP = ("/pro/", "investingclub", "/select/", "/video/", "/sounds/", "/iplayer/", "/live/")
# Only headlines about things prediction markets trade on (politics, economy, markets, crypto, conflict, big tech)
NEWS_RELEVANT = re.compile(r"\b(" + "|".join([
    "trump", "biden", "vance", "harris", "newsom", "congress", "senate", "senator", "house", "speaker", "election",
    "vote", "voters", "ballot", "poll", "impeach\\w*", "supreme court", "court", "judge", "ruling", "white house",
    "pentagon", "hegseth", "rubio", "governor", "mayor", "shutdown", "budget", "bill", "law", "tariffs?", "trade",
    "fed", "federal reserve", "powell", "rates?", "inflation", "cpi", "jobs", "unemployment", "economy", "gdp",
    "recession", "stocks?", "markets?", "dow", "s&p", "nasdaq", "shares", "earnings", "ipo", "bonds?", "treasury",
    "dollar", "oil", "opec", "gold", "bitcoin", "crypto\\w*", "ethereum", "bank", "banks", "layoffs", "merger",
    "ai", "openai", "anthropic", "nvidia", "apple", "tesla", "musk", "google", "microsoft", "amazon", "meta",
    "war", "strikes?", "missiles?", "drone", "ceasefire", "troops", "military", "nato", "sanctions", "nuclear",
    "iran", "israel", "gaza", "hamas", "hezbollah", "ukraine", "russia", "putin", "zelensky", "china", "xi",
    "taiwan", "north korea", "venezuela", "cuba", "mexico", "india", "pakistan", "saudi", "hormuz", "oman"]) + r")\b", re.I)


def news(n=15, per_source=6):
    """Market-relevant headlines (free to read) for the LATEST line under the ticker. Newest first, last 24h."""
    from email.utils import parsedate_to_datetime
    items, seen = [], set()
    for src, url in NEWS_FEEDS:
        try:
            root = ET.fromstring(get(url, raw=True))
        except Exception as err:
            print("News feed failed:", url, err)
            continue
        for i in root.iter("item"):
            title = (i.findtext("title") or "").strip()
            link = (i.findtext("link") or "").strip()
            try:
                when = parsedate_to_datetime(i.findtext("pubDate") or "")
            except Exception:
                continue
            key = title.lower()
            if not title or key in seen or any(x in link for x in NEWS_SKIP) or not NEWS_RELEVANT.search(title):
                continue
            if (datetime.now(timezone.utc) - when).total_seconds() > 86400:
                continue
            seen.add(key)
            items.append({"title": title, "url": link.split("?")[0], "src": src,
                          "time": when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
    items.sort(key=lambda x: x["time"], reverse=True)
    out, count = [], {}
    for x in items:                                  # no single source takes over the line
        if count.get(x["src"], 0) < per_source:
            out.append(x)
            count[x["src"]] = count.get(x["src"], 0) + 1
    print("News:", {s: c for s, c in count.items()}, "kept of", len(items), "relevant")
    return out[:n]


out = {"updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "quotes": {}}
for name, sym in QUOTES:
    q = quote(sym)
    if q:
        out["quotes"][name] = q
for key, fn in (("crypto", crypto), ("trends_us", lambda: trends("US", 5)), ("trends_uk", lambda: trends("GB", 5)),
                ("conflict", conflict), ("news", news)):
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

for key in ("news",):           # keep the last good headlines if the feeds fail
    if not out.get(key):
        try:
            out[key] = json.load(open("desk.json")).get(key, [])
        except Exception:
            out[key] = []

# Interleave US and UK trends: US, UK, US, UK...
out["trends"] = [t for pair in zip(out.pop("trends_us"), out.pop("trends_uk")) for t in pair]

with open("desk.json", "w") as fh:
    json.dump(out, fh, indent=1, ensure_ascii=False)
print("Wrote desk.json:", len(out["quotes"]), "of", len(QUOTES), "quotes |",
      len(out["crypto"]), "crypto |", len(out["trends"]), "trends |", len(out["conflict"]), "conflict headlines |", len(out.get("news", [])), "news headlines")
