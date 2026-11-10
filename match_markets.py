# Alpha Intel Desk: cross-site matching engine (v1).
# For every open Alpha Arcade market (any end date), find the same event on
# Polymarket and Kalshi, line up the outcomes, and score how sure we are they're the same market.
#   SAME (90+)     same event, same outcome, end times line up  -> used for Gap Scanner math
#   SIMILAR (70-89) probably the same event, something differs   -> shown with a badge, never gap math
#   below 70        hidden
# v6: deadlines read from the label first (Kalshi expiration can be weeks later); empty Polymarket books
#     ignored; Movers skip price-bracket ladders and word-mention markets, rank by move x volume.
# v5: dates written differently line up (December 31 = Before Jan 1, 2027); return = returns.
# v4: also writes movers.json (biggest 24h price moves with real volume) and keeps alpha_hist.json.
# v3: lines up 'Yes' markets with the matching deadline inside multi-deadline events.
# v2: also pairs Polymarket with Kalshi directly (non-sports), so Kalshi shows even when Alpha has no market.
# v7: calendar_links() finds each site's own market for Catalyst Calendar events (cal_links.json).
# Writes matches.json. Public market data only.
import json, re, time, unicodedata, urllib.parse, urllib.request
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher

NOTE = "Matches are automatic. Always check each site's rules before you trade."
MAX_PAGES_KALSHI = 150   # Kalshi events, 200 per page
n = datetime.now(timezone.utc)
f = "%Y-%m-%dT%H:%M:%SZ"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "AlphaIntelDesk/1.0"})
    return json.load(urllib.request.urlopen(req, timeout=30))


def ts(v):
    """Any time value (ms, s or ISO text) -> seconds."""
    if v in (None, ""):
        return 0.0
    if isinstance(v, (int, float)):
        return v / 1000 if v > 1e11 else float(v)
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


# ---------------- words ----------------
STOP = set("""fc cf afc sc ac cd sd ud club the will beat beats win wins winner vs v versus match game
who of to a an in on at by be is it for and or de del la el los las le les u21 u23 women womens
ufc wta atp nba nfl nhl mlb ncaa ncaaf ncaab epl mls lal ser bun cs2 counter strike dota lol valorant
esports bo1 bo3 bo5 2025 2026 2027 2028 jan feb mar apr may jun jul aug sep oct nov dec
how high low get what when which much many more than above below before after end year this next new
happen out again any does did do reach hit price yes no there between during until into become becomes""".split())
# place/scope words: "in the US" and worldwide are different markets
SCOPE = set("""us usa uk america american global worldwide world international europe european eu
canada china india japan russia mexico brazil france germany state states federal national""".split())
PROPS = set("""total totals spread over under handicap points goals corners cards half quarter set sets
map maps rounds exact score btts both margin first anytime player props period periods inning innings""".split())

# US team nicknames -> city / region words (Kalshi often names teams by city)
TEAMS = """76ers:philadelphia sixers:philadelphia celtics:boston nets:brooklyn knicks:new york raptors:toronto
bulls:chicago cavaliers:cleveland cavs:cleveland pistons:detroit pacers:indiana bucks:milwaukee hawks:atlanta
hornets:charlotte heat:miami magic:orlando wizards:washington nuggets:denver timberwolves:minnesota
thunder:oklahoma city blazers:portland jazz:utah warriors:golden state clippers:los angeles lakers:los angeles
suns:phoenix kings:sacramento mavericks:dallas rockets:houston grizzlies:memphis pelicans:new orleans
spurs:san antonio bills:buffalo dolphins:miami patriots:new england jets:new york ravens:baltimore
bengals:cincinnati browns:cleveland steelers:pittsburgh texans:houston colts:indianapolis jaguars:jacksonville
titans:tennessee broncos:denver chiefs:kansas city raiders:las vegas chargers:los angeles cowboys:dallas
giants:new york eagles:philadelphia commanders:washington bears:chicago lions:detroit packers:green bay
vikings:minnesota falcons:atlanta panthers:carolina saints:new orleans buccaneers:tampa bay cardinals:arizona
rams:los angeles 49ers:san francisco niners:san francisco seahawks:seattle bruins:boston sabres:buffalo
canadiens:montreal senators:ottawa leafs:toronto blackhawks:chicago avalanche:colorado stars:dallas wild:minnesota
predators:nashville blues:st louis flames:calgary oilers:edmonton canucks:vancouver ducks:anaheim
sharks:san jose kraken:seattle knights:vegas penguins:pittsburgh flyers:philadelphia capitals:washington
hurricanes:carolina devils:new jersey islanders:new york rangers:new york lightning:tampa bay
yankees:new york mets:new york orioles:baltimore rays:tampa bay red sox:boston blue jays:toronto
guardians:cleveland tigers:detroit royals:kansas city twins:minnesota white sox:chicago astros:houston
angels:los angeles athletics:oakland mariners:seattle braves:atlanta marlins:miami phillies:philadelphia
nationals:washington cubs:chicago reds:cincinnati brewers:milwaukee pirates:pittsburgh dodgers:los angeles
padres:san diego diamondbacks:arizona rockies:colorado mammoth:utah
fire:chicago crew:columbus revolution:new england whitecaps:vancouver sounders:seattle timbers:portland
dynamo:houston galaxy:los angeles union:philadelphia earthquakes:san jose rapids:colorado"""
ALIAS = {}
for pair in re.findall(r"([a-z0-9]+(?: sox| jays)?):([a-z ]+?)(?= [a-z0-9]+(?: sox| jays)?:|$)", TEAMS.replace("\n", " ")):
    ALIAS[pair[0]] = pair[1].split()


def words(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = s.replace("&", " and ")
    return [w for w in re.findall(r"[a-z0-9]+", s)]


def key_words(s):
    return [w for w in words(s) if w not in STOP and not w.isdigit() and len(w) > 1]


def numbers(s):
    return set(re.findall(r"(?<![a-z0-9])\d+(?:\.\d+)?(?![a-z0-9])", (s or "").lower().replace(",", "")))


def same_word(a, b):
    if a == b:
        return True
    if len(a) >= 4 and len(b) >= 4 and (a.startswith(b) or b.startswith(a)):
        return True
    return len(a) >= 5 and SequenceMatcher(None, a, b).ratio() >= 0.85


def covers(side, text_words):
    """Share of a name's key words found in the other text (1.0 = all found).
    A team nickname also counts if its city is there (76ers <-> Philadelphia); a matched last word
    (a surname, 'City', 'United') counts as the whole name."""
    sw = key_words(side)
    if not sw:
        return 0.0
    hit = lambda w: any(same_word(w, t) for t in text_words)
    found = [hit(w) for w in sw]
    share = sum(found) / len(sw)
    for w in sw:
        city = ALIAS.get(w)
        others = [x for x in sw if x != w and x not in ("trail", "maple", "red", "white", "blue")]
        if city and not others and all(hit(c) for c in city if c not in STOP):
            share = 1.0
    if len(sw) >= 2 and not found[-1] and share < 1.0:
        share = min(share, 0.4)              # a first name alone is not enough
    if len(sw) >= 2 and found[-1] and share >= 0.5:
        share = 1.0
    return share


def sides(title):
    """'A vs. B' or 'Will A beat B?' -> [A, B]; otherwise []."""
    t = re.sub(r"^[A-Za-z0-9 \-]{2,20}:\s*", "", title or "")       # drop 'UFC:' / 'WTA:' prefixes
    m = re.match(r"(?i)\s*will (.+?) (?:beat|defeat) (.+?)\??$", t)
    if m:
        return [m.group(1), m.group(2)]
    parts = re.split(r"(?i)\s+(?:vs\.?|v\.?|versus|@)\s+", t)
    if len(parts) == 2:
        return [parts[0], re.sub(r"[?:].*$", "", parts[1])]
    return []


# ---------------- load the three sites ----------------
def price(p):
    """Alpha Arcade price in millionths -> percent; None when there's no price yet."""
    return round(p / 1e4, 1) if p else None


def lead_of(outs):
    """The leading outcome: highest price, else the first team (not the draw)."""
    priced = [k for k, v in outs.items() if v is not None]
    if priced:
        return max(priced, key=lambda k: outs[k])
    return next((k for k in outs if k.lower() not in ("draw", "tie")), next(iter(outs)))


def load_alpha():
    b = json.load(open("alpha_live.json"))
    out = []
    for m in b["markets"]:
        end = ts(m.get("endTs"))
        if end <= n.timestamp():
            continue
        opts = m.get("options") or []
        vol = float(m.get("volume") or 0)
        if vol < 100 or (vol < 2000 and not m.get("twentyFourHrVolume")):
            # thin and no trades today: exactly 50/50 is just the starting price
            opts = [dict(o, yesProb=None) if o.get("yesProb") == 500000 else o for o in opts]
        if len(opts) == 1 or all((o.get("label") or "").lower() in ("yes", "no") for o in opts):
            yes = next((o for o in opts if (o.get("label") or "").lower() == "yes"), opts[0] if opts else {})
            sd = sides(m.get("title"))
            label = re.sub(r"(?i)^the\s+", "", sd[0]) if sd else "Yes"
            outs = {label: price(yes.get("yesProb"))}
        else:
            outs = {o.get("label") or "?": price(o.get("yesProb")) for o in opts}
            live = {k: v for k, v in outs.items()
                    if (label_date(k, end) or end) >= n.timestamp() - 2 * 86400}   # drop deadlines already passed
            outs = live or outs
        out.append({"id": m.get("id"), "title": m.get("title") or "", "end": end, "outcomes": outs,
                    "volume": vol, "volume24h": float(m.get("twentyFourHrVolume") or 0),
                    "categories": (m.get("primaryCategories") or []) + (m.get("categories") or []),
                    "rules": m.get("rules") or "", "fee": m.get("feeBasePercent"),
                    "url": "https://www.alphaarcade.com/market/" + (m.get("slug") or "")})
    return out


def load_poly():
    """All open Polymarket events, outcomes -> price (0-100)."""
    # Polymarket won't page past ~2,000 results, so ask for one end-date window at a time
    edges = [n + timedelta(days=d) for d in list(range(0, 15)) + [30, 60, 120, 240, 400, 800, 2000]]
    seen, evs = set(), []
    for lo, hi in zip(edges, edges[1:]):
        off = 0
        while off < 2000:
            try:
                d = get("https://gamma-api.polymarket.com/events?active=true&closed=false&limit=100"
                        f"&offset={off}&end_date_min={lo.strftime(f)}&end_date_max={hi.strftime(f)}")
            except Exception as err:
                print("Matcher: Polymarket window", lo.strftime("%b %d"), "stopped at", off, "-", err)
                break
            if not d:
                break
            for ev in d:
                k = ev.get("id") or ev.get("slug")
                if k not in seen:
                    seen.add(k); evs.append(ev)
            off += len(d)
            if len(d) < 100:
                break
    out = []
    for ev in evs:
        if "Up or Down" in (ev.get("title") or ""):
            continue
        e = {"title": ev.get("title") or "", "outcomes": {}, "text": "", "end": 0,
             "volume": float(ev.get("volume") or 0), "volume24h": float(ev.get("volume24hr") or 0),
             "rules": ev.get("description") or "", "url": "https://polymarket.com/event/" + (ev.get("slug") or ""),
             "categories": [t.get("label") or "" for t in (ev.get("tags") or []) if isinstance(t, dict)]}
        for m in ev.get("markets") or []:
            if m.get("closed") or m.get("acceptingOrders") is False:
                continue
            try:
                names = json.loads(m.get("outcomes") or "[]")
                prices = [float(p) for p in json.loads(m.get("outcomePrices") or "[]")]
            except (ValueError, TypeError):
                continue
            q = m.get("question") or ""
            e["text"] += " " + q
            e["end"] = e["end"] or ts(m.get("gameStartTime") or m.get("endDate"))
            if [x.lower() for x in names] == ["yes", "no"] and prices:
                bb, ba = m.get("bestBid"), m.get("bestAsk")
                if bb is not None and ba is not None and float(ba) - float(bb) > 0.5:
                    continue                           # nobody really bidding/asking: the price is a placeholder
                lbl = m.get("groupItemTitle") or q
                e["outcomes"][lbl] = round(prices[0] * 100, 1)
                try:                                   # Yes token id: lets make_gaps.py read the order book (fillable size)
                    e.setdefault("book", {})[lbl] = json.loads(m.get("clobTokenIds") or "[]")[0]
                except (ValueError, TypeError, IndexError):
                    pass
                e.setdefault("ends", {})[lbl] = ts(m.get("endDate"))
                e.setdefault("qs", {})[lbl] = q
                if m.get("oneDayPriceChange") is not None:
                    e.setdefault("chg", {})[lbl] = round(float(m.get("oneDayPriceChange") or 0) * 100, 1)
                    e.setdefault("v24", {})[lbl] = float(m.get("volume24hr") or 0)
            else:
                try:
                    toks = json.loads(m.get("clobTokenIds") or "[]")
                except (ValueError, TypeError):
                    toks = []
                for i, (nm, p) in enumerate(zip(names, prices)):
                    e["outcomes"][nm] = round(p * 100, 1)
                    if i < len(toks):
                        e.setdefault("book", {})[nm] = toks[i]
        e["end"] = e["end"] or ts(ev.get("endDate"))
        if e["outcomes"]:
            out.append(e)
    return out


def load_kalshi():
    """All open Kalshi events; each market in an event is one outcome."""
    evs, cur = [], ""
    for _ in range(MAX_PAGES_KALSHI):
        try:
            d = get("https://api.elections.kalshi.com/trade-api/v2/events?status=open&with_nested_markets=true"
                    f"&limit=200&cursor={cur}")
        except Exception as err:
            print("Matcher: Kalshi stopped after", len(evs), "events -", err)
            break
        evs += d.get("events") or []
        cur = d.get("cursor") or ""
        if not cur:
            break
    out = []
    for ev in evs:
        k = ev.get("event_ticker") or ""
        e = {"title": ev.get("title") or "", "outcomes": {}, "text": ev.get("sub_title") or "", "end": 0,
             "volume": 0.0, "volume24h": 0.0, "rules": "", "url": "https://kalshi.com/markets/" + (ev.get("series_ticker") or k.split("-")[0]).lower(),
             "categories": [ev.get("category") or ""], "alt": ""}
        for m in ev.get("markets") or []:
            if m.get("status") not in (None, "active", "open"):
                continue
            bid = float(m.get("yes_bid_dollars") or 0)
            ask = float(m.get("yes_ask_dollars") or 0)
            last = float(m.get("last_price_dollars") or 0)
            p = (bid + ask) / 2 if bid > 0 and ask > 0 else last
            label = m.get("yes_sub_title") or m.get("subtitle") or m.get("title") or ev.get("title") or "Yes"
            e["outcomes"][label] = round(p * 100, 1) if p > 0 else None
            if m.get("ticker"):
                e.setdefault("book", {})[label] = m["ticker"]       # for the order book (fillable size)
            e.setdefault("ends", {})[label] = ts(m.get("expected_expiration_time") or m.get("close_time"))
            e.setdefault("qs", {})[label] = m.get("title") or ""
            pb = float(m.get("previous_yes_bid_dollars") or 0)
            pa = float(m.get("previous_yes_ask_dollars") or 0)
            prev = (pb + pa) / 2 if pb > 0 and pa > 0 else float(m.get("previous_price_dollars") or 0)
            if p > 0 and prev > 0:
                e.setdefault("chg", {})[label] = round((p - prev) * 100, 1)
                e.setdefault("v24", {})[label] = float(m.get("volume_24h_fp") or m.get("volume_24h") or 0)
            e["volume"] += float(m.get("volume_fp") or m.get("volume") or 0)
            e["volume24h"] += float(m.get("volume_24h_fp") or m.get("volume_24h") or 0)
            e["text"] += " " + (m.get("title") or "") + " " + label
            e["end"] = e["end"] or ts(m.get("expected_expiration_time") or m.get("close_time"))
            e["rules"] = e["rules"] or (m.get("rules_primary") or "")
        if len(e["outcomes"]) == 1:          # one-market event: its question is often closer to other sites' titles
            e["alt"] = (ev.get("markets") or [{}])[0].get("title") or ""
        if e["outcomes"]:
            out.append(e)
    return out


# ---------------- matching ----------------
def by_deadline(real, ends, a_end):
    """In a ladder of deadlines (before 2027 / before 2028 ...) pick the one that ends with the Alpha market."""
    if not a_end:
        return None
    when = {k: label_date(k) or (ends or {}).get(k) for k in real}   # the date in the name beats the expiry time
    if not any(when.values()):
        return None
    ds = sorted((abs(when[k] - a_end) if when.get(k) else 9e12, k) for k in real)
    away = max(0.0, a_end - n.timestamp())
    ok = ds[0][0] <= max(2 * 86400, away * 0.05)
    clear = len(ds) < 2 or ds[1][0] - ds[0][0] >= 86400         # same end for all = a price ladder, not dates
    return ds[0][1] if ok and clear else None


MONTHS = {m: i + 1 for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split())}


def label_date(label, ref=None):
    """'December 31' / 'Dec 31, 2026' / 'Before Jan 1, 2027' / 'Before 2027' / 'In 2026' -> timestamp, else None."""
    t = (label or "").lower()
    m = re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s*(\d{4}))?", t)
    if m:
        mo, d = MONTHS[m.group(1)], int(m.group(2))
        try:
            if m.group(3):
                dt = datetime(int(m.group(3)), mo, d, tzinfo=timezone.utc)
            elif ref:                                # no year: the last time that date falls before the market ends
                r = datetime.fromtimestamp(ref, timezone.utc)
                dt = datetime(r.year, mo, d, tzinfo=timezone.utc)
                if dt > r + timedelta(days=2):
                    dt = datetime(r.year - 1, mo, d, tzinfo=timezone.utc)
            else:                                    # no year: the next time that date comes round
                dt = datetime(n.year, mo, d, tzinfo=timezone.utc)
                if dt < n - timedelta(days=1):
                    dt = datetime(n.year + 1, mo, d, tzinfo=timezone.utc)
        except ValueError:
            return None
    else:
        y = re.fullmatch(r"\s*(before|by|in|end of)?\s*(20\d\d)\s*", t)
        if not y:
            return None
        dt = datetime(int(y.group(2)) + (0 if y.group(1) == "before" else 1), 1, 1, tzinfo=timezone.utc)
        return dt.timestamp() - 86400                # Before 2027 / In 2026 = by Dec 31, 2026
    if "before" in t:
        dt -= timedelta(days=1)                      # Before Jan 1, 2027 = by Dec 31, 2026
    return dt.timestamp()


def by_date_label(label, outs, ends, a_end=0):
    """Alpha option 'December 31' -> the other site's market for the same deadline."""
    d = label_date(label, a_end or None)
    if d is None:
        return None
    real = [k for k in outs if k.lower() != "no"]
    return by_deadline(real, ends, d)


def map_outcome(label, outs, ends=None, a_end=0):
    """Which outcome on the other site is the same as this Alpha outcome?"""
    if label.lower() in ("draw", "tie"):
        for k in outs:
            if k.lower() in ("draw", "tie") or "draw" in words(k) or "tie" in words(k):
                return k
        return None
    if label.lower() == "yes":
        real = [k for k in outs if k.lower() != "no"]
        return real[0] if len(real) == 1 else by_deadline(real, ends, a_end)
    k = by_date_label(label, outs, ends, a_end)
    if k:
        return k
    best, bs = None, (0.0, 0)
    for k in outs:
        kw = words(k)
        if k.lower() in ("yes", "no") or "draw" in kw or "tie" in kw:
            continue
        if numbers(label) and numbers(k) != numbers(label):
            continue                                   # Above 4% is not Above $150
        s = (covers(label, key_words(k)), -len(kw))          # best match, then shortest label
        if s > bs:
            best, bs = k, s
    return best if bs[0] >= 0.5 else None


# ---------- fine print: resolution sources + cancel/void rules (Nov 10) ----------
# Each source: (name shown on the site, family, pattern). Same name on both sites = match;
# different news outlets = similar; any other difference = differ (pair kept out of the gap math).
import re as _re
SOURCES = [
    ("AP", "news", r"associated press|\bap\b"), ("Fox News", "news", r"fox news"), ("NBC", "news", r"\bnbc\b"),
    ("CNN", "news", r"\bcnn\b"), ("ABC News", "news", r"abc news"), ("CBS", "news", r"\bcbs\b"),
    ("Reuters", "news", r"reuters"), ("Bloomberg", "news", r"bloomberg"), ("Decision Desk", "news", r"decision desk"),
    ("BLS", "gov", r"bureau of labor statistics|\bbls\b"), ("BEA", "gov", r"bureau of economic analysis|\bbea\b"),
    ("Federal Reserve", "gov", r"federal reserve|\bfomc\b"), ("US Treasury", "gov", r"treasury"),
    ("Census Bureau", "gov", r"census bureau"), ("Congress", "gov", r"congress\.gov|clerk of the house|senate\.gov"),
    ("Federal Register", "gov", r"federal register"), ("NOAA / NWS", "gov", r"\bnoaa\b|national weather service"),
    ("Binance", "crypto", r"binance"), ("Coinbase", "crypto", r"coinbase"), ("CoinGecko", "crypto", r"coingecko"),
    ("CoinMarketCap", "crypto", r"coinmarketcap"), ("Kraken", "crypto", r"kraken"), ("Chainlink", "crypto", r"chainlink"),
    ("Pyth", "crypto", r"\bpyth\b"), ("Yahoo Finance", "data", r"yahoo finance"),
    ("Nasdaq Private Market", "data", r"nasdaq private market"), ("Challenger", "data", r"challenger, gray"),
    ("Box Office Mojo", "data", r"box office mojo"), ("The Numbers", "data", r"the-numbers|the numbers\b"),
    ("Billboard", "data", r"billboard"), ("Spotify", "data", r"spotify"), ("Google Trends", "data", r"google trends"),
    ("Christie's", "data", r"christie"), ("Sotheby's", "data", r"sotheby"), ("Wikipedia", "data", r"wikipedia"),
]
CANCEL = r"50[-/ ]?50|fifty[- ]fifty|refund|\bvoid|cancel|postpone|annul"
RANK = {"match": 0, "similar": 1, "unknown": 2, "differ": 3}


def sources_in(text):
    t = (text or "").lower()
    return {name: fam for name, fam, pat in SOURCES if _re.search(pat, t)}


def fine_print(ra, rb):
    """Compare two sites' rules text: {'src': match|similar|unknown|differ, 'srcs': [...], 'void': same|check|none}."""
    a, b = sources_in(ra), sources_in(rb)
    both = sorted(set(a) & set(b))
    if not a or not b:
        src = "unknown"                                  # one site doesn't name a source in its rules text
    elif both:
        src = "match"
    elif {"news"} >= set(a.values()) | set(b.values()):
        src = "similar"                                  # different news outlets calling the same result
    else:
        src = "differ"
    ca, cb = bool(_re.search(CANCEL, (ra or "").lower())), bool(_re.search(CANCEL, (rb or "").lower()))
    void = "same" if ca and cb else "check" if ca != cb else "none"
    return {"src": src, "srcs": both or sorted(set(a) | set(b)), "void": void}


def score(a, e):
    """(score 0-100, flags, outcome map) for Alpha market a vs other-site event e."""
    sd = sides(a["title"])
    text = key_words(e["title"] + " " + e["text"])
    if sd:
        real = [k for k in e["outcomes"] if k.lower() not in ("draw", "tie")]
        if len(real) > 3:
            return 0, [], {}                           # a field of many (a championship), not a head-to-head
        c = [covers(x, text) for x in sd]
        if min(c) < 0.5:
            return 0, [], {}
        name = 50 * (c[0] + c[1]) / 2
    else:
        aw, an, best_j = set(key_words(a["title"])), numbers(a["title"]), 0.0
        for t in [e["title"], e.get("alt") or ""] + list((e.get("qs") or {}).values())[:8]:
            ew, en = set(key_words(t)), numbers(t)
            if not aw or not ew or (an and en and an != en):
                continue                                        # different line or threshold
            both = {w for w in aw if any(same_word(w, x) for x in ew)}
            if (aw ^ ew) & SCOPE:
                continue                                        # one says "US", the other doesn't
            j = len(both) / (len(aw) + len(ew) - len(both))
            if j >= 0.6 and len(both) >= min(2, len(aw)):
                best_j = max(best_j, j)
        if not best_j:
            return 0, [], {}
        name = 50 * best_j
    if (PROPS & set(words(e["title"]))) and not (PROPS & set(words(a["title"]))):
        return 0, [], {}                                        # totals/spreads are a different market
    an, en = numbers(a["title"]), numbers(e["title"])
    if sd and an and en and an != en:
        return 0, [], {}                                        # different line or threshold
    omap = {l: map_outcome(l, e["outcomes"], e.get("ends"), a["end"]) for l in a["outcomes"]}
    lead = lead_of(a["outcomes"])
    s = name + (20 if omap.get(lead) is not None else 0)
    mo = omap.get(lead)
    e_end = (label_date(mo) if mo else None) or (e.get("ends") or {}).get(mo) or e["end"]
    hours = abs(a["end"] - e_end) / 3600 if a["end"] and e_end else 9999
    away = max(0.0, (a["end"] - n.timestamp()) / 3600)          # hours until the Alpha market ends
    s += 20 if hours <= max(12, away * 0.03) else 10 if hours <= max(36, away * 0.06) else 0
    mapped = sum(v is not None for v in omap.values())
    s += 10 if mapped >= 0.6 * len(omap) else 0               # most outcomes line up (fields of candidates differ a bit)
    flags = []
    if hours > max(12, away * 0.03):
        flags.append("end dates differ by %s" % ("%dh" % hours if hours < 72 else "%d days" % (hours / 24)))
    if any(l.lower() == "draw" for l in a["outcomes"]) and not omap.get("Draw") and not omap.get("draw"):
        flags.append("draw handled differently")
    ra, re_ = a["rules"].lower(), e["rules"].lower()
    if ("regulation" in ra) != ("regulation" in re_) or ("overtime" in ra) != ("overtime" in re_):
        flags.append("check overtime / extra-time rules")
    fp = fine_print(a["rules"], e["rules"])
    if fp["src"] == "differ":
        flags.append("resolution sources differ (%s)" % ", ".join(fp["srcs"][:4]))
    return min(100, round(s)), flags, omap


def build_index(events):
    """word prefix -> events containing it (fast first pass)."""
    idx = {}
    for i, e in enumerate(events):
        for w in set(key_words(e["title"] + " " + e["text"])):
            idx.setdefault(w[:4], set()).add(i)
    return idx


def candidates(a, events, idx):
    ws = set(key_words(a["title"]))
    for w in list(ws):
        ws.update(ALIAS.get(w, []))
    hits = {}
    for w in ws:
        for i in idx.get(w[:4], ()):
            hits[i] = hits.get(i, 0) + 1
    need = 2 if len(ws) >= 2 else 1
    return [events[i] for i, c in hits.items() if c >= need]


def best_match(a, events, idx):
    best = (0, [], {}, None)
    away = max(0.0, a["end"] - n.timestamp())
    for e in candidates(a, events, idx):
        ends = [x for x in [e["end"]] + list((e.get("ends") or {}).values()) +
                [label_date(k) for k in list(e["outcomes"])[:40]] if x]
        if a["end"] and ends and min(abs(a["end"] - x) for x in ends) > max(4 * 86400, away * 0.15):
            continue
        s, fl, om = score(a, e)
        if s > best[0]:
            best = (s, fl, om, e)
    return best


SPORTY = ("sport", "esports", "soccer", "football", "basketball", "baseball", "hockey", "nfl", "nba", "mls",
          "nhl", "mlb", "ufc", "mma", "tennis", "f1", "golf", "league", "cricket", "boxing", "games")
PK_MIN_POLY_VOLUME = 5000       # same floor make_gaps.py uses for Polymarket


def sporty(e):
    return any(any(t in (c or "").lower() for t in SPORTY) for c in e.get("categories") or []) \
        or bool(sides(e["title"]))


def poly_kalshi(poly, kalshi, used):
    """Polymarket <-> Kalshi pairs with no Alpha market in between (non-sports only)."""
    ks = [e for e in kalshi if not sporty(e)]
    idx = build_index(ks)
    best = {}                                          # kalshi url -> best row, so each Kalshi event is used once
    for p in poly:
        if p["url"] in used or sporty(p) or p["volume"] < PK_MIN_POLY_VOLUME:
            continue
        outs = p["outcomes"]
        if len(outs) == 1:
            outs = {"Yes": next(iter(outs.values()))}  # one-question event: compare it as Yes
        a = {"id": p["url"], "title": p["title"], "end": p["end"], "outcomes": outs, "rules": p["rules"]}
        s, fl, om, e = best_match(a, ks, idx)
        if not e or s < 70:
            continue
        lead = lead_of(outs)
        label = "SAME" if s >= 90 else "SIMILAR"
        fp = fine_print(p["rules"], e["rules"])
        k = {"url": e["url"], "title": e["title"], "score": s, "flags": fl, "label": label, "fine": fp,
             "volume": round(e["volume"]), "volume24h": round(e["volume24h"]), "matched_outcome": om.get(lead),
             "outcomes": {l: e["outcomes"][x] for l, x in om.items() if x is not None},
             "book": {l: (e.get("book") or {}).get(x) for l, x in om.items() if x is not None}}
        row = {"title": p["title"], "close": datetime.fromtimestamp(p["end"] or e["end"], timezone.utc).strftime(f),
               "sites": {"polymarket": {"url": p["url"], "title": p["title"], "score": s, "flags": fl, "label": label, "fine": fp,
                                        "volume": round(p["volume"]), "volume24h": round(p["volume24h"]),
                                        "matched_outcome": lead, "outcomes": outs,
                                        "book": {lead: (p.get("book") or {}).get(lead if len(p["outcomes"]) > 1 else next(iter(p["outcomes"])))}},
                         "kalshi": k},
               "flags": fl, "score": s, "categories": (p.get("categories") or []) + (e.get("categories") or []),
               "outcome": lead, "prices": {"polymarket": outs[lead], "kalshi": k["outcomes"].get(lead)},
               "label": label, "pair": "polymarket-kalshi"}
        ps = [v for v in row["prices"].values() if v is not None]
        row["gap"] = round(max(ps) - min(ps), 1) if len(ps) > 1 and label == "SAME" else None
        if e["url"] not in best or s > best[e["url"]]["score"]:
            best[e["url"]] = row
    return list(best.values())


# ---------------- movers ----------------
MOVE_MIN = 5                                        # points (cents) moved in 24h
MOVE_VOL = {"polymarket": 25000, "kalshi": 15000, "alpha": 100}  # 24h volume: $ / contracts / $
LADDER = re.compile(r"(?i)^\s*(above|below|over|under|between|at least|at most|more than|less than|fewer than|"
                    r"[$<>≥≤]\s*\d|\d[\d,.]*\s*(%|[kmb]\b|\+|$))")
MENTION = re.compile(r"(?i)\b(say|says|mention|mentions|tweet|tweets|post)\b|view count|top \d+ (song|album)")
MOVE_TOP, MOVE_ALPHA, MOVE_MAX_CRYPTO = 10, 3, 2
NAMES = {"alpha": "Alpha Arcade", "polymarket": "Polymarket", "kalshi": "Kalshi"}


def why_link(title):
    q = " ".join(key_words(title)[:6]) or title
    return "https://news.google.com/search?" + urllib.parse.urlencode({"q": q, "hl": "en-US", "gl": "US", "ceid": "US:en"})


def alpha_changes(alpha):
    """Alpha has no 24h change in its data: keep hourly snapshots and compare with ~24h ago."""
    try:
        hist = json.load(open("alpha_hist.json"))
    except Exception:
        hist = []
    now = n.timestamp()
    snap = {a["id"]: {k: v for k, v in a["outcomes"].items() if v is not None} for a in alpha}
    hist = [h for h in hist if now - h["t"] <= 26 * 3600] + [{"t": now, "p": snap}]
    json.dump(hist, open("alpha_hist.json", "w"), separators=(",", ":"))
    old = [h for h in hist if now - h["t"] >= 20 * 3600]
    if not old:
        print("Movers: Alpha history is %.1fh old, needs 20h before Alpha moves show" % ((now - hist[0]["t"]) / 3600))
        return {}
    base = old[-1]["p"]                                  # the snapshot closest to 24h ago
    return {i: {k: round(v - base[i][k], 1) for k, v in o.items() if k in base.get(i, {})} for i, o in snap.items()}


def movers(alpha, sites):
    rows = []
    soon = n.timestamp() + 3 * 86400                     # skip markets ending within 3 days (daily/weekly ranges)
    achg = alpha_changes(alpha)
    for a in alpha:
        if sporty(a) or a["end"] < soon or a["volume24h"] < MOVE_VOL["alpha"]:
            continue
        for k, c in (achg.get(a["id"]) or {}).items():
            rows.append(("alpha", a, k, a["outcomes"][k], c, a["volume24h"]))
    for site in ("polymarket", "kalshi"):
        for e in sites[site]:
            if sporty(e) or (e["end"] and e["end"] < soon):
                continue
            for k, c in (e.get("chg") or {}).items():
                v = (e.get("v24") or {}).get(k, 0)
                if v >= MOVE_VOL[site]:
                    rows.append((site, e, k, e["outcomes"].get(k), c, v))
    best = {}
    for site, e, k, p, c, v in rows:
        if p is None or not (5 <= p <= 95) or abs(c) < MOVE_MIN:
            continue
        if LADDER.match(k or "") or MENTION.search(e["title"]) or \
                any("mention" in (x or "").lower() for x in e.get("categories") or []):
            continue                                     # price brackets and word-mention markets swing for no news
        if k == e["title"] or len(k) > 45 or k.lower() == "yes":
            k = "Yes"                                    # one-question market: the label is the question
        key = (site, e["url"])
        if key not in best or abs(c) > abs(best[key]["change"]):
            best[key] = {"title": e["title"], "outcome": k, "site": site, "name": NAMES[site], "price": p,
                         "change": c, "prev": round(p - c, 1), "vol24": round(v), "url": e["url"],
                         "why": why_link(e["title"]), "category": (e.get("categories") or ["Other"])[0] or "Other",
                         "crypto": any("crypto" in (x or "").lower() or "financ" in (x or "").lower()
                                       for x in e.get("categories") or [])}
    import math
    allr = sorted(best.values(), key=lambda r: -abs(r["change"]) * math.log10(max(r["vol24"], 10)))
    out, crypto = [r for r in allr if r["site"] == "alpha"][:MOVE_ALPHA], 0
    for r in allr:
        if len(out) >= MOVE_TOP:
            break
        if r in out or (r["crypto"] and crypto >= MOVE_MAX_CRYPTO):
            continue
        crypto += r["crypto"]
        out.append(r)
    out.sort(key=lambda r: -abs(r["change"]) * math.log10(max(r["vol24"], 10)))
    json.dump({"updated": n.strftime(f), "note": "Biggest 24-hour price moves with real trading behind them. No sports. "
               "\"Why?\" opens a news search, not our analysis.", "movers": out}, open("movers.json", "w"), indent=1)
    cnt = {s_: sum(r["site"] == s_ for r in allr) for s_ in NAMES}
    print("Movers: %d shown | candidates Poly %d, Kalshi %d, Alpha %d" % (len(out), cnt["polymarket"], cnt["kalshi"], cnt["alpha"]))
    for r in out:
        print("  %+5.1f | %-11s | %s | %s | now %s | 24h vol %s" % (r["change"], r["name"], r["title"][:44], r["outcome"][:16], r["price"], r["vol24"]))


# ---------------- calendar links ----------------
def calendar_links(alpha, sites):
    """For each catalysts.json event with "find" word-sets, pick each site's own market for it
    (title holds every word of a set; earlier sets win, then the market settling closest to the event date).
    Skips word-mention and combo markets. Writes cal_links.json."""
    try:
        cats = json.load(open("catalysts.json"))["events"]
    except Exception as err:
        print("Calendar links: no catalysts.json -", err)
        return
    pools = {"alpha": alpha, "polymarket": sites.get("polymarket", []), "kalshi": sites.get("kalshi", [])}
    rx = lambda w: re.compile(r"(?<![a-z0-9])" + re.escape(w.lower()))
    skip = re.compile(r"\b(say|said|mention|mentions|combo|parlay)\b")   # word-mention and combo markets aren't the event itself
    out = {}
    for c in cats:
        finds = c.get("find") or []
        try:
            when = datetime.strptime(c["date"], f).replace(tzinfo=timezone.utc).timestamp()
        except (KeyError, ValueError):
            continue
        if not finds or not (n.timestamp() - 2 * 86400 <= when <= n.timestamp() + 60 * 86400):
            continue
        sets = [[rx(w) for w in s] for s in finds]
        nots = [rx(w) for w in c.get("not") or []]          # words that rule a market out for this event
        links = {}
        for site, evs in pools.items():
            hits = []
            for e in evs:
                t = (e.get("title", "") + " " + e.get("alt", "")).lower()
                if skip.search(t) or any(r.search(t) for r in nots):
                    continue
                si = next((i for i, s in enumerate(sets) if all(r.search(t) for r in s)), None)
                if si is None:
                    continue
                end = e.get("end") or 0
                if not end or end < when - 2 * 86400 or end > when + 45 * 86400:
                    continue
                priced = {k: v for k, v in (e.get("outcomes") or {}).items() if v is not None}
                if not priced:
                    continue
                hits.append((si, abs(end - when) // 86400, -(e.get("volume") or 0), e, priced))
            hits.sort(key=lambda h: h[:3])                 # earlier word-set first, then closest date, then volume
            hits = [h[1:] for h in hits]
            if hits:
                _, _, e, priced = hits[0]
                oc = min(priced, key=lambda k: (abs(priced[k] - 50), -priced[k]))   # the outcome most in play
                links[site] = {"title": e["title"], "outcome": oc, "price": priced[oc], "url": e["url"],
                               "end": datetime.fromtimestamp(e["end"], timezone.utc).strftime(f),
                               "volume": round(e.get("volume") or 0)}
            print("  CAL %-10s | %-34s | %s" % (site, c["name"][:34],
                  "; ".join("%s [%s %s, ends %s]" % (h[2]["title"][:50], min(h[3], key=lambda k: abs(h[3][k] - 50))[:22],
                            h[3][min(h[3], key=lambda k: abs(h[3][k] - 50))], datetime.fromtimestamp(h[2]["end"], timezone.utc).strftime("%b %d"))
                            for h in hits[:3]) or "-"))
        if links:
            out[c["date"] + "|" + c["name"]] = links
    json.dump({"updated": n.strftime(f), "links": out}, open("cal_links.json", "w"), indent=1)
    print("Calendar links: %d events linked" % len(out))


def main():
    alpha = load_alpha()
    sites = {}
    for name, fn in (("polymarket", load_poly), ("kalshi", load_kalshi)):
        try:
            sites[name] = fn()
        except Exception as err:
            print("Matcher:", name, "failed:", err)
            sites[name] = []
    print("Matcher: %d Alpha Arcade markets | %d Polymarket events | %d Kalshi events"
          % (len(alpha), len(sites["polymarket"]), len(sites["kalshi"])))
    try:
        movers(alpha, sites)
    except Exception as err:
        print("Movers failed:", err)
    try:
        calendar_links(alpha, sites)
    except Exception as err:
        print("Calendar links failed:", err)
    idxs = {k: build_index(v) for k, v in sites.items()}
    try:
        fix = json.load(open("match_fixes.json"))      # {"block": [["alpha id", "other url"], ...]}
    except Exception:
        fix = {}
    blocked = {tuple(x) for x in fix.get("block", [])}

    out, near = [], []
    for a in alpha:
        row = {"title": a["title"], "close": datetime.fromtimestamp(a["end"], timezone.utc).strftime(f),
               "sites": {"alpha": {"url": a["url"], "outcomes": a["outcomes"], "volume": round(a["volume"]),
                                   "volume24h": round(a["volume24h"]), "fee": a["fee"]}},
               "flags": [], "score": 100, "categories": a["categories"]}
        lead = lead_of(a["outcomes"])
        row["outcome"] = lead
        row["prices"] = {"alpha": a["outcomes"][lead]}
        for name, evs in sites.items():
            s, fl, om, e = best_match(a, evs, idxs[name])
            if name == "kalshi" and (not e or s < 70) and a["volume"] >= 1000 and not sporty(a):
                if not e:                              # nothing scored: show the Kalshi title sharing the most words
                    aw = set(key_words(a["title"]))
                    c = candidates(a, evs, idxs[name])
                    e = max(c, key=lambda x: len(aw & set(key_words(x["title"]))), default=None)
                    s, om = 0, {}
                near.append((a["title"], s, e["title"] if e else "-", (om or {}).get(lead_of(a["outcomes"]))))
                e = None if s < 70 else e
            if not e or s < 70 or (a["id"], e["url"]) in blocked:
                continue
            row["sites"][name] = {"url": e["url"], "title": e["title"], "score": s, "flags": fl,
                                  "label": "SAME" if s >= 90 else "SIMILAR", "fine": fine_print(a["rules"], e["rules"]),
                                  "volume": round(e["volume"]), "volume24h": round(e["volume24h"])}
            row["sites"][name]["matched_outcome"] = om.get(lead)
            # this site's price for every Alpha outcome it lines up with
            row["sites"][name]["outcomes"] = {l: e["outcomes"][k] for l, k in om.items() if k is not None}
            row["sites"][name]["book"] = {l: (e.get("book") or {}).get(k) for l, k in om.items() if k is not None}
            row["prices"][name] = e["outcomes"][om[lead]] if om.get(lead) is not None else None
            row["score"] = min(row["score"], s)
            row["flags"] += [x for x in fl if x not in row["flags"]]
        if len(row["sites"]) < 2:
            continue
        row["label"] = "SAME" if row["score"] >= 90 else "SIMILAR"
        ps = [v for v in row["prices"].values() if v is not None]
        row["gap"] = round(max(ps) - min(ps), 1) if len(ps) > 1 and row["label"] == "SAME" else None
        out.append(row)

    print("Matcher: %d busy non-sports Alpha markets with no Kalshi match (best try shown):" % len(near))
    for t, sc, kt, mo in near[:20]:
        print("  NEAR %3d | %s | K: %s -> %s" % (sc, t[:44], kt[:48], mo))
    used = {r["sites"]["polymarket"]["url"] for r in out if "polymarket" in r["sites"]}
    pk = poly_kalshi(sites["polymarket"], sites["kalshi"], used)
    print("Matcher: %d Polymarket-Kalshi pairs (%d SAME)" % (len(pk), sum(r["label"] == "SAME" for r in pk)))
    for r in sorted(pk, key=lambda r: -r["score"])[:25]:
        x = r["sites"]["kalshi"]
        print("  PK %-7s %3d | %s | %s | P %s K %s | K: %s -> %s" % (
            r["label"], r["score"], r["title"][:44], r["outcome"][:18], r["prices"]["polymarket"],
            r["prices"]["kalshi"], x["title"][:44], x["matched_outcome"]))
    out += pk

    out.sort(key=lambda r: (r["label"] != "SAME", -(r["gap"] or 0)))
    json.dump({"updated": n.strftime(f), "note": NOTE, "matches": out}, open("matches.json", "w"), indent=1)
    same = sum(r["label"] == "SAME" for r in out)
    print("Matcher: %d matched (%d SAME, %d SIMILAR)" % (len(out), same, len(out) - same))
    try:
        import collections
        c = collections.Counter(x.get("fine", {}).get("src") for r in out + pk for n, x in r["sites"].items() if n != "alpha")
        print("FINE sources:", dict(c))
        for r in (out + pk)[:400]:
            for n, x in r["sites"].items():
                fp = x.get("fine")
                if fp and fp["src"] in ("differ", "similar") and x.get("label") == "SAME":
                    print("  FINE %-7s %-10s | %s | %s" % (fp["src"], n, r["title"][:50], ", ".join(fp["srcs"][:5])))
    except Exception as err:
        print("FINE log failed:", err)
    for r in out[:30]:
        p = r["prices"]
        print("  %-7s %3d | %s | %s | A %s P %s K %s | gap %s | A vol $%s %s" % (
            r["label"], r["score"], r["title"][:48], r["outcome"][:22], p.get("alpha"),
            p.get("polymarket", "-"), p.get("kalshi", "-"), r["gap"], r["sites"].get("alpha", {}).get("volume", "-"),
            "; ".join(r["flags"])))
        for site in ("polymarket", "kalshi"):          # what it matched, so we can check it
            x = r["sites"].get(site)
            if x:
                print("        %s %d: %s -> %s" % (site[0].upper(), x["score"], x["title"][:60], x["matched_outcome"]))


if __name__ == "__main__":
    main()
