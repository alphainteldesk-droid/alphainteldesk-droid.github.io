# Alpha Intel Desk: cross-site matching engine (v1).
# For every open Alpha Arcade market (any end date), find the same event on
# Polymarket and Kalshi, line up the outcomes, and score how sure we are they're the same market.
#   SAME (90+)     same event, same outcome, end times line up  -> used for Gap Radar math
#   SIMILAR (70-89) probably the same event, something differs   -> shown with a badge, never gap math
#   below 70        hidden
# Writes matches.json. Public market data only.
import json, re, time, unicodedata, urllib.request
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
happen out again any does did do reach hit price yes no there between during until""".split())
PROPS = set("""total totals spread over under handicap points goals corners cards half quarter set sets
map maps rounds exact score btts both margin first anytime player props""".split())

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
        if city and all(hit(c) for c in city if c not in STOP):
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
        if vol < 100:        # barely traded: exactly 50/50 is just the starting price
            opts = [dict(o, yesProb=None) if o.get("yesProb") == 500000 else o for o in opts]
        if len(opts) == 1 or all((o.get("label") or "").lower() in ("yes", "no") for o in opts):
            yes = next((o for o in opts if (o.get("label") or "").lower() == "yes"), opts[0] if opts else {})
            sd = sides(m.get("title"))
            label = re.sub(r"(?i)^the\s+", "", sd[0]) if sd else "Yes"
            outs = {label: price(yes.get("yesProb"))}
        else:
            outs = {o.get("label") or "?": price(o.get("yesProb")) for o in opts}
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
             "rules": ev.get("description") or "", "url": "https://polymarket.com/event/" + (ev.get("slug") or "")}
        for m in ev.get("markets") or []:
            if m.get("closed"):
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
                e["outcomes"][m.get("groupItemTitle") or q] = round(prices[0] * 100, 1)
            else:
                for nm, p in zip(names, prices):
                    e["outcomes"][nm] = round(p * 100, 1)
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
             "volume": 0.0, "volume24h": 0.0, "rules": "", "url": "https://kalshi.com/markets/" + (ev.get("series_ticker") or k.split("-")[0]).lower()}
        for m in ev.get("markets") or []:
            if m.get("status") not in (None, "active", "open"):
                continue
            bid = float(m.get("yes_bid_dollars") or 0)
            ask = float(m.get("yes_ask_dollars") or 0)
            last = float(m.get("last_price_dollars") or 0)
            p = (bid + ask) / 2 if bid > 0 and ask > 0 else last
            label = m.get("yes_sub_title") or m.get("subtitle") or m.get("title") or ev.get("title") or "Yes"
            e["outcomes"][label] = round(p * 100, 1) if p > 0 else None
            e["volume"] += float(m.get("volume_fp") or m.get("volume") or 0)
            e["volume24h"] += float(m.get("volume_24h_fp") or m.get("volume_24h") or 0)
            e["text"] += " " + (m.get("title") or "") + " " + label
            e["end"] = e["end"] or ts(m.get("expected_expiration_time") or m.get("close_time"))
            e["rules"] = e["rules"] or (m.get("rules_primary") or "")
        if e["outcomes"]:
            out.append(e)
    return out


# ---------------- matching ----------------
def map_outcome(label, outs):
    """Which outcome on the other site is the same as this Alpha outcome?"""
    if label.lower() in ("draw", "tie"):
        for k in outs:
            if k.lower() in ("draw", "tie") or "draw" in words(k) or "tie" in words(k):
                return k
        return None
    if label.lower() == "yes":
        real = [k for k in outs if k.lower() != "no"]
        return real[0] if len(real) == 1 else None
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
        aw, ew = set(key_words(a["title"])), set(key_words(e["title"]))
        if not aw or not ew:
            return 0, [], {}
        both = aw & ew
        j = len(both) / len(aw | ew)
        if j < 0.6 or len(both) < min(2, len(aw)):
            return 0, [], {}
        name = 50 * j
    if (PROPS & set(words(e["title"]))) and not (PROPS & set(words(a["title"]))):
        return 0, [], {}                                        # totals/spreads are a different market
    an, en = numbers(a["title"]), numbers(e["title"])
    if an and en and an != en:
        return 0, [], {}                                        # different line or threshold
    omap = {l: map_outcome(l, e["outcomes"]) for l in a["outcomes"]}
    lead = lead_of(a["outcomes"])
    s = name + (20 if omap.get(lead) is not None else 0)
    hours = abs(a["end"] - e["end"]) / 3600 if a["end"] and e["end"] else 9999
    away = max(0.0, (a["end"] - n.timestamp()) / 3600)          # hours until the Alpha market ends
    s += 20 if hours <= max(12, away * 0.03) else 10 if hours <= max(36, away * 0.06) else 0
    s += 10 if all(v is not None for v in omap.values()) else 0
    flags = []
    if hours > max(12, away * 0.03):
        flags.append("end dates differ by %s" % ("%dh" % hours if hours < 72 else "%d days" % (hours / 24)))
    if any(l.lower() == "draw" for l in a["outcomes"]) and not omap.get("Draw") and not omap.get("draw"):
        flags.append("draw handled differently")
    ra, re_ = a["rules"].lower(), e["rules"].lower()
    if ("regulation" in ra) != ("regulation" in re_) or ("overtime" in ra) != ("overtime" in re_):
        flags.append("check overtime / extra-time rules")
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
        if a["end"] and e["end"] and abs(a["end"] - e["end"]) > max(4 * 86400, away * 0.15):
            continue
        s, fl, om = score(a, e)
        if s > best[0]:
            best = (s, fl, om, e)
    return best


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
    idxs = {k: build_index(v) for k, v in sites.items()}
    try:
        fix = json.load(open("match_fixes.json"))      # {"block": [["alpha id", "other url"], ...]}
    except Exception:
        fix = {}
    blocked = {tuple(x) for x in fix.get("block", [])}

    out = []
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
            if not e or s < 70 or (a["id"], e["url"]) in blocked:
                continue
            row["sites"][name] = {"url": e["url"], "title": e["title"], "score": s, "flags": fl,
                                  "label": "SAME" if s >= 90 else "SIMILAR",
                                  "volume": round(e["volume"]), "volume24h": round(e["volume24h"])}
            row["sites"][name]["matched_outcome"] = om.get(lead)
            # this site's price for every Alpha outcome it lines up with
            row["sites"][name]["outcomes"] = {l: e["outcomes"][k] for l, k in om.items() if k is not None}
            row["prices"][name] = e["outcomes"][om[lead]] if om.get(lead) is not None else None
            row["score"] = min(row["score"], s)
            row["flags"] += [x for x in fl if x not in row["flags"]]
        if len(row["sites"]) < 2:
            continue
        row["label"] = "SAME" if row["score"] >= 90 else "SIMILAR"
        ps = [v for v in row["prices"].values() if v is not None]
        row["gap"] = round(max(ps) - min(ps), 1) if len(ps) > 1 and row["label"] == "SAME" else None
        out.append(row)

    out.sort(key=lambda r: (r["label"] != "SAME", -(r["gap"] or 0)))
    json.dump({"updated": n.strftime(f), "note": NOTE, "matches": out}, open("matches.json", "w"), indent=1)
    same = sum(r["label"] == "SAME" for r in out)
    print("Matcher: %d matched (%d SAME, %d SIMILAR)" % (len(out), same, len(out) - same))
    for r in out[:30]:
        p = r["prices"]
        print("  %-7s %3d | %s | %s | A %s P %s K %s | gap %s | A vol $%s %s" % (
            r["label"], r["score"], r["title"][:48], r["outcome"][:22], p.get("alpha"),
            p.get("polymarket", "-"), p.get("kalshi", "-"), r["gap"], r["sites"]["alpha"]["volume"],
            "; ".join(r["flags"])))
        for site in ("polymarket", "kalshi"):          # what it matched, so we can check it
            x = r["sites"].get(site)
            if x:
                print("        %s %d: %s -> %s" % (site[0].upper(), x["score"], x["title"][:60], x["matched_outcome"]))


if __name__ == "__main__":
    main()
