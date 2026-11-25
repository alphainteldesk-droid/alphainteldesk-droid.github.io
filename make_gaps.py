# Alpha Intel Desk: Gap Scanner + Catalyst Calendar data.
# Reads matches.json (from match_markets.py) and catalysts.json (hand-kept list of scheduled events).
# Writes gaps.json  (price gaps after estimated fees, no sports, strict filters: all-3-site gaps first, then top 10 two-site)
#    and calendar.json (next scheduled catalysts + big non-sports markets resolving soon).
# Wording rule: "price gap after fees" - never "guaranteed" or "arbitrage", no trade instructions.
import json
import re
from datetime import datetime, timezone, timedelta

f = "%Y-%m-%dT%H:%M:%SZ"
n = datetime.now(timezone.utc)
NOTE = ("Matches are automatic. Always check each site's rules before you trade. "
        "Fees are estimates; prices are midpoints and don't include the bid/ask spread.")

# ---------- filters (tune here) ----------
MIN_PRICE, MAX_PRICE = 3, 97          # skip near-certain outcomes: tiny prices are noisy
MAX_RAW_GAP = 35                      # bigger usually means a stale or mismatched market
FLIP_GAP, FLIP_SUM = 20, 6            # Nov 19: a 20¢+ gap whose two prices add up to 94-106 is a Yes/No flip
LONGSHOT = 10                         # if the lower price is under 10 cents...
MAX_RATIO = 3                         # ...the higher one can't be more than 3x it (thin/stale book)
MIN_NET_GAP = 1.0                     # points left after estimated fees
MIN_VOLUME = {"alpha": 50, "polymarket": 5000, "kalshi": 500}   # $ / $ / contracts traded
MAX_SPREAD = 10                       # Nov 14: cents between best bid and ask; wider = the midpoint is not a price anyone can trade
MIN_HOURS_LEFT = 2                    # markets about to close move too fast to compare
TOP = 10
MIN_ALPHA_ROWS = 4                    # Alpha Arcade is our edge: keep at least this many Alpha rows in the top 10
# James, Nov 8: gaps priced on ALL THREE sites come first (tagged all3); two-site gaps fill in after them,
# so the homepage box is always full and the full page shows "On all 3 sites" then "More price gaps (2 sites)".

SPORT_TAGS = ("sport", "esports", "soccer", "football", "nfl", "nba", "mls", "nhl", "mlb", "ufc",
              "tennis", "f1", "golf", "league", "copa", "serie", "efl", "counter-strike")
NAMES = {"alpha": "Alpha Arcade", "polymarket": "Polymarket", "kalshi": "Kalshi"}


def is_sports(cats):
    return any(any(t in (c or "").lower() for t in SPORT_TAGS) for c in cats)


def fee_rate(site, row):
    """Taker fee rate r; fee per $1 contract = r * p * (1 - p).
    Nov 15: the fee the site publishes for this market comes first (matches.json "fr" = [rate, exponent]);
    the estimates below are only the fallback. All published exponents are 1 today; fee_pts() warns if not."""
    own = (row["sites"].get(site) or {}).get("fr")
    if own:
        if float(own[1]) != 1:
            print("Fees: %s publishes exponent %s on %s - using the rate with exponent 1" % (site, own[1], row.get("title", "")[:40]))
        return float(own[0])
    if site == "kalshi":
        return 0.07
    if site == "alpha":
        fb = row["sites"]["alpha"].get("fee")
        return (fb / 1e6) if fb else 0.07          # feeBasePercent 70000 -> 0.07 (estimate)
    cats = " ".join(row.get("categories") or []).lower()  # Polymarket fees from Nov 20, 2026: 0.01 or 0.05 by category
    if "geopolitic" in cats:
        return 0.0
    if "combo" in cats or "parlay" in cats:
        return 0.05
    if "crypto" in cats:                           # BTC 5/15-min up/down 0.05, all other crypto 0.01
        t = row.get("title", "").lower()
        return 0.05 if "up or down" in t and any(k in t for k in ("5 min", "15 min", "5m", "15m")) else 0.01
    if any(k in cats for k in ("sport", "election", "primar")):
        return 0.05
    if any(k in cats for k in ("politic", "econom", "culture", "weather", "mention")):
        return 0.01
    return 0.05                                    # finance, tech, other/general


def fee_pts(r, price_pct):
    p = price_pct / 100
    return 100 * r * p * (1 - p)


RANK = {"match": 0, "similar": 1, "unknown": 2, "differ": 3}


def fine_grade(row, lo, hi):
    """Fine-print checks for the two sites in a gap (Nov 10). Grade A = sources named on both and the same,
    cancel rules consistent; B = passed every check we can run, but read the rules (source not named / differs in outlet)."""
    fps = [row["sites"][x].get("fine") for x in (lo, hi) if x != "alpha" and row["sites"][x].get("fine")]
    if not fps:
        return None, None
    src = max((f["src"] for f in fps), key=RANK.get)
    srcs = sorted({n for f in fps for n in f["srcs"]})
    void = "check" if any(f["void"] == "check" for f in fps) else "same" if all(f["void"] == "same" for f in fps) else "none"
    grade = "A" if src == "match" and void != "check" else "B"
    fine = {"src": src, "srcs": srcs[:4], "void": void}
    if fps and all(f.get("twin") for f in fps):
        fine["twin"] = True                             # Nov 14: same rules text on both sites
    return grade, fine


def fair_price(row, ps):
    """Fair price estimate (Nov 10): each site's price weighted by dollars traded there.
    Kalshi volume is in contracts, so it's converted at that price. Deep markets count more."""
    w = {}
    for site, p in ps.items():
        v = row["sites"][site].get("volume") or 0
        w[site] = v * p / 100 if site == "kalshi" else v
    tot = sum(w.values())
    return round(sum(ps[x] * w[x] for x in ps) / tot, 1) if tot > 0 else None


COMBO = re.compile(r"\s&\s|\bparlay\b|\bcombo\b", re.I)      # Nov 13: two events in one question


def alpha_traded_48h():
    """URLs of Alpha Arcade markets that traded in the last 48 h (from alpha_trades.json); None if no record yet."""
    try:
        st = json.load(open("alpha_trades.json"))
    except Exception:
        return None
    now = n.timestamp()
    return {u for u, x in st.items() if now - x.get("last", 0) <= 48 * 3600}


def brackets_ok(row):
    """Nov 13: if the two sites disagree by more than 40¢ on ANY outcome of the same market, the outcomes were
    paired wrong (e.g. Picasso: Polymarket "<$40m" 8.6¢ vs Kalshi 87.5¢ - Kalshi uses "above $X" thresholds),
    so the pair isn't the same contract and none of its gaps are real."""
    sites = [x.get("outcomes") or {} for x in row["sites"].values()]
    for i, a in enumerate(sites):
        for b in sites[i + 1:]:
            for o, p in a.items():
                q = b.get(o)
                if p is not None and q is not None and abs(p - q) > 40:
                    return False
    return True


LEAN_MIN, LEAN_SHARE, LEAN_CENTS = 4, 0.75, 5


def lean_ok(row):
    """Nov 14: two sites that list the same names but one is higher on nearly all of them (4+ shared outcomes,
    75%+ leaning the same way, typical difference 5 cents or more) are not pricing the same contract: the rules or
    the deadline differ across the whole event, or one market is too new to have real prices. None of its gaps count.
    (e.g. "Who will leave Trump Administration before 2028?": Kalshi higher on 9 of 10 names, by 10 cents typically)"""
    sites = [x.get("outcomes") or {} for x in row["sites"].values()]
    for i, a in enumerate(sites):
        for b in sites[i + 1:]:
            d = sorted(b[o] - p for o, p in a.items() if p is not None and b.get(o) is not None)
            if len(d) < LEAN_MIN:
                continue
            one_way = max(sum(x >= 2 for x in d), sum(x <= -2 for x in d)) / len(d)
            mid = (d[len(d) // 2] + d[(len(d) - 1) // 2]) / 2
            if one_way >= LEAN_SHARE and abs(mid) >= LEAN_CENTS:
                return False
    return True


_BOOKS = {}
ALPHA_RESERVED_MIN = 2.0               # Nov 21 (James): an Alpha gap only gets the reserved spot at 2c+ after fees
MIN_BOOK_USD = 10                      # Nov 21: Alpha book price must have at least $10 of orders behind it


def alpha_book_mid(alpha, outcome):
    """Nov 21 (James: the same Alpha gap sat on the board for days): Alpha's feed price can stay frozen even
    after trades, so check it against the real on-chain order book (fillable._alpha, as the Danger Zone does).
    -> midpoint of the best Yes bid and ask with $10+ behind each, in cents; False = no buyer or no seller, or wider than
    MAX_SPREAD (no real price); None = book could not be read (keep the feed price)."""
    app = (alpha.get("apps") or {}).get(outcome)
    if not app:
        return None
    if app not in _BOOKS:
        try:
            from fillable import _alpha
            _BOOKS[app] = _alpha(app)
        except Exception as err:
            print("  Alpha book read failed | %s | %s" % (outcome[:30], err))
            _BOOKS[app] = None
    b = _BOOKS[app]
    if b is None:
        return None
    def level(orders):                              # first price with $10+ behind it (a $1 order is not a price)
        tot = 0.0
        for px, q in orders:
            tot += px * q
            if tot >= MIN_BOOK_USD:
                return 100 * px
        return None
    bid, ask = level(b["yes"]), level(b["ask_yes"])
    if bid is None or ask is None:
        return False
    if ask - bid > MAX_SPREAD or ask < bid:
        return False
    return round((bid + ask) / 2, 1)


def gaps(matches, alpha_fresh):
    out = []
    live = alpha_traded_48h()
    skipped = {"combo": 0, "alpha_idle": 0, "brackets": 0, "wide": 0, "lean": 0, "flip": 0, "alpha_book": 0}
    for row in matches:
        if is_sports(row.get("categories") or []):
            continue
        if COMBO.search(row.get("title") or ""):
            skipped["combo"] += 1
            continue
        if not brackets_ok(row):
            skipped["brackets"] += 1
            continue
        if not lean_ok(row):
            skipped["lean"] += 1
            continue
        try:
            left = (datetime.strptime(row["close"], f).replace(tzinfo=timezone.utc) - n).total_seconds() / 3600
        except (KeyError, ValueError):
            continue
        if left < MIN_HOURS_LEFT:
            continue
        # every site's price for every outcome: {outcome: {site: price}}
        table = {}
        for site, x in row["sites"].items():
            if site == "alpha" and not alpha_fresh:
                continue
            if site == "alpha" and live is not None and x.get("url") not in live:
                skipped["alpha_idle"] += 1
                continue                               # Nov 13: no trade in 48 h, its price is stale
            if site != "alpha" and (x.get("label") != "SAME" or x.get("flags")):
                continue                               # each site's match must be SAME with no warnings
            if (x.get("volume") or 0) < MIN_VOLUME[site]:
                continue
            for o, p in (x.get("outcomes") or {}).items():
                sp = (x.get("spread") or {}).get(o)
                if sp is not None and sp > MAX_SPREAD:
                    skipped["wide"] += 1
                    continue                           # Nov 14: bid and ask too far apart to trust the midpoint
                if p is not None and MIN_PRICE <= p <= MAX_PRICE:
                    table.setdefault(o, {})[site] = p
        for o, ps in table.items():                     # Nov 21: Alpha price = real order book midpoint
            if "alpha" in ps and len(ps) >= 2:
                q = alpha_book_mid(row["sites"]["alpha"], o)
                if q is False:
                    del ps["alpha"]
                    skipped["alpha_book"] += 1
                    print("  Alpha no real book | %s | %s (feed %s)" % (row["title"][:40], o[:20], ps.get("alpha")))
                elif q is not None:
                    if abs(q - ps["alpha"]) >= 2:
                        print("  Alpha book mid %s vs feed %s | %s | %s" % (q, ps["alpha"], row["title"][:40], o[:20]))
                    ps["alpha"] = q
        best = None
        for o, ps in table.items():
            if len(ps) < 2:
                continue
            lo = min(ps, key=ps.get)
            hi = max(ps, key=ps.get)
            raw = ps[hi] - ps[lo]
            if raw > MAX_RAW_GAP:
                continue
            if raw >= FLIP_GAP and abs(ps[lo] + ps[hi] - 100) <= FLIP_SUM:
                skipped["flip"] += 1
                continue                               # Nov 19: big gap but the prices add to ~100 = opposite sides
            if ps[lo] < LONGSHOT and ps[hi] > MAX_RATIO * ps[lo]:
                continue                               # long shot on one site, not on the other: thin book
            f_lo, f_hi = fee_pts(fee_rate(lo, row), ps[lo]), fee_pts(fee_rate(hi, row), ps[hi])
            fees = f_lo + f_hi
            net = raw - fees
            three = len(ps) == 3
            if net >= MIN_NET_GAP and (best is None or (three, net) > (best["all3"], best["net"])):
                best = {"title": row["title"], "outcome": o, "close": row["close"],
                        "prices": {s: ps.get(s) for s in ("polymarket", "kalshi", "alpha")},
                        "low": {"site": lo, "name": NAMES[lo], "price": ps[lo], "url": row["sites"][lo]["url"]},
                        "high": {"site": hi, "name": NAMES[hi], "price": ps[hi], "url": row["sites"][hi]["url"]},
                        "urls": {s: x["url"] for s, x in row["sites"].items()},
                        "volumes": {s: x.get("volume") for s, x in row["sites"].items()},
                        "volumes24": {s: x.get("volume24h") for s, x in row["sites"].items()},
                        "raw": round(raw, 1), "fees": round(fees, 1), "net": round(net, 1), "all3": three,
                        "fee_low": round(f_lo, 2), "fee_high": round(f_hi, 2),
                        "fair": fair_price(row, ps),
                        "grade": fine_grade(row, lo, hi)[0], "fine": fine_grade(row, lo, hi)[1],
                        "rate_low": fee_rate(lo, row), "rate_high": fee_rate(hi, row),
                        "category": (row.get("categories") or ["Other"])[0]}
        if best:
            out.append(best)
    print("Gaps: left out %d combo markets, %d bracket mismatches, %d idle Alpha Arcade prices (no trade in 48h), "
          "%d prices with a bid/ask wider than %d cents, %d events where one site is higher on nearly every outcome"
          % (skipped["combo"], skipped["brackets"], skipped["alpha_idle"], skipped["wide"], MAX_SPREAD, skipped["lean"]))
    print("Gaps: left out %d Alpha Arcade prices with no real buyer/seller within %d cents (on-chain book)"
          % (skipped["alpha_book"], MAX_SPREAD))
    print("Gaps: left out %d likely Yes/No flips (gap %d¢+, prices add to ~100)" % (skipped["flip"], FLIP_GAP))
    out.sort(key=lambda g: -g["net"])
    three = [g for g in out if g["all3"]]              # every all-three-sites gap, always shown first
    rest = [g for g in out if not g["all3"]]
    has_a = [g for g in rest if g["prices"].get("alpha") is not None]
    keep = [g for g in has_a if g["net"] >= ALPHA_RESERVED_MIN][:MIN_ALPHA_ROWS]   # Nov 21 (James): reserved spot needs 2c+
    keep += [g for g in rest if g not in keep][:TOP - len(keep)]
    keep.sort(key=lambda g: -g["net"])
    return three + keep


def history_dates():
    """Anniversaries and past black swans from warroom_config.json (the same dates the War Room scores), placed
    on their next date in the calendar window as all-day HISTORY events."""
    try:
        cfg = json.load(open("warroom_config.json"))
    except Exception:
        return []
    NAMES = {"gulf": "Iran & the Gulf", "levant": "Israel, Gaza & Lebanon", "redsea": "Red Sea & Yemen", "ukraine": "Ukraine & Russia",
             "taiwan": "Taiwan Strait", "korea": "Korean Peninsula", "southasia": "India & Pakistan", "caribbean": "Venezuela & the Caribbean"}
    rows = [(x["md"], "Anniversary: " + x["what"], hid, "Anniversary in the Situation Room's %s region. Dates like this can bring "
             "protests, speeches, drills or attacks; the Situation Room adds a little heat to the region around it." % NAMES.get(hid, hid), 1)
            for hid, xs in (cfg.get("dates") or {}).items() for x in xs]
    rows += [(x["md"], "Black swan on this date, %s: %s" % (x["year"], x["what"]), x.get("hotspot"),
              "A past market or world shock on this date. History doesn't repeat on schedule, but traders remember."
              + (" Counts toward the Situation Room's %s score." % NAMES.get(x["hotspot"], x["hotspot"]) if x.get("hotspot") else ""), 2)
             for x in cfg.get("black_swans") or []]
    out = []
    for md, name, hid, note, imp in rows:
        mo, dd = map(int, md.split("-"))
        for y in (n.year, n.year + 1):
            try:
                when = datetime(y, mo, dd, 5, tzinfo=timezone.utc)          # midnight US Eastern
            except ValueError:
                continue
            if n - timedelta(hours=19) <= when <= n + timedelta(days=45):
                out.append({"date": when.strftime(f), "name": name, "source": "", "kind": "scheduled", "cat": "history",
                            "note": note, "end": None, "allday": True, "est": False, "impact": imp, "links": None, "market": None})
    return out


def calendar(matches):
    """Scheduled catalysts (catalysts.json) + big non-sports markets resolving in the next 14 days."""
    try:
        cats = json.load(open("catalysts.json"))["events"]
    except Exception as err:
        print("Calendar: no catalysts.json -", err)
        cats = []
    pool = [m for m in matches if not is_sports(m.get("categories") or [])]
    try:                                             # each site's own market per event (match_markets.py)
        direct = json.load(open("cal_links.json"))["links"]
    except Exception:
        direct = {}

    def market_card(m):
        ps = {s: m["prices"].get(s) for s in ("polymarket", "kalshi", "alpha")}
        live = [v for v in ps.values() if v is not None]
        return {"title": m["title"], "outcome": m["outcome"], "prices": ps,
                "urls": {s: x["url"] for s, x in m["sites"].items()}, "label": m.get("label"),
                "coiled": bool(live) and any(40 <= v <= 60 for v in live)}

    items = []
    for c in cats:
        try:
            when = datetime.strptime(c["date"], f).replace(tzinfo=timezone.utc)
        except (KeyError, ValueError):
            continue
        try:
            last = datetime.strptime(c["end"] + "T23:59:59Z", f).replace(tzinfo=timezone.utc) if c.get("end") else when
        except ValueError:
            last = when
        if c.get("allday"):
            last = max(last, when + timedelta(hours=14))   # all-day events stay up for the rest of that day
        if not (last >= n - timedelta(hours=2) and when <= n + timedelta(days=45)):
            continue
        keys = [k.lower() for k in c.get("keys", [])]
        linked = [m for m in pool if any(k in m["title"].lower() for k in keys)]
        def near(m):                                 # markets that settle near the event first, then by volume
            try:
                d = abs((datetime.strptime(m["close"], f).replace(tzinfo=timezone.utc) - when).days)
            except (KeyError, ValueError):
                d = 999
            return (d > 10, -len(m["sites"]), -sum((x.get("volume") or 0) for s, x in m["sites"].items() if s != "kalshi"))
        linked.sort(key=near)
        items.append({"date": c["date"], "name": c["name"], "source": c.get("source", ""), "kind": "scheduled",
                      "cat": c.get("cat", "econ"), "note": c.get("note", ""), "end": c.get("end"),
                      "allday": bool(c.get("allday")), "est": bool(c.get("est")), "impact": int(c.get("impact", 1)),
                      "links": direct.get(c["date"] + "|" + c["name"]),
                      "market": None if direct.get(c["date"] + "|" + c["name"]) else (market_card(linked[0]) if linked else None)})
    items += history_dates()                         # Nov 24 (James): every War Room date + black swan on the calendar
    res = []
    for m in pool:                                   # markets that resolve in the next 2 weeks, on 2+ sites
        try:
            when = datetime.strptime(m["close"], f).replace(tzinfo=timezone.utc)
        except (KeyError, ValueError):
            continue
        if any(k in " ".join(m.get("categories") or []).lower()
               for k in ("entertain", "culture", "pop", "music", "movie", "film", "tv", "netflix", "celebr", "award")):
            continue                                 # chart/awards markets aren't market-moving events
        live = [v for v in m["prices"].values() if v is not None]
        if not any(8 <= v <= 92 for v in live):
            continue                                 # already decided (99c): not worth a calendar slot
        if n <= when <= n + timedelta(days=14) and len(m["sites"]) >= 2:
            vol = sum((x.get("volume") or 0) for s, x in m["sites"].items() if s != "kalshi")
            res.append((vol, {"date": m["close"], "name": "Resolves: " + m["title"], "kind": "resolves",
                              "cat": "resolves", "impact": 1, "market": market_card(m)}))
    res.sort(key=lambda r: -r[0])
    items += [r[1] for r in res[:20]]                # the 20 busiest settling markets
    items.sort(key=lambda i: i["date"])
    return items


def add_also(matches):
    """For each mover, the matched market's price on the other two sites (same outcome), from matches.json."""
    mv = json.load(open("movers.json"))
    found = 0
    for x in mv.get("movers", []):
        if x.get("also"):                              # Nov 12: matcher already found it (mover_cross)
            found += 1
            continue
        x["also"] = {}
        for row in matches:
            me = row["sites"].get(x["site"])
            if not me or me.get("url") != x["url"]:
                continue
            outs = me.get("outcomes") or {}
            if x["site"] == "alpha":
                key = x["outcome"] if x["outcome"] in outs else None
            else:                                      # other sites: find the Alpha-side label with this price
                key = next((l for l, p in outs.items() if p is not None and abs(p - x["price"]) < 0.05), None)
            if key is None and x["outcome"] == "Yes" and len(outs) == 1:
                key = next(iter(outs))
            if key is None:
                continue
            for s, other in row["sites"].items():
                if s != x["site"] and other.get("label", "SAME") == "SAME" and (other.get("outcomes") or {}).get(key) is not None:
                    x["also"][s] = other["outcomes"][key]
            if x["also"]:
                found += 1
                break
    json.dump(mv, open("movers.json", "w"), indent=1)
    print("Movers: %d of %d also priced on another site" % (found, len(mv.get("movers", []))))


DEADLINE_Q = re.compile(r"\bby\b|\bbefore\b|\buntil\b|\bthrough\b|\bin 20\d\d\b|\bthis (year|month|week)\b|\.\.\.", re.I)


def rule_risk(matches):
    """Nov 14: Rule Risk (rules.json). One row per matched pair of sites with plain badges for what the two sets of
    rules agree and disagree on. Everything comes from checks the matcher already runs (flags, fine print, the
    scanner's own leave-out rules); nothing here is a new judgement.
    level: differ = the rules are known to differ, check = something could not be confirmed, clear = they line up."""
    rows = []
    for row in matches:
        if is_sports(row.get("categories") or []):
            continue
        sites = row["sites"]
        pairs = [("alpha", s) for s in ("polymarket", "kalshi") if s in sites] if "alpha" in sites else [("polymarket", "kalshi")]
        lined_up = brackets_ok(row) and lean_ok(row)
        for a, b in pairs:
            x = sites[b]
            fine = x.get("fine") or {}
            bad, warn, ok = [], [], []
            for fl in x.get("flags") or []:
                if fl.startswith("end dates differ"):
                    apart = re.sub(r"(\d)h$", r"\1 hours", fl[len("end dates differ by"):])
                    if fine.get("twin") or not DEADLINE_Q.search((row.get("title") or "") + " " + (row.get("outcome") or "")):
                        # the event decides the answer (an election, a nomination), or the rules are word for word the
                        # same: the date each site lists for closing is housekeeping, not a different contract
                        warn.append(["LISTED END DATES DIFFER", "the sites list closing dates" + apart +
                                     " apart; the event decides the answer, so check each site's cutoff"])
                    else:
                        bad.append(["DEADLINE MISMATCH", "the two sites list end dates" + apart + " apart"])
                elif fl.startswith("resolution sources differ"):
                    bad.append(["SOURCE DIFFERS", fl.replace("resolution sources differ", "they settle from different sources")])
                elif "draw" in fl or "overtime" in fl:
                    bad.append(["TIE RULE DIFFERS", fl])
                else:
                    bad.append(["RULES DIFFER", fl])
            if COMBO.search(row.get("title") or ""):
                bad.append(["COMBO MARKET", "two events in one question rarely mean the same thing on two sites"])
            if not lined_up:
                bad.append(["PRICES DON'T LINE UP", "the two sites disagree across the whole event, which points to different rules"])
            if fine.get("twin"):
                ok.append(["IDENTICAL RULES", "both sites publish the same rules, word for word"])
            elif fine.get("src") == "match":
                ok.append(["SAME SOURCE", ", ".join((fine.get("srcs") or [])[:3]) + " on both"])
            elif fine.get("src") == "differ" and not any(t[0] == "SOURCE DIFFERS" for t in bad):
                bad.append(["SOURCE DIFFERS", ", ".join((fine.get("srcs") or [])[:4])])
            elif fine.get("src") == "similar":
                warn.append(["DIFFERENT OUTLETS", "both use news reports, but not the same ones: " + ", ".join((fine.get("srcs") or [])[:4])])
            elif not fine.get("twin"):
                warn.append(["SOURCE NOT NAMED", "at least one site doesn't say who decides the answer"])
            if fine.get("void") == "check" and not fine.get("twin"):
                warn.append(["CANCEL RULE ON ONE SITE", "only one site says what happens if the event is cancelled"])
            if not bad and not warn and not ok:
                continue
            o = row.get("outcome") or ""
            pa, pb = (sites[a].get("outcomes") or {}).get(o), (x.get("outcomes") or {}).get(o)
            if pa is None and len(sites[a].get("outcomes") or {}) == 1:
                pa = next(iter(sites[a]["outcomes"].values()))
            rows.append({"title": row["title"], "outcome": o, "close": row.get("close"), "a": a, "b": b,
                         "urls": [sites[a]["url"], x["url"]], "prices": [pa, pb],
                         "level": "differ" if bad else "check" if warn else "clear",
                         "bad": bad, "warn": warn, "ok": ok,
                         "volume": round(max(x.get("volume") or 0, sites[a].get("volume") or 0))})
    order = {"differ": 0, "check": 1, "clear": 2}
    rows.sort(key=lambda r: (order[r["level"]], -r["volume"]))
    counts = {k: sum(r["level"] == k for r in rows) for k in order}
    json.dump({"updated": n.strftime(f), "counts": counts, "rows": rows}, open("rules.json", "w"), separators=(",", ":"))
    print("Rule risk: %d pairs | rules differ %d, check %d, clear %d" % (len(rows), counts["differ"], counts["check"], counts["clear"]))


def main():
    try:
        mj = json.load(open("matches.json"))
    except Exception as err:
        print("Gaps: no matches.json -", err)
        return
    try:
        a_up = datetime.strptime(json.load(open("alpha_live.json"))["updated"], f).replace(tzinfo=timezone.utc)
        alpha_fresh = (n - a_up).total_seconds() < 3 * 3600
    except Exception:
        alpha_fresh = False
    g = gaps(mj["matches"], alpha_fresh)
    try:
        rule_risk(mj["matches"])
    except Exception as err:
        print("Rule risk failed:", err)
    try:                                               # Nov 10: Movers page - same market's price on the other sites
        add_also(mj["matches"])
    except Exception as err:
        print("Movers cross-check failed:", err)
    try:                                               # Nov 10: fillable size from live order books (phase 1, logs first)
        from fillable import add_fillable
        add_fillable(g, mj["matches"])
        # Nov 12: gaps the order books show can't be traded right now ($0 at real prices) drop to the bottom
        g.sort(key=lambda x: (not x.get("all3"), bool(x.get("fill")) and not x["fill"].get("usd")))
    except Exception as err:
        print("Fillable step failed:", err)
    try:                                             # price change per site since the last update (shown as ▲ / ▼)
        old = {(o["title"], o["outcome"]): o["prices"] for o in json.load(open("gaps.json")).get("gaps", [])}
    except Exception:
        old = {}
    for x in g:
        was = old.get((x["title"], x["outcome"])) or {}
        x["chg"] = {s: round(p - was[s], 1) for s, p in x["prices"].items()
                    if p is not None and was.get(s) is not None and abs(p - was[s]) >= 0.5}
    # Nov 24 (James): Alpha Arcade markets traded in the last 24 h that the other sites also price, gap or not,
    # so the Alpha column isn't empty. Only markets with real Alpha trading today (an untraded Alpha price is often a placeholder).
    shown = set(x["title"] for x in g if x["prices"].get("alpha") is not None)
    side = []
    for r in mj["matches"]:
        a = r["sites"].get("alpha") or {}
        ps = r.get("prices") or {}
        if (not a or is_sports(r.get("categories") or []) or COMBO.search(r.get("title") or "") or r["title"] in shown
                or (a.get("volume24h") or 0) < 1 or ps.get("alpha") is None or len([v for v in ps.values() if v is not None]) < 2):
            continue
        diff = max(abs(ps["alpha"] - v) for k, v in ps.items() if k != "alpha" and v is not None)
        if diff > 15:
            continue                                  # a gap this big on a no-gap list = a placeholder price or a bad match
        side.append({"title": r["title"], "outcome": r.get("outcome"), "close": r.get("close"),
                     "prices": {s_: ps.get(s_) for s_ in ("polymarket", "kalshi", "alpha")},
                     "urls": {s_: x["url"] for s_, x in r["sites"].items()},
                     "diff": round(max(abs(ps["alpha"] - v) for k, v in ps.items() if k != "alpha" and v is not None), 1),
                     "vol24": a.get("volume24h") or 0})
    side = sorted(side, key=lambda r: -r["vol24"])[:10]
    json.dump({"updated": n.strftime(f), "note": NOTE, "alpha_fresh": alpha_fresh, "gaps": g, "alpha_side": side},
              open("gaps.json", "w"), indent=1)
    cal = calendar(mj["matches"])
    json.dump({"updated": n.strftime(f), "note": NOTE, "items": cal}, open("calendar.json", "w"), indent=1)
    print("Gaps: %d after filters (Alpha data fresh: %s)" % (len(g), alpha_fresh))
    for x in g:
        print("  net %4.1f (raw %4.1f - fees %3.1f) | %s | %s | low %s %s, high %s %s" % (
            x["net"], x["raw"], x["fees"], x["title"][:44], x["outcome"][:20],
            x["low"]["name"], x["low"]["price"], x["high"]["name"], x["high"]["price"]))
    print("Calendar: %d items" % len(cal))
    for i in cal:
        if i.get("links"):
            print("  %s | %s | LINKS %s" % (i["date"][:10], i["name"][:50], "; ".join(
                "%s %s %s" % (s[0].upper(), v["outcome"][:16], v["price"]) for s, v in i["links"].items())))
            continue
        mk = i["market"]
        print("  %s | %s | %s" % (i["date"][:10], i["name"][:50],
                                  ("%s P %s K %s A %s" % (mk["outcome"][:18], mk["prices"]["polymarket"],
                                                           mk["prices"]["kalshi"], mk["prices"]["alpha"])) if mk else "-"))


if __name__ == "__main__":
    main()
