# Alpha Intel Desk: Gap Scanner + Catalyst Calendar data.
# Reads matches.json (from match_markets.py) and catalysts.json (hand-kept list of scheduled events).
# Writes gaps.json  (price gaps after estimated fees, no sports, strict filters: all-3-site gaps first, then top 10 two-site)
#    and calendar.json (next scheduled catalysts + big non-sports markets resolving soon).
# Wording rule: "price gap after fees" - never "guaranteed" or "arbitrage", no trade instructions.
import json
from datetime import datetime, timezone, timedelta

f = "%Y-%m-%dT%H:%M:%SZ"
n = datetime.now(timezone.utc)
NOTE = ("Matches are automatic. Always check each site's rules before you trade. "
        "Fees are estimates; prices are midpoints and don't include the bid/ask spread.")

# ---------- filters (tune here) ----------
MIN_PRICE, MAX_PRICE = 3, 97          # skip near-certain outcomes: tiny prices are noisy
MAX_RAW_GAP = 35                      # bigger usually means a stale or mismatched market
LONGSHOT = 10                         # if the lower price is under 10 cents...
MAX_RATIO = 3                         # ...the higher one can't be more than 3x it (thin/stale book)
MIN_NET_GAP = 1.0                     # points left after estimated fees
MIN_VOLUME = {"alpha": 50, "polymarket": 5000, "kalshi": 500}   # $ / $ / contracts traded
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
    """Taker fee rate r; fee per $1 contract = r * p * (1 - p)."""
    if site == "kalshi":
        return 0.07
    if site == "alpha":
        fb = row["sites"]["alpha"].get("fee")
        return (fb / 1e6) if fb else 0.07          # feeBasePercent 70000 -> 0.07 (estimate)
    cats = " ".join(row.get("categories") or []).lower()  # Polymarket Fee Structure V2 by category
    if "geopolitic" in cats:
        return 0.0
    if "crypto" in cats:
        return 0.07
    if any(k in cats for k in ("politic", "election", "tech", "finance", "business")):
        return 0.04
    return 0.05


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
    return grade, {"src": src, "srcs": srcs[:4], "void": void}


def fair_price(row, ps):
    """Fair price estimate (Nov 10): each site's price weighted by dollars traded there.
    Kalshi volume is in contracts, so it's converted at that price. Deep markets count more."""
    w = {}
    for site, p in ps.items():
        v = row["sites"][site].get("volume") or 0
        w[site] = v * p / 100 if site == "kalshi" else v
    tot = sum(w.values())
    return round(sum(ps[x] * w[x] for x in ps) / tot, 1) if tot > 0 else None


def gaps(matches, alpha_fresh):
    out = []
    for row in matches:
        if is_sports(row.get("categories") or []):
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
            if site != "alpha" and (x.get("label") != "SAME" or x.get("flags")):
                continue                               # each site's match must be SAME with no warnings
            if (x.get("volume") or 0) < MIN_VOLUME[site]:
                continue
            for o, p in (x.get("outcomes") or {}).items():
                if p is not None and MIN_PRICE <= p <= MAX_PRICE:
                    table.setdefault(o, {})[site] = p
        best = None
        for o, ps in table.items():
            if len(ps) < 2:
                continue
            lo = min(ps, key=ps.get)
            hi = max(ps, key=ps.get)
            raw = ps[hi] - ps[lo]
            if raw > MAX_RAW_GAP:
                continue
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
    out.sort(key=lambda g: -g["net"])
    three = [g for g in out if g["all3"]]              # every all-three-sites gap, always shown first
    rest = [g for g in out if not g["all3"]]
    has_a = [g for g in rest if g["prices"].get("alpha") is not None]
    keep = has_a[:MIN_ALPHA_ROWS]
    keep += [g for g in rest if g not in keep][:TOP - len(keep)]
    keep.sort(key=lambda g: -g["net"])
    return three + keep


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
    json.dump({"updated": n.strftime(f), "note": NOTE, "alpha_fresh": alpha_fresh, "gaps": g},
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
