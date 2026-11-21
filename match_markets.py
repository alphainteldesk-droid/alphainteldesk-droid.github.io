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
# v8 (Nov 12): stricter everywhere: titles naming different months/years/quarters never match (Gap Scanner,
#     Momentum Scanner cross-check, Polymarket-Kalshi pairs, Calendar); calendar markets must settle with the event.
# Writes matches.json. Public market data only.
import json, re, time, unicodedata, urllib.parse, urllib.request
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher

NOTE = "Matches are automatic. Always check each site's rules before you trade."
MAX_PAGES_KALSHI = 150   # Kalshi events, 200 per page
n = datetime.now(timezone.utc)
f = "%Y-%m-%dT%H:%M:%SZ"



def kalshi_end_picker(mk):
    """Nov 15: Kalshi sometimes stamps every rung of a deadline ladder with the FIRST rung's
    expected_expiration_time (KXALIENS: 'Before Jan 20, 2029' said Jan 1, 2027), while close_time is right.
    If 2+ markets in an event share one expected time but have different close times, use the later close_time."""
    by = {}
    for m in mk:
        by.setdefault(m.get("expected_expiration_time"), set()).add(m.get("close_time"))
    def pick(m):
        exp, close = m.get("expected_expiration_time"), m.get("close_time")
        if exp and close and len(by.get(exp, ())) > 1 and ts(close) > ts(exp):
            return close
        return exp or close
    return pick

def get(url):
    """GET JSON. If a site says "too many requests" (HTTP 429), wait and try again (up to 4 tries) - Nov 10."""
    import time, urllib.error
    for attempt in range(4):
        req = urllib.request.Request(url, headers={"User-Agent": "AlphaIntelDesk/1.0", "Accept": "application/json"})
        try:
            return json.load(urllib.request.urlopen(req, timeout=30))
        except urllib.error.HTTPError as err:
            if err.code != 429 or attempt == 3:
                raise
            wait = float(err.headers.get("Retry-After") or 0) or 2 * (attempt + 1)
            print("Matcher: HTTP 429 (too many requests), waiting %.0fs and retrying" % min(wait, 20))
            time.sleep(min(wait, 20))


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
    s = re.sub(r"(?i)\((?:h\.?\s?r\.?|s\.?|h\.?\s?j\.?\s?res\.?)\s?\d+\)", " ", s or "")   # Nov 14: "(H.R.3633)" is a bill number
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
            apps = {label: yes.get("marketAppId") or m.get("marketAppId")}
        else:
            outs = {o.get("label") or "?": price(o.get("yesProb")) for o in opts}
            apps = {o.get("label") or "?": o.get("marketAppId") for o in opts}
            live = {k: v for k, v in outs.items()
                    if (label_date(k, end) or end) >= n.timestamp() - 2 * 86400}   # drop deadlines already passed
            outs = live or outs
        out.append({"id": m.get("id"), "title": m.get("title") or "", "end": end, "outcomes": outs,
                    "volume": vol, "volume24h": float(m.get("twentyFourHrVolume") or 0),
                    "categories": (m.get("primaryCategories") or []) + (m.get("categories") or []),
                    "rules": m.get("rules") or "", "fee": m.get("feeBasePercent"),
                    "apps": apps,     # Nov 15: Algorand app id per outcome (the track record reads the result on-chain)
                    "url": "https://www.alphaarcade.com/market/" + (m.get("slug") or "")})
    return out


def load_poly():
    """All open Polymarket events, outcomes -> price (0-100)."""
    # Polymarket won't page past ~2,000 results, so ask for one end-date window at a time
    # Nov 12: smaller windows past 2 weeks - Polymarket's /markets list stops paging at ~2,100 per window
    edges = [n + timedelta(days=d) for d in list(range(0, 15)) +
             [18, 22, 26, 30, 37, 45, 52, 60, 75, 90, 105, 120, 150, 180, 240, 300, 400, 550, 800, 2000]]
    seen, evs, byk, merged = set(), [], {}, 0
    for lo, hi in zip(edges, edges[1:]):
        try:                                       # Nov 12: shared helper (keyset list, old list as backup)
            import polyapi
            d = polyapi.events({"end_date_min": lo.strftime(f), "end_date_max": hi.strftime(f)})
        except Exception as err:
            print("Matcher: Polymarket window", lo.strftime("%b %d"), "failed -", err)
            continue
        for ev in d:
            k = ev.get("id") or ev.get("slug")
            if k not in seen:
                seen.add(k); evs.append(ev); byk[k] = ev
            else:                                  # Nov 14: same event again in a later window = its later deadlines.
                old = byk[k]                       # Before, only the first window's markets were kept, so "by...?" events lost most outcomes
                got = {m.get("id") or m.get("slug") or m.get("question") for m in old.get("markets") or []}
                add = [m for m in ev.get("markets") or [] if (m.get("id") or m.get("slug") or m.get("question")) not in got]
                if add:
                    old["markets"] = (old.get("markets") or []) + add
                    merged += len(add)
    print("Matcher: Polymarket deadline ladders: %d later-deadline markets joined to their events" % merged)
    out = []
    for ev in evs:
        e = poly_event(ev)
        if e:
            out.append(e)
    return out


def poly_fee(m):
    """Nov 15: the fee Polymarket publishes for this market: (rate, exponent), fee per $1 = rate * (p(1-p))^exponent.
    (0, 1) when fees are off; None when the market doesn't say (then we fall back to the category estimate)."""
    if m.get("feesEnabled") is False:
        return (0.0, 1)
    fs = m.get("feeSchedule") or {}
    try:
        return (float(fs["rate"]), float(fs.get("exponent") or 1))
    except (KeyError, TypeError, ValueError):
        return None


def poly_event(ev):
    """One Polymarket event -> our shape (None if it has no live prices). Used for the full list AND for
    the Alpha-first lookups (Nov 14), so every rule here applies to both."""
    if True:
        if "Up or Down" in (ev.get("title") or ""):
            return None
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
                if bb is not None and ba is not None:  # Nov 14: bid/ask width in cents (wide = the midpoint isn't a real price)
                    e.setdefault("spr", {})[lbl] = round((float(ba) - float(bb)) * 100, 1)
                    e.setdefault("ba", {})[lbl] = (round(float(bb) * 100, 1), round(float(ba) * 100, 1))
                try:                                   # Yes token id: lets make_gaps.py read the order book (fillable size)
                    e.setdefault("book", {})[lbl] = json.loads(m.get("clobTokenIds") or "[]")[0]
                except (ValueError, TypeError, IndexError):
                    pass
                e.setdefault("ends", {})[lbl] = ts(m.get("endDate"))
                e.setdefault("qs", {})[lbl] = q
                if poly_fee(m) is not None:            # Nov 15: the market's own fee, not our category guess
                    e.setdefault("fr", {})[lbl] = poly_fee(m)
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
        return e if e["outcomes"] else None


ALPHA_FIRST_MAX = 90      # lookups per run (busiest Alpha markets first)
ALPHA_FIRST_SECS = 240    # and never more than 4 minutes of a run


def alpha_first(alpha, poly):
    """Nov 14: Alpha Arcade is our edge, so no Alpha market should miss its Polymarket twin just because
    Polymarket's big list is cut short. For every Alpha market with no good match in the list we loaded,
    ask Polymarket for that one market (search by title, then by link name). Anything found is ADDED TO THE
    SAME POOL the matcher uses, so it is scored, graded and filtered exactly like every other event."""
    import polyapi
    idx = build_index(poly)
    have = {e["url"] for e in poly}
    pos = {e["url"]: i for i, e in enumerate(poly)}
    fuller = 0
    todo = sorted([a for a in alpha if best_match(a, poly, idx, loose=True)[0] < 70], key=lambda a: -a["volume"])
    t0, added, tried, fails = time.time(), 0, 0, 0
    for a in todo[:ALPHA_FIRST_MAX]:
        if time.time() - t0 > ALPHA_FIRST_SECS or fails >= 6:
            break
        tried += 1
        raw, how = [], "search"
        try:
            raw = polyapi.search(re.sub(r"[^\w$%&' -]+", " ", a["title"]).strip())
        except Exception as err:
            fails += 1
            how = "search failed (%s)" % str(err)[:40]
        if not any(ev.get("markets") for ev in raw):
            try:
                raw = polyapi.by_slug(a["url"].rsplit("/", 1)[-1])
                how += " > link name"
            except Exception as err:
                how += " > link name failed (%s)" % str(err)[:40]
        best, seen = (0, None), []
        for ev in raw:
            try:
                e = poly_event(ev)
            except Exception:
                e = None
            if e and len(seen) < 3:
                seen.append("%s [%s%s]" % (e["title"][:38], why(a, e), " had" if e["url"] in have else ""))
            if e and e["url"] in pos and len(e["outcomes"]) > len(poly[pos[e["url"]]]["outcomes"]):
                poly[pos[e["url"]]] = e                # the pool's copy was cut short by Polymarket's list limit
                fuller += 1
            if not e or e["url"] in have:
                continue
            sc = score(a, e)[0]
            if sc > best[0] or best[1] is None:
                best = (sc, e)
            if sc >= 70:
                have.add(e["url"])
                poly.append(e)
                added += 1
        print("  ALPHA-FIRST %3d | %s | %s | P: %s" % (best[0], a["title"][:44], how, " || ".join(seen) or "-"))
    print("Alpha-first: %d Alpha markets had no Polymarket match in the main list, looked up %d, added %d Polymarket events, completed %d cut-short ones (%.0fs)"
          % (len(todo), tried, added, fuller, time.time() - t0))


def kalshi_fees():
    """Nov 15: Kalshi's fee multiplier for every series (one call). Taker fee per $1 = 0.07 * multiplier * p(1-p);
    almost all are 1, a few are 0.5 or 0 (no fee). {} if the call fails (then 0.07 for everything, as before)."""
    try:
        d = get("https://api.elections.kalshi.com/trade-api/v2/series?limit=1000")
        out = {x["ticker"]: float(x.get("fee_multiplier") if x.get("fee_multiplier") is not None else 1)
               for x in d.get("series") or [] if x.get("ticker")}
        print("Kalshi fees: %d series, %d with a lower fee" % (len(out), sum(1 for v in out.values() if v < 1)))
        return out
    except Exception as err:
        print("Kalshi fees: series list failed -", err)
        return {}


def load_kalshi():
    """All open Kalshi events; each market in an event is one outcome."""
    fees = kalshi_fees()
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
        if ev.get("series_ticker") in fees:             # Nov 15: the series' own fee (multiplier x 7%)
            e["fr_all"] = (0.07 * fees[ev["series_ticker"]], 1)
        kend = kalshi_end_picker(ev.get("markets") or [])
        for m in ev.get("markets") or []:
            if m.get("status") not in (None, "active", "open"):
                continue
            bid = float(m.get("yes_bid_dollars") or 0)
            ask = float(m.get("yes_ask_dollars") or 0)
            last = float(m.get("last_price_dollars") or 0)
            p = (bid + ask) / 2 if bid > 0 and ask > 0 else last
            label = m.get("yes_sub_title") or m.get("subtitle") or m.get("title") or ev.get("title") or "Yes"
            e["outcomes"][label] = round(p * 100, 1) if p > 0 else None
            if bid > 0 and ask > 0:
                e.setdefault("spr", {})[label] = round((ask - bid) * 100, 1)
                e.setdefault("ba", {})[label] = (round(bid * 100, 1), round(ask * 100, 1))
            if m.get("ticker"):
                e.setdefault("book", {})[label] = m["ticker"]       # for the order book (fillable size)
            e.setdefault("ends", {})[label] = ts(kend(m))
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
            e["end"] = e["end"] or ts(kend(m))
            if not e["rules"]:                 # Nov 12: primary + secondary rules (secondary often names the source)
                e["rules"] = ((m.get("rules_primary") or "") + " " + (m.get("rules_secondary") or "")).strip()
        srcs = [x.get("name") or x.get("url") or "" for x in (ev.get("settlement_sources") or []) if isinstance(x, dict)]
        if srcs:                                # Kalshi's own list of settlement sources, when the event has one
            e["rules"] += " Resolution source: " + ", ".join(srcs) + "."
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


# ---------------- period check (Nov 12: stricter matching, used everywhere) ----------------
# Two titles that name different months, years or quarters are different markets
# ("Fed decision in December" is not "Fed decision in January"; "CPI in October" is not "CPI in November").
# Month and year words are ignored by key_words(), so this check keeps them from slipping through.
_MON = {"january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3, "april": 4, "apr": 4, "may": 5,
        "june": 6, "jun": 6, "july": 7, "jul": 7, "august": 8, "aug": 8, "september": 9, "sept": 9, "sep": 9,
        "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12}
_MON_RX = re.compile(r"(?<![a-z0-9-])(" + "|".join(sorted(_MON, key=len, reverse=True)) + r")(?![a-z-])\.?(\s*\d)?")


def periods(title):
    """(months, years, quarters) named in a title. 'Before Jan 1, 2027' counts as December 2026, 'Before 2027' as 2026;
    'May' only counts as a month when a number follows it (it is also an ordinary word)."""
    t = " " + (title or "").lower().replace(",", " ") + " "
    t = re.sub(r"before\s+jan(?:uary)?\.?\s+1(?:st)?\s+(20\d\d)", lambda m: "dec 31 %d" % (int(m.group(1)) - 1), t)
    t = re.sub(r"before\s+(20\d\d)", lambda m: "by %d" % (int(m.group(1)) - 1), t)
    months = {_MON[m.group(1)] for m in _MON_RX.finditer(t) if m.group(1) != "may" or m.group(2)}
    years = set(re.findall(r"(?<![0-9])(20\d\d)(?![0-9])", t))
    quarters = set(re.findall(r"(?<![a-z0-9])q([1-4])(?![0-9])", t))
    return months, years, quarters


def period_clash(t1, t2):
    """True when both titles name a month (or year, or quarter) and they don't share one."""
    a, b = periods(t1), periods(t2)
    return any(x and y and not (x & y) for x, y in zip(a, b))


_NEG = re.compile(r"\b(no|not|none|never|nobody|neither|without)\b")


def negated(label):
    """Nov 19: True for outcome names that say something does NOT happen ("No solution by ...", "Not before 2027").
    A plain "No" side is handled separately."""
    t = (label or "").lower().strip()
    return t != "no" and bool(_NEG.search(t))


def by_date_label(label, outs, ends, a_end=0):
    """Alpha option 'December 31' -> the other site's market for the same deadline."""
    d = label_date(label, a_end or None)
    if d is None:
        return None
    # Nov 19: "No solution by Dec 31, 2027" is the opposite of "Before 2028" - the dates match, the sides don't
    real = [k for k in outs if k.lower() != "no" and negated(k) == negated(label)]
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
        if negated(k) != negated(label):
            continue                                   # Nov 19: "No one" is not "Someone"
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
    ("Census Bureau", "gov", r"census bureau"), ("Congress", "gov", r"congress\.gov|clerk of the house|senate\.gov|library of congress|resolution source: (?:the )?us senate"),
    ("Federal Register", "gov", r"federal register"), ("NOAA / NWS", "gov", r"\bnoaa\b|national weather service"),
    ("Binance", "crypto", r"binance"), ("Coinbase", "crypto", r"coinbase"), ("CoinGecko", "crypto", r"coingecko"),
    ("CoinMarketCap", "crypto", r"coinmarketcap"), ("Kraken", "crypto", r"kraken"), ("Chainlink", "crypto", r"chainlink"),
    ("Pyth", "crypto", r"\bpyth\b"), ("Yahoo Finance", "data", r"yahoo finance"),
    ("Nasdaq Private Market", "data", r"nasdaq private market"), ("Challenger", "data", r"challenger, gray"),
    ("Box Office Mojo", "data", r"box office mojo"), ("The Numbers", "data", r"the-numbers|the numbers\b"),
    ("Billboard", "data", r"billboard"), ("Spotify", "data", r"spotify"), ("Google Trends", "data", r"google trends"),
    ("Christie's", "data", r"christie"), ("Sotheby's", "data", r"sotheby"), ("Wikipedia", "data", r"wikipedia"),
    # Nov 14 (from fine_watch.json, the wording both sites actually use):
    ("ESPN", "sports", r"\bespn\b"), ("DAZN", "sports", r"\bdazn\b"), ("Tapology", "sports", r"tapology"),
    ("CF Benchmarks", "crypto", r"cf benchmarks|\bbrti\b"),
    ("Rotten Tomatoes", "data", r"rotten tomatoes"), ("Recording Academy", "data", r"recording academy"),
    ("Academy (AMPAS)", "data", r"academy of motion picture|\bampas\b"), ("CMA Awards", "data", r"cma awards|country music association"),
    ("IMF PortWatch", "data", r"portwatch"), ("French Constitutional Council", "gov", r"conseil constitutionnel|constitutional council"),
    ("World Health Organization", "gov", r"world health organization|resolution source: who\b"),
    # Nov 16 grade check (unrecognised wording in fine_watch.json; Library of Congress folded into Congress, same source):
    ("Formula 1", "sports", r"formula 1\b|\bf1\b"), ("NHL", "sports", r"\bnhl\b"), ("NFL", "sports", r"\bnfl\b"),
    ("Netflix", "data", r"(?:reported by|resolution source:) netflix"), ("Knesset", "gov", r"knesset"),
    ("Democratic Party", "gov", r"official democratic party|resolution source: democratic party|democratic national committee"),
    ("Republican Party", "gov", r"official republican party|resolution source: republican party|republican national committee"),
    ("OpenAI", "data", r"resolution source: openai|official (?:information|announcements?) from openai"),
    ("Anthropic", "data", r"resolution source: anthropic|official (?:information|announcements?) from anthropic"),
    ("SpaceX", "data", r"resolution source: spacex|official (?:information|announcements?) from spacex"),
    ("LMArena", "data", r"lm ?arena|resolution source for this market is the arena"),
    ("Trading Economics", "data", r"trading economics"), ("Election authority", "election", r"board of elections|electoral commission|election commission\b|clerk of the crown"),
    ("BBC", "news", r"\bbbc\b"), ("Prime Minister's Office", "gov", r"prime minister's office"),
    ("Office of the Presidency", "election", r"office of the presidency"),
    ("SEC EDGAR", "gov", r"\bedgar\b|securities and exchange commission"),
    ("Smithsonian GVP", "data", r"smithsonian|global volcanism"), ("CME Group", "data", r"\bcme\b"),
    ("Central bank", "gov", r"announced by the central bank|bank of israel|bank of england|bank of japan|bank of canada|european central bank|reserve bank of"),
    # Nov 20 grade check (unrecognised wording in fine_watch.json; election bodies get their own family):
    ("Luminate", "data", r"luminate"),
    ("Tesla", "data", r"resolution source: tesla|official (?:information|announcements?) from tesla"),
    ("National Archives", "gov", r"national archives"), ("USGS", "gov", r"\busgs\b|geological survey"),
    ("AAA", "data", r"published by aaa|gasprices\.aaa"), ("NBER", "data", r"\bnber\b|national bureau of economic research"),
    ("White House", "gov", r"resolution source: (?:the )?white house"), ("New York Times", "news", r"new york times|nytimes"),
    ("Hits Daily Double", "data", r"hits ?daily ?double"), ("Miss Universe Org", "data", r"miss universe organization"),
    ("Governing league", "sports", r"resolution source: the governing league"),
    ("Exchange listing", "data", r"official company filings|exchange.s official listing page"),
    ("Credible reporting", "news", r"consensus of credible (?:reporting|sources)"),
]
CANCEL = r"50[-/ ]?50|fifty[- ]fifty|refund|\bvoid|cancel|postpone|annul|abandon"
RANK = {"match": 0, "similar": 1, "unknown": 2, "differ": 3}


def sources_in(text):
    t = (text or "").lower()
    return {name: fam for name, fam, pat in SOURCES if _re.search(pat, t)}


# Nov 15: Danger Zone settlement line (who decides the result, clear-cut or a judgement call)
SETTLE_VAGUE = _re.compile(r"credible report|consensus of|widely reported|sole discretion|(?:its|the|our) discretion|"
                   r"in (?:its|our|the) (?:sole )?judg|reasonabl[ey] (?:determine|interpret)|spirit of", _re.I)
SETTLE_SRC = _re.compile(r"(?:primary )?resolution source (?:for this market )?(?:will be|is|shall be)\s+(?:the |an? )?([^.\n]{3,90})", _re.I)
SETTLE_KAL = _re.compile(r"Resolution source: (.+?)\.\s*$")


def _settle_row(text):
    """Cut-off rules (ending in "…") that name no source might name one further on: no grade rather than a wrong C."""
    r = settle_info(text)
    return None if r["g"] == "none" and text.rstrip().endswith(("…", "...")) else r   # Nov 17: Alpha cuts with "..."


def settle_info(text):
    """Nov 15 (James): who decides the result, and is it clear-cut? -> {"g": clear|mixed|judgement|none, "src": "..."}"""
    t = text or ""
    names = [x.strip() for x in (SETTLE_KAL.search(t).group(1).split(",") if SETTLE_KAL.search(t) else []) if x.strip()]
    if not names:                           # Kalshi lists its own; otherwise the sources we recognise in the rules
        names = [k for k in sources_in(t) if k != "Credible reporting"]
    if not names:                           # else the name after "resolution source ... will be", if it looks like a name
        m = SETTLE_SRC.search(t)
        if m:
            x = _re.sub(r"(?i)^(official (information|data|results?|announcements?) (from|of|by) (the )?)", "", m.group(1))
            x = _re.split(r",| and | or |;|\(| however| but| found at| at http| which", x)[0].strip().rstrip("…")
            if x[:1].isupper() and not _re.match(r"(?i)(a )?consensus|credible", x):
                names = [x]
    vague = bool(SETTLE_VAGUE.search(t))
    g = ("mixed" if vague else "clear") if names else ("judgement" if vague else "none")
    src = ", ".join(names[:2])
    return {"g": g, "src": src[:48] + ("…" if len(src) > 48 else "")}


import collections as _col
FINE_WATCH = {"unknown": _col.Counter(), "seen": set()}
_CUE = _re.compile(r"[^.]*\b(resolution source|resolve[sd]? (?:according to|based on|using|per)|according to|"
                   r"as reported by|reported by|settle[sd]? (?:on|using|based on)|primary source|official (?:data|results?|source|website))\b[^.]*\.", _re.I)


def _watch(text):
    """Nov 12: remember rules sentences that point at a source we don't recognise (reviewed weekly)."""
    text = _re.sub(r"\bU\.S\.", "US", text or "")       # Nov 16: "Resolution source: U.S. ..." was cut at "U."
    h = hash(text)
    if not text or h in FINE_WATCH["seen"]:
        return
    FINE_WATCH["seen"].add(h)
    for m in _CUE.finditer(text):
        sent = " ".join(m.group(0).split())[:160]
        if not sources_in(sent):
            FINE_WATCH["unknown"][sent.lower()] += 1


def fine_print(ra, rb):
    """Compare two sites' rules text: {'src': match|similar|unknown|differ, 'srcs': [...], 'void': same|check|none}."""
    a, b = sources_in(ra), sources_in(rb)
    if not a:
        _watch(ra)
    if not b:
        _watch(rb)
    both = sorted(set(a) & set(b))
    if not a or not b:
        src = "unknown"                                  # one site doesn't name a source in its rules text
    elif both:
        src = "match"
    elif (set(a.values()) | set(b.values()) <= {"news"} or set(a.values()) | set(b.values()) <= {"sports"}   # Nov 16: two sports
          or set(a.values()) | set(b.values()) <= {"news", "election"}   # Nov 20: news call vs official election body
          or "Credible reporting" in a or "Credible reporting" in b):                                   # sources = similar
        src = "similar"                                  # different news outlets calling the same result; "a consensus of
                                                         # credible reporting" (Polymarket's stock wording) never counts as a different source
    else:
        src = "differ"
    ca, cb = bool(_re.search(CANCEL, (ra or "").lower())), bool(_re.search(CANCEL, (rb or "").lower()))
    void = "same" if ca and cb else "check" if ca != cb else "none"
    out = {"src": src, "srcs": both or sorted(set(a) | set(b)), "void": void}
    if rules_twin(ra, rb) >= 0.9:                        # Nov 14: the two sites publish the same rules word for word,
        out.update(src="match", twin=True)               # so source, deadline and cancel rules are the same by definition
        out["void"] = "none" if void == "check" else void
    return out


def score(a, e):
    """(score 0-100, flags, outcome map) for Alpha market a vs other-site event e."""
    if period_clash(a["title"], e["title"]):
        return 0, [], {}                                        # Nov 12: different month / year / quarter
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
    game = sporty(e) or bool(sides(a["title"]))               # Nov 14: a sports check only; "regulation" in a bill's rules is not overtime
    if game and (("regulation" in ra) != ("regulation" in re_) or ("overtime" in ra) != ("overtime" in re_)):
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


def same_question(t1, t2):
    """True when two titles ask the same thing word for word (ignoring filler words) with the same numbers."""
    k1, k2 = set(key_words(t1)), set(key_words(t2))
    return len(k1) >= 2 and k1 == k2 and numbers(t1) == numbers(t2)


def rules_twin(r1, r2):
    """0-1: how alike the opening of two rule texts is (Alpha Arcade often copies Polymarket's rules)."""
    c = lambda t: " ".join(words(t))[:260]
    return round(SequenceMatcher(None, c(r1), c(r2)).ratio(), 2) if r1 and r2 else 0.0


LOOSE_DAYS = 135         # identical question: listed end dates may differ by up to this many days and still be scored


def best_match(a, events, idx, loose=False):
    best = (0, [], {}, None)
    away = max(0.0, a["end"] - n.timestamp())
    for e in candidates(a, events, idx):
        ends = [x for x in [e["end"]] + list((e.get("ends") or {}).values()) +
                [label_date(k) for k in list(e["outcomes"])[:40]] if x]
        gap_s = min(abs(a["end"] - x) for x in ends) if a["end"] and ends else 0
        if gap_s > max(4 * 86400, away * 0.15) and not (
                loose and gap_s <= LOOSE_DAYS * 86400 and same_question(a["title"], e["title"])):
            continue                                   # Nov 14: for Alpha rows, word-for-word the same question still gets scored
        s, fl, om = score(a, e)
        if s > best[0]:
            best = (s, fl, om, e)
    return best


def why(a, e):
    """Log helper (Nov 14): 'score / days apart / DATE-GATE' for one Alpha market against one event."""
    ends = [x for x in [e["end"]] + list((e.get("ends") or {}).values()) +
            [label_date(k) for k in list(e["outcomes"])[:40]] if x]
    away = max(0.0, a["end"] - n.timestamp())
    d = min(abs(a["end"] - x) for x in ends) if a["end"] and ends else 0
    gate = d > max(4 * 86400, away * 0.15)
    return "%d/%dd%s/twin %.2f" % (score(a, e)[0], d / 86400, "/DATE-GATE" if gate else "", rules_twin(a.get("rules"), e.get("rules")))


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
        pe = p.get("ends") or {}
        own = pe.get(lead_of(outs)) if len(p["outcomes"]) > 1 else next(iter(pe.values()), None)
        a = {"id": p["url"], "title": p["title"], "end": own or p["end"], "outcomes": outs, "rules": p["rules"]}
        s, fl, om, e = best_match(a, ks, idx)
        if (not e or s < 90) and len(p["outcomes"]) > 1:
            # Nov 14: deadline ladder where Kalshi lists fewer deadlines: try each deadline by itself, soonest first
            full = outs
            for lbl in sorted([l for l in full if full[l] is not None and pe.get(l) and label_date(l)], key=lambda l: pe[l])[:3]:
                a1 = dict(a, end=pe[lbl], outcomes={lbl: full[lbl]})
                s1, fl1, om1, e1 = best_match(a1, ks, idx)
                if e1 and s1 > s and om1.get(lbl) is not None:
                    s, fl, om, e, a, outs = s1, fl1, om1, e1, a1, a1["outcomes"]
        if not e or s < 70:
            continue
        lead = lead_of(outs)
        label = "SAME" if s >= 90 else "SIMILAR"
        fp = fine_print(p["rules"], e["rules"])
        k = {"url": e["url"], "title": e["title"], "score": s, "flags": fl, "label": label, "fine": fp,
             "volume": round(e["volume"]), "volume24h": round(e["volume24h"]), "matched_outcome": om.get(lead),
             "outcomes": {l: e["outcomes"][x] for l, x in om.items() if x is not None},
             "book": {l: (e.get("book") or {}).get(x) for l, x in om.items() if x is not None},
             "spread": {l: (e.get("spr") or {}).get(x) for l, x in om.items() if x is not None},
             "fr": site_fee(e, om.get(lead))}
        row = {"title": p["title"], "close": datetime.fromtimestamp(a["end"] or e["end"], timezone.utc).strftime(f),
               "sites": {"polymarket": {"url": p["url"], "title": p["title"], "score": s, "flags": fl, "label": label, "fine": fp,
                                        "volume": round(p["volume"]), "volume24h": round(p["volume24h"]),
                                        "matched_outcome": lead, "outcomes": outs,
                                        "spread": (p.get("spr") or {}) if len(p["outcomes"]) > 1 else
                                                  {"Yes": next(iter((p.get("spr") or {}).values()), None)},
                                        "book": {lead: (p.get("book") or {}).get(lead if len(p["outcomes"]) > 1 else next(iter(p["outcomes"])))},
                                        "fr": site_fee(p, lead if len(p["outcomes"]) > 1 else next(iter(p["outcomes"])))},
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
LADDER = re.compile(r"(?i)^\s*[↑↓▲▼⬆⬇]?\s*(above|below|over|under|between|at least|at most|more than|less than|fewer than|"
                    r"[$<>≥≤]\s*\d|\d[\d,.]*\s*(%|[kmb]\b|\+|$))")
# Nov 12: price-target markets ("What price will Bitcoin hit…", "Bitcoin above $X on…") swing all day without news
PRICE_TITLE = re.compile(r"(?i)\bwhat price will\b|\bprice (?:of|on|at)\b.*\b(?:on|at|by|end of)\b|"
                         r"\b(?:bitcoin|btc|ethereum|eth|solana|sol|xrp|doge|dogecoin|bnb|cardano|ada|algorand|algo|"
                         r"gold|silver|oil|wti|brent|s&p|nasdaq|dow|tesla|nvidia)\b.*\b(?:above|below|hit|reach|range|price)\b")
# Nov 13: "by how much" markets (margin of victory, vote-share ranges) swing between thin ranges without news
MARGIN_TITLE = re.compile(r"(?i)\bmargin\b|\bby how much\b|\bvote share\b|\bshare of the vote\b|\bpercentage of the vote\b")
MARGIN_LABEL = re.compile(r"(?i)\d+(?:\.\d+)?\s*\+?\s*(?:pts?|points?)\b|\b\d+(?:\.\d+)?\s*(?:to|-|–)\s*\d+(?:\.\d+)?\s*%")
MENTION = re.compile(r"(?i)\b(say|says|mention|mentions|tweet|tweets|post)\b|view count|top \d+ (song|album)")
MOVE_TOP, MOVE_ALPHA, MOVE_MAX_CRYPTO = 30, 4, 5   # Nov 10: 30 for the full Movers page (homepage shows 3)
NAMES = {"alpha": "Alpha Arcade", "polymarket": "Polymarket", "kalshi": "Kalshi"}


def why_link(title):
    q = " ".join(key_words(title)[:6]) or title
    return "https://news.google.com/search?" + urllib.parse.urlencode({"q": q, "hl": "en-US", "gl": "US", "ceid": "US:en"})


def alpha_trades(alpha):
    """Nov 13: remember when each Alpha Arcade market last traded (alpha_trades.json, keyed by URL).
    Traded = 24h volume above 0, or total volume went up since last run. A market seen for the first time
    with no trading today counts as last traded 24 h ago. make_gaps.py ignores Alpha prices with no trade in 48 h."""
    try:
        st = json.load(open("alpha_trades.json"))
    except Exception:
        st = {}
    now, out = n.timestamp(), {}
    for a in alpha:
        u, v = a["url"], a["volume"]
        old = st.get(u) or {}
        traded = a["volume24h"] > 0 or (old and v > old.get("vol", 0) + 0.5)
        last = now if traded else old.get("last", now - 24 * 3600)
        out[u] = {"last": round(last), "vol": round(v, 2)}
    json.dump(out, open("alpha_trades.json", "w"), separators=(",", ":"))
    stale = sum(now - x["last"] > 48 * 3600 for x in out.values())
    print("Alpha trades: %d markets, %d with no trade in 48h (their prices are left out of the Gap Scanner)" % (len(out), stale))


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


def mover_cross(out, src, alpha, sites):
    """Nov 12: for each mover, find the SAME market on the other two sites with the Gap Scanner's matcher
    (score >= 90 only, never a weak match) and record that site's price for the same outcome in r["also"]."""
    pools = {"alpha": [dict(a, text=a.get("text") or "") for a in alpha if not sporty(a)],
             "polymarket": [e for e in sites.get("polymarket", []) if not sporty(e)],
             "kalshi": [e for e in sites.get("kalshi", []) if not sporty(e)]}
    idxs = {s: build_index(p) for s, p in pools.items()}
    found = 0
    for r in out:
        e, k = src[(r["site"], r["url"])]
        outs = e["outcomes"] if len(e["outcomes"]) > 1 else {"Yes": next(iter(e["outcomes"].values()))}
        key = k if k in outs else ("Yes" if "Yes" in outs else None)
        if key is None:
            continue
        a = {"id": e["url"], "title": e["title"], "end": e["end"], "outcomes": outs, "rules": e.get("rules") or ""}
        r["also"] = {}
        for other, pool in pools.items():
            if other == r["site"] or not pool:
                continue
            s, fl, om, m = best_match(a, pool, idxs[other])
            if not m or s < 90 or om.get(key) is None:
                continue
            p = m["outcomes"].get(om[key])
            if p is not None:
                r["also"][other] = p
                r.setdefault("also_url", {})[other] = m["url"]
        found += bool(r["also"])
    print("Movers: %d of %d matched on another site (SAME, score 90+)" % (found, len(out)))


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
    best, src = {}, {}
    for site, e, k, p, c, v in rows:
        if p is None or not (5 <= p <= 95) or abs(c) < MOVE_MIN:
            continue
        if LADDER.match(k or "") or PRICE_TITLE.search(e["title"]) or MARGIN_TITLE.search(e["title"]) or \
                MARGIN_LABEL.search(k or "") or MENTION.search(e["title"]) or \
                any("mention" in (x or "").lower() for x in e.get("categories") or []):
            continue                                     # price brackets and word-mention markets swing for no news
        if k == e["title"] or len(k) > 45 or k.lower() == "yes":
            k = "Yes"                                    # one-question market: the label is the question
        key = (site, e["url"])
        if key not in best or abs(c) > abs(best[key]["change"]):
            src[key] = (e, k)
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
    try:
        mover_cross(out, src, alpha, sites)
    except Exception as err:
        print("Movers cross-site lookup failed:", err)
    json.dump({"updated": n.strftime(f), "note": "Biggest 24-hour price moves with real trading behind them. No sports. "
               "\"Why?\" opens a news search, not our analysis.", "movers": out}, open("movers.json", "w"), indent=1)
    cnt = {s_: sum(r["site"] == s_ for r in allr) for s_ in NAMES}
    print("Movers: %d shown | candidates Poly %d, Kalshi %d, Alpha %d" % (len(out), cnt["polymarket"], cnt["kalshi"], cnt["alpha"]))
    for r in out:
        print("  %+5.1f | %-11s | %s | %s | now %s | 24h vol %s" % (r["change"], r["name"], r["title"][:44], r["outcome"][:16], r["price"], r["vol24"]))


# ---------------- calendar links ----------------
CAL_SETTLE_DAYS = 14     # Nov 12: a calendar market must settle within 14 days of the event (was 45);
CAL_SETTLE_POLITICS = 30 # elections settle at certification, weeks after the vote
def calendar_links(alpha, sites):
    """For each catalysts.json event with "find" word-sets, pick each site's own market for it
    (title holds every word of a set; earlier sets win, then the market settling closest to the event date).
    Skips word-mention and combo markets. Writes cal_links.json.
    Nov 12, stricter: the market must settle within CAL_SETTLE_DAYS (politics: CAL_SETTLE_POLITICS) of the event (it has to be about this event,
    not just the same topic), and any month/year in its title must match the event's (e.g. 'CPI (Oct)')."""
    try:
        cats = json.load(open("catalysts.json"))["events"]
    except Exception as err:
        print("Calendar links: no catalysts.json -", err)
        return
    pools = {"alpha": alpha, "polymarket": sites.get("polymarket", []), "kalshi": sites.get("kalshi", [])}
    rx = lambda w: re.compile(r"(?<![a-z0-9])" + re.escape(w.lower()))
    skip = re.compile(r"\b(say|said|mention|mentions|combo|parlay|postpone[ds]?|postponement|cancel(?:s|ed|led|lation)?|"
                      r"delay(?:s|ed)?|reschedul(?:e|ed|ing))\b")   # word-mention, combo and "will it be postponed" side bets
                                                                   # aren't the event itself (postponed/cancelled added Nov 12)
    clock = re.compile(r"\b\d{1,2}(:\d\d)?\s*(am|pm)\b")   # Nov 12: "Silver at 2:30pm ET · FOMC minutes" is a price bet, not the event
    out = {}
    for c in cats:
        finds = c.get("find") or []
        try:
            when = datetime.strptime(c["date"], f).replace(tzinfo=timezone.utc).timestamp()
        except (KeyError, ValueError):
            continue
        if not finds or not (n.timestamp() - 2 * 86400 <= when <= n.timestamp() + 60 * 86400):
            continue
        days = CAL_SETTLE_POLITICS if c.get("cat") == "politics" else CAL_SETTLE_DAYS
        stop = when + days * 86400
        if c.get("end"):                                    # multi-day events (summits): count from the last day
            try:
                stop = datetime.strptime(c["end"], "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() + days * 86400
            except ValueError:
                pass
        ev_d = datetime.fromtimestamp(when, timezone.utc)
        ev_m = {ev_d.month} | periods(" ".join(re.findall(r"\(([^)]*)\)", c["name"])))[0]   # release month + the month it covers
        ev_y = {str(ev_d.year)} | ({str(ev_d.year - 1)} if ev_d.month == 1 else set())
        sets = [[rx(w) for w in s] for s in finds]
        nots = [rx(w) for w in c.get("not") or []]          # words that rule a market out for this event
        links = {}
        for site, evs in pools.items():
            hits = []
            for e in evs:
                t = (e.get("title", "") + " " + e.get("alt", "")).lower()
                if skip.search(t) or clock.search(t) or any(r.search(t) for r in nots):
                    continue
                si = next((i for i, s in enumerate(sets) if all(r.search(t) for r in s)), None)
                if si is None:
                    continue
                end = e.get("end") or 0
                if not end or end < when - 86400 or end > stop:
                    continue                                # Nov 12: must settle with the event, not weeks later
                pm, py, _ = periods(e.get("title", ""))
                if (pm and not (pm & ev_m)) or (py and not (py & ev_y)):
                    continue                                # Nov 12: names a different month or year
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


EXP_LO, EXP_HI, EXP_SPREAD, EXP_DAYS, EXP_PER_EVENT = 80, 98.5, 4, 180, 2   # Nov 15: 30 -> 180 days, 85 -> 80 cents (James: Expiry Hub)
EXP_MIN_VOL = {"polymarket": 20000, "kalshi": 5000, "alpha": 50}
EXP_SKIP = ("weather", "climate")      # daily temperature and rain brackets: hundreds of rows, little interest


def site_fee(e, label):
    """Nov 15: the fee the site itself publishes for this outcome as (rate, exponent), or None if it doesn't say."""
    return (e.get("fr") or {}).get(label) or e.get("fr_all")


def exp_fee_rate(site, e):
    """Taker fee rate r (fee per $1 contract = r * p * (1 - p)); same numbers as make_gaps.fee_rate."""
    if site == "kalshi":
        return 0.07
    if site == "alpha":
        return (e.get("fee") / 1e6) if e.get("fee") else 0.07
    cats = " ".join(e.get("categories") or []).lower()
    if "geopolitic" in cats:
        return 0.0
    if "crypto" in cats:
        return 0.07
    return 0.04 if any(k in cats for k in ("politic", "election", "tech", "finance", "business")) else 0.05


def exp_sane(rows, now):
    """Nov 15: last check before anything reaches The Danger Zone. Recompute every number from scratch and drop
    any row that doesn't add up: closed already, price outside 80-98.5, a fee that can't be right, or a return /
    per-year figure that doesn't match the price and fee. Logs what it dropped (the watchdog reads the count)."""
    good, bad = [], {}
    for x in rows:
        p = x["ask"] / 100
        why = None
        if not (EXP_LO <= x["ask"] <= EXP_HI):
            why = "price out of range"
        elif not (0 <= x["fee"] <= 100 * 0.10 * p * (1 - p) + 0.01):   # no site charges over 10% of p(1-p)
            why = "fee out of range"
        elif not (0.25 * 86400 <= datetime.strptime(x["close"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp() - now
                  <= (EXP_DAYS + 1) * 86400):
            why = "closes outside the window"
        elif abs((100 - x["ask"] - x["fee"]) / (x["ask"] + x["fee"]) * 100 - x["ret"]) > 0.02:
            why = "return doesn't add up"
        elif x["days"] >= 3 and abs(x["ret"] * 365 / x["days"] - x["apr"]) > max(2, 0.01 * x["apr"]):
            why = "per-year doesn't add up"
        elif x["side"] not in ("Yes", "No") or not x.get("url"):
            why = "missing side or link"
        if why:
            bad[why] = bad.get(why, 0) + 1
        else:
            good.append(x)
    if bad:
        print("Expiry returns: sanity check dropped %s" % bad)
    return good, bad


def expiry_returns(alpha, sites):
    """Nov 14: Expiry Returns (expiry.json). Contracts you can buy today at 80-98.5 cents (85 until Nov 15) that settle within 180 days (30 until Nov 15):
    what you make after the fee IF it resolves that way (it pays $1), and the same figure per year (simple, not
    compounded). Uses the real ASK for Yes and 100 minus the real BID for No, never the midpoint; bid and ask must
    be within 4 cents. Alpha Arcade has no bid/ask in our feed, so its rows use the last price, are marked "est",
    and need a trade in the last 5 days (James, Nov 14: 5 days until Alpha Arcade has more volume; the Gap Scanner
    keeps its own 48 h rule). No sports."""
    now = n.timestamp()
    iso = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        tr = json.load(open("alpha_trades.json"))
        live = {u for u, x in tr.items() if now - x.get("last", 0) <= 5 * 86400}
    except Exception:
        live = None
    rows = []

    def add(site, e, label, side, ask, end, est):
        """fee per contract = rate * (p(1-p))^exponent; the site's own published rate when it gives one."""
        days = (end - now) / 86400
        if not (EXP_LO <= ask <= EXP_HI) or not (0.25 <= days <= EXP_DAYS):
            return None
        own = site_fee(e, label) if site != "alpha" else None
        r, ex = own or (exp_fee_rate(site, e), 1)
        fee = 100 * r * ((ask / 100) * (1 - ask / 100)) ** ex
        cost = ask + fee
        ret = (100 - cost) / cost * 100
        if ret < 0.3:
            return None
        return {"site": site, "title": e["title"], "outcome": label, "side": side, "ask": round(ask, 1),
                "fee": round(fee, 2), "ret": round(ret, 2), "apr": round(ret * 365 / days), "close": iso(end),
                "days": round(days, 2), "volume": round(e.get("volume") or 0), "url": e["url"], "est": est,
                "cat": next((c for c in e.get("categories") or [] if c), ""),
                "fs": "site" if own or site == "alpha" else "est", "fr": round(r, 4),
                "id": (e.get("book") or {}).get(label) if site != "alpha" else (e.get("apps") or {}).get(label),
                "q": (e.get("qs") or {}).get(label) or "",
                "st": _settle_row(e.get("rules") or "")}   # Alpha: needs the full rules from the Courier (300-char cut removed Nov 15)   # Nov 15 (James): the site's full question for this contract, shown in plain words   # Nov 15: Kalshi ticker / Polymarket Yes token, for the track record   # where the fee came from (watchdog counts the estimates)

    for site in ("polymarket", "kalshi"):
        for e in sites.get(site) or []:
            if (e.get("volume") or 0) < EXP_MIN_VOL[site] or sporty(e) \
                    or any(k in " ".join(e.get("categories") or []).lower() for k in EXP_SKIP):
                continue
            got = []
            for label, (bid, ask) in (e.get("ba") or {}).items():
                if ask - bid > EXP_SPREAD or bid <= 0:
                    continue
                end = (e.get("ends") or {}).get(label) or e["end"]
                for side, px in (("Yes", ask), ("No", 100 - bid)):
                    row = add(site, e, label, side, px, end, False)
                    if row:
                        got.append(row)
            rows += sorted(got, key=lambda x: -x["ret"])[:EXP_PER_EVENT]
    for a in alpha:
        if a["volume"] < EXP_MIN_VOL["alpha"] or sporty(a) or (live is not None and a["url"] not in live):
            continue
        got = []
        for label, p in a["outcomes"].items():
            if p is None:
                continue
            end = (label_date(label, a["end"]) if len(a["outcomes"]) > 1 else None) or a["end"]
            for side, px in (("Yes", p), ("No", 100 - p)):
                row = add("alpha", a, label, side, px, end, True)
                if row:
                    got.append(row)
        rows += sorted(got, key=lambda x: -x["ret"])[:EXP_PER_EVENT]
    rows, bad = exp_sane(rows, now)
    total, keep = len(rows), []
    for lo, hi in ((0, 3), (3, 7), (7, 31), (31, 91), (91, EXP_DAYS + 1)):   # the busiest 150 in each window, so every filter on the page has rows
        keep += sorted([x for x in rows if lo <= x["days"] < hi], key=lambda x: (x["site"] != "alpha", -x["volume"]))[:150]
    rows = sorted(keep, key=lambda x: x["days"])
    fees = {}
    for x in rows:                                     # which fee rates were used: the watchdog alerts James when a new one shows up
        k = x["site"] + (" est" if x["fs"] == "est" else "")
        fees.setdefault(k, {})
        fees[k][str(x["fr"])] = fees[k].get(str(x["fr"]), 0) + 1
    json.dump({"updated": iso(now), "total": total, "dropped": bad, "fees": fees, "rows": rows},
              open("expiry.json", "w"), separators=(",", ":"))
    from collections import Counter
    print("Expiry returns: %d contracts at %s-%s cents settling within %d days %s"
          % (len(rows), EXP_LO, EXP_HI, EXP_DAYS, dict(Counter(x["site"] for x in rows))))


def main():
    alpha = load_alpha()
    sites = {}
    for name, fn in (("polymarket", load_poly), ("kalshi", load_kalshi)):
        try:
            sites[name] = fn()
        except Exception as err:
            print("Matcher:", name, "failed:", err)
            sites[name] = []
    try:
        if sites["polymarket"]:
            alpha_first(alpha, sites["polymarket"])
    except Exception as err:
        print("Alpha-first lookup failed:", err)
    print("Matcher: %d Alpha Arcade markets | %d Polymarket events | %d Kalshi events"
          % (len(alpha), len(sites["polymarket"]), len(sites["kalshi"])))
    try:
        try:
            alpha_trades(alpha)
        except Exception as err:
            print("Alpha trade tracker failed:", err)
        movers(alpha, sites)
    except Exception as err:
        print("Movers failed:", err)
    try:
        calendar_links(alpha, sites)
    except Exception as err:
        print("Calendar links failed:", err)
    try:
        expiry_returns(alpha, sites)
    except Exception as err:
        print("Expiry returns failed:", err)
    idxs = {k: build_index(v) for k, v in sites.items()}
    try:
        fix = json.load(open("match_fixes.json"))      # {"block": [["alpha id", "other url"], ...]}
    except Exception:
        fix = {}
    blocked = {tuple(x) for x in fix.get("block", [])}

    out, near, twins = [], [], []
    for a in alpha:
        row = {"title": a["title"], "close": datetime.fromtimestamp(a["end"], timezone.utc).strftime(f),
               "sites": {"alpha": {"url": a["url"], "outcomes": a["outcomes"], "volume": round(a["volume"]),
                                   "volume24h": round(a["volume24h"]), "fee": a["fee"],
                                   "apps": a.get("apps") or {}}},     # Nov 21: app id per outcome (Gap Scanner reads the real book)
               "flags": [], "score": 100, "categories": a["categories"]}
        lead = lead_of(a["outcomes"])
        row["outcome"] = lead
        row["prices"] = {"alpha": a["outcomes"][lead]}
        for name, evs in sites.items():
            s, fl, om, e = best_match(a, evs, idxs[name], loose=True)
            if name == "polymarket" and e and s >= 70 and any("end dates differ" in x for x in fl) \
                    and same_question(a["title"], e["title"]) and rules_twin(a["rules"], e["rules"]) >= 0.9:
                mo = om.get(lead)                      # Nov 14: same question AND the same rules text = the same contract;
                e_end = (label_date(mo) if mo else None) or (e.get("ends") or {}).get(mo) or e["end"]
                if e_end:                              # only the listed end date differs, so line this row up on Polymarket's date
                    a = dict(a, end=e_end)
                    s, fl, om = score(a, e)
                    twins.append("%s (twin %.2f -> %d)" % (a["title"][:40], rules_twin(a["rules"], e["rules"]), s))
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
            row["sites"][name]["fr"] = site_fee(e, om.get(lead))
            # this site's price for every Alpha outcome it lines up with
            row["sites"][name]["outcomes"] = {l: e["outcomes"][k] for l, k in om.items() if k is not None}
            row["sites"][name]["book"] = {l: (e.get("book") or {}).get(k) for l, k in om.items() if k is not None}
            row["sites"][name]["spread"] = {l: (e.get("spr") or {}).get(k) for l, k in om.items() if k is not None}
            row["prices"][name] = e["outcomes"][om[lead]] if om.get(lead) is not None else None
            row["score"] = min(row["score"], s)
            row["flags"] += [x for x in fl if x not in row["flags"]]
        if len(row["sites"]) < 2:
            continue
        row["label"] = "SAME" if row["score"] >= 90 else "SIMILAR"
        ps = [v for v in row["prices"].values() if v is not None]
        row["gap"] = round(max(ps) - min(ps), 1) if len(ps) > 1 and row["label"] == "SAME" else None
        out.append(row)

    print("Matcher: %d Alpha markets share Polymarket's rules word for word (end date taken from Polymarket): %s"
          % (len(twins), " | ".join(twins)))
    print("Matcher: %d busy non-sports Alpha markets with no Kalshi match (best try shown):" % len(near))
    for t, sc, kt, mo in near[:20]:
        print("  NEAR %3d | %s | K: %s -> %s" % (sc, t[:44], kt[:48], mo))
    try:                                           # Nov 14: for the busiest Alpha markets with no Kalshi match,
        kw = {}                                        # list what Kalshi DOES have on the rarest word in the title
        for ev in sites["kalshi"]:
            for w in set(key_words(ev["title"] + " " + (ev.get("alt") or ""))):
                kw.setdefault(w, []).append(ev["title"])
        miss = sorted([r for r in out if "kalshi" not in r["sites"]], key=lambda r: -r["sites"]["alpha"]["volume"])
        solo = sorted([a for a in alpha if a["url"] not in {r["sites"]["alpha"]["url"] for r in out} and not sporty(a)],
                      key=lambda a: -a["volume"])
        for t in [r["title"] for r in miss[:30]] + [a["title"] for a in solo[:15]]:
            ws = sorted([w for w in set(key_words(t)) if w in kw and w not in SCOPE], key=lambda w: len(kw[w]))
            if not ws:
                print("  KALSHI-HAS nothing | %s" % t[:50])
                continue
            w = ws[0]
            a0 = next(x for x in alpha if x["title"] == t)
            aw = set(key_words(t))
            top = sorted([ev for ev in sites["kalshi"] if w in key_words(ev["title"] + " " + (ev.get("alt") or ""))],
                         key=lambda ev: -len(aw & set(key_words(ev["title"]))))[:4]
            print("  KALSHI-HAS '%s' x%d | %s | %s" % (w, len(kw[w]), t[:44],
                                                    " || ".join("%s [%s]" % (ev["title"][:52], why(a0, ev)) for ev in top)))
    except Exception as err:
        print("Kalshi subject check failed:", err)
    used = {r["sites"]["polymarket"]["url"] for r in out if "polymarket" in r["sites"]
            and r["sites"]["polymarket"]["label"] == "SAME"}   # Nov 14: a SIMILAR Alpha row must not hide a SAME Polymarket-Kalshi pair
    pk = poly_kalshi(sites["polymarket"], sites["kalshi"], used)
    print("Matcher: %d Polymarket-Kalshi pairs (%d SAME)" % (len(pk), sum(r["label"] == "SAME" for r in pk)))
    for r in sorted(pk, key=lambda r: -r["score"])[:25]:
        x = r["sites"]["kalshi"]
        print("  PK %-7s %3d | %s | %s | P %s K %s | K: %s -> %s" % (
            r["label"], r["score"], r["title"][:44], r["outcome"][:18], r["prices"]["polymarket"],
            r["prices"]["kalshi"], x["title"][:44], x["matched_outcome"]))
    out += pk

    out.sort(key=lambda r: (r["label"] != "SAME", -(r["gap"] or 0)))
    json.dump({"updated": n.strftime(f), "note": NOTE, "matches": out,
               "counts": {"alpha": len(alpha), "polymarket": len(sites["polymarket"]), "kalshi": len(sites["kalshi"]),
                          "matched": len(out), "poly_kalshi": len(pk)}},
              open("matches.json", "w"), indent=1)        # counts: read by watchdog.py (Nov 12)
    same = sum(r["label"] == "SAME" for r in out)
    print("Matcher: %d matched (%d SAME, %d SIMILAR)" % (len(out), same, len(out) - same))
    try:
        import collections
        c = collections.Counter(x.get("fine", {}).get("src") for r in out + pk for nm, x in r["sites"].items() if nm != "alpha")
        print("FINE sources:", dict(c))
        for r in (out + pk)[:400]:
            for nm, x in r["sites"].items():
                fp = x.get("fine")
                if fp and fp["src"] in ("differ", "similar") and x.get("label") == "SAME":
                    print("  FINE %-7s %-10s | %s | %s" % (fp["src"], nm, r["title"][:50], ", ".join(fp["srcs"][:5])))
        drops = [{"title": r["title"][:80], "site": nm, "srcs": x["fine"]["srcs"][:5]}
                 for r in out + pk for nm, x in r["sites"].items()
                 if (x.get("fine") or {}).get("src") == "differ"][:60]
        json.dump({"updated": n.strftime(f), "counts": dict(c), "differ": drops,
                   "unknown_wording": FINE_WATCH["unknown"].most_common(60)},
                  open("fine_watch.json", "w"), indent=1)
        print("FINE watch: %d unrecognised source phrases, %d 'differ' pairs -> fine_watch.json"
              % (len(FINE_WATCH["unknown"]), len(drops)))
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
