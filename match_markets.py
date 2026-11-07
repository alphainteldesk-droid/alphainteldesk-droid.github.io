# Alpha Intel Desk: cross-site matching engine (v1).
# For every priced Alpha Arcade market closing in the next 14 days, find the same event on
# Polymarket and Kalshi, line up the outcomes, and score how sure we are they're the same market.
#   SAME (90+)     same event, same outcome, end times line up  -> used for Gap Radar math
#   SIMILAR (70-89) probably the same event, something differs   -> shown with a badge, never gap math
#   below 70        hidden
# Writes matches.json. Public market data only.
import json, re, time, unicodedata, urllib.request
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher

NOTE = "Matches are automatic. Always check each site's rules before you trade."
DAYS = 14
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
esports bo1 bo3 bo5 2025 2026 2027 2028 jan feb mar apr may jun jul aug sep oct nov dec""".split())
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
padres:san diego diamondbacks:arizona rockies:colorado mammoth:utah"""
ALIAS = {}
for pair in re.findall(r"([a-z0-9]+(?: sox| jays)?):([a-z ]+?)(?= [a-z0-9]+(?: sox| jays)?:|$)", TEAMS.replace("\n", " ")):
    ALIAS[pair[0]] = pair[1].split()


def words(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = s.replace("&", " and ")
    return [w for w in re.findall(r"[a-z0-9]+", s)]


def key_words(s):
    return [w for w in words(s) if w not in STOP and not w.isdigit()]


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
def load_alpha():
    b = json.load(open("alpha_live.json"))
    out = []
    for m in b["markets"]:
        end = ts(m.get("endTs"))
        if not (n.timestamp() < end <= n.timestamp() + DAYS * 86400):
            continue
        opts = m.get("options") or []
        if len(opts) == 1 or all((o.get("label") or "").lower() in ("yes", "no") for o in opts):
            yes = next((o for o in opts if (o.get("label") or "").lower() == "yes"), opts[0] if opts else {})
            sd = sides(m.get("title"))
            label = re.sub(r"(?i)^the\s+", "", sd[0]) if sd else "Yes"
            outs = {label: (yes.get("yesProb") or 0) / 1e4}
        else:
            outs = {o.get("label") or "?": (o.get("yesProb") or 0) / 1e4 for o in opts}
        if not any(outs.values()):
            continue
        out.append({"id": m.get("id"), "title": m.get("title") or "", "end": end, "outcomes": outs,
                    "rules": m.get("rules") or "", "fee": m.get("feeBasePercent"),
                    "url": "https://www.alphaarcade.com/market/" + (m.get("slug") or "")})
    return out


def load_poly():
    """Polymarket events closing within DAYS days, grouped by event, outcomes -> price (0-100)."""
    ms = []
    for page in range(20):
        d = get("https://gamma-api.polymarket.com/markets?active=true&closed=false&limit=500"
                f"&offset={page * 500}&end_date_min=" + n.strftime(f) +
                "&end_date_max=" + (n + timedelta(days=DAYS + 1)).strftime(f))
        ms += d
        if len(d) < 500:
            break
    evs = {}
    for m in ms:
        if "Up or Down" in (m.get("question") or ""):
            continue
        ev = (m.get("events") or [{}])[0]
        k = ev.get("slug") or m.get("slug")
        e = evs.setdefault(k, {"title": ev.get("title") or m.get("question") or "", "outcomes": {},
                               "text": "", "end": ts(m.get("gameStartTime") or m.get("endDate")),
                               "rules": m.get("description") or "",
                               "url": "https://polymarket.com/event/" + (k or "")})
        try:
            names = json.loads(m.get("outcomes") or "[]")
            prices = [float(p) for p in json.loads(m.get("outcomePrices") or "[]")]
        except (ValueError, TypeError):
            continue
        q = m.get("question") or ""
        e["text"] += " " + q
        if [x.lower() for x in names] == ["yes", "no"] and prices:
            label = m.get("groupItemTitle") or q
            e["outcomes"][label] = round(prices[0] * 100, 1)
            e.setdefault("questions", {})[label] = q
        else:
            for nm, p in zip(names, prices):
                e["outcomes"][nm] = round(p * 100, 1)
                e.setdefault("questions", {})[nm] = q
    return list(evs.values())


def load_kalshi():
    """Kalshi events closing within DAYS days; each market in an event is one outcome."""
    t = int(time.time())
    ms, cur = [], ""
    for _ in range(15):
        d = get("https://api.elections.kalshi.com/trade-api/v2/markets?status=open&mve_filter=exclude"
                f"&limit=1000&min_close_ts={t}&max_close_ts={t + (DAYS + 1) * 86400}&cursor={cur}")
        ms += d["markets"]
        cur = d.get("cursor") or ""
        if not cur:
            break
    evs = {}
    for m in ms:
        k = m["event_ticker"]
        e = evs.setdefault(k, {"title": m.get("title") or "", "outcomes": {}, "text": "",
                               "end": ts(m.get("expected_expiration_time") or m.get("close_time")),
                               "rules": m.get("rules_primary") or "",
                               "url": "https://kalshi.com/markets/" + k.split("-")[0].lower()})
        bid = float(m.get("yes_bid_dollars") or 0)
        ask = float(m.get("yes_ask_dollars") or 0)
        last = float(m.get("last_price_dollars") or 0)
        p = (bid + ask) / 2 if bid > 0 and ask > 0 else last
        label = m.get("yes_sub_title") or m.get("subtitle") or m.get("title") or ""
        e["outcomes"][label] = round(p * 100, 1)
        e["text"] += " " + (m.get("title") or "") + " " + label
    return list(evs.values())


# ---------------- matching ----------------
def map_outcome(label, outs):
    """Which outcome on the other site is the same as this Alpha outcome?"""
    if label.lower() in ("draw", "tie"):
        for k in outs:
            if k.lower() in ("draw", "tie") or "draw" in words(k) or "tie" in words(k):
                return k
        return None
    best, bs = None, (0.0, 0)
    for k in outs:
        kw = words(k)
        if k.lower() in ("yes", "no") or "draw" in kw or "tie" in kw:
            continue
        s = (covers(label, key_words(k)), -len(kw))          # best match, then shortest label
        if s > bs:
            best, bs = k, s
    return best if bs[0] >= 0.5 else None


def score(a, e):
    """(score 0-100, flags, outcome map) for Alpha market a vs other-site event e."""
    sd = sides(a["title"])
    text = key_words(e["title"] + " " + e["text"])
    if sd:
        c = [covers(s, text) for s in sd]
        if min(c) < 0.5:
            return 0, [], {}
        name = 50 * (c[0] + c[1]) / 2
    else:
        aw, ew = set(key_words(a["title"])), set(key_words(e["title"]))
        if not aw or not ew:
            return 0, [], {}
        j = len(aw & ew) / len(aw | ew)
        if j < 0.5:
            return 0, [], {}
        name = 50 * j
    if (PROPS & set(words(e["title"]))) and not (PROPS & set(words(a["title"]))):
        return 0, [], {}                                        # totals/spreads are a different market
    an, en = numbers(a["title"]), numbers(e["title"])
    if an and en and an != en:
        return 0, [], {}                                        # different line or threshold
    omap = {l: map_outcome(l, e["outcomes"]) for l in a["outcomes"]}
    lead = max(a["outcomes"], key=a["outcomes"].get)
    s = name + (20 if omap.get(lead) else 0)
    hours = abs(a["end"] - e["end"]) / 3600 if a["end"] and e["end"] else 99
    s += 20 if hours <= 12 else 10 if hours <= 36 else 0
    s += 10 if all(omap.values()) else 0
    flags = []
    if hours > 12:
        flags.append("end times differ by %dh" % hours)
    if any(l.lower() == "draw" for l in a["outcomes"]) and not omap.get("Draw") and not omap.get("draw"):
        flags.append("draw handled differently")
    ra, re_ = a["rules"].lower(), e["rules"].lower()
    if ("regulation" in ra) != ("regulation" in re_) or ("overtime" in ra) != ("overtime" in re_):
        flags.append("check overtime / extra-time rules")
    return min(100, round(s)), flags, omap


def best_match(a, events):
    best = (0, [], {}, None)
    for e in events:
        if a["end"] and e["end"] and abs(a["end"] - e["end"]) > 4 * 86400:
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
    print("Matcher: %d Alpha Arcade markets (next %d days) | %d Polymarket events | %d Kalshi events"
          % (len(alpha), DAYS, len(sites["polymarket"]), len(sites["kalshi"])))
    try:
        fix = json.load(open("match_fixes.json"))      # {"block": [["alpha id", "other url"], ...]}
    except Exception:
        fix = {}
    blocked = {tuple(x) for x in fix.get("block", [])}

    out = []
    for a in alpha:
        row = {"title": a["title"], "close": datetime.fromtimestamp(a["end"], timezone.utc).strftime(f),
               "sites": {"alpha": {"url": a["url"], "outcomes": a["outcomes"]}}, "flags": [], "score": 100}
        lead = max(a["outcomes"], key=a["outcomes"].get)
        row["outcome"] = lead
        row["prices"] = {"alpha": round(a["outcomes"][lead], 1)}
        for name, evs in sites.items():
            s, fl, om, e = best_match(a, evs)
            if not e or s < 70 or (a["id"], e["url"]) in blocked:
                continue
            row["sites"][name] = {"url": e["url"], "title": e["title"], "score": s, "flags": fl,
                                  "label": "SAME" if s >= 90 else "SIMILAR"}
            if om.get(lead) is not None:
                row["prices"][name] = e["outcomes"][om[lead]]
            row["score"] = min(row["score"], s)
            row["flags"] += [x for x in fl if x not in row["flags"]]
        if len(row["sites"]) < 2:
            continue
        row["label"] = "SAME" if row["score"] >= 90 else "SIMILAR"
        ps = list(row["prices"].values())
        row["gap"] = round(max(ps) - min(ps), 1) if len(ps) > 1 and row["label"] == "SAME" else None
        out.append(row)

    out.sort(key=lambda r: (r["label"] != "SAME", -(r["gap"] or 0)))
    json.dump({"updated": n.strftime(f), "note": NOTE, "matches": out}, open("matches.json", "w"), indent=1)
    same = sum(r["label"] == "SAME" for r in out)
    print("Matcher: %d matched (%d SAME, %d SIMILAR)" % (len(out), same, len(out) - same))
    for r in out[:20]:
        p = r["prices"]
        print("  %-7s %3d | %s | %s | A %s P %s K %s | gap %s %s" % (
            r["label"], r["score"], r["title"][:48], r["outcome"][:22], p.get("alpha"),
            p.get("polymarket", "-"), p.get("kalshi", "-"), r["gap"], "; ".join(r["flags"])))


if __name__ == "__main__":
    main()
