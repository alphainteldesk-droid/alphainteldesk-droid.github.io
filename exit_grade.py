# Alpha Intel Desk: Danger Zone "Exit grade" (Nov 15, session 19).
# "Can I get out before close?" For each Danger Zone row, read the live PUBLIC order book for the side
# you'd hold and add up how many dollars you could sell back right now within 2 cents of the best bid.
#   Yes holder sells into Yes bids. No holder sells into No bids
#   (Polymarket: No bids = the Yes token's asks mirrored, 1 - price; Kalshi lists No bids directly).
# Adds row["ex"] = {"usd": dollars, "px": lowest price counted (cents), "bid": best bid (cents), "g": "A".."D"}
# to expiry.json. Alpha Arcade (Nov 17): its on-chain book via the public Algorand indexer (fillable._alpha), Yes/No bids.
# Public data only, read-only. Never raises: if a book can't be read the row just has no grade.
import json
import math
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from fillable import _poly, _kalshi, _alpha

WITHIN = 0.02            # count bids down to 2 cents under the best bid
BUDGET = 120             # seconds; whatever isn't read by then gets no grade this run
WORKERS = 8
GRADES = ((10000, "A"), (2000, "B"), (300, "C"), (0, "D"))   # $ depth -> grade. Set Nov 15 from 529 live books: p25 $430, median $2.2K, p75 $7.5K, p90 $29K


def depth(site, row, tries=3):
    """Retries a busy site (Kalshi rate limit) up to 3 times, then gives up on that row this run."""
    for i in range(tries):
        try:
            return _depth(site, row)
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(1.5 * (i + 1))


def _depth(site, row):
    """-> (usd, lowest price counted, best bid) for selling the row's side, or None if no bids."""
    if site == "alpha":                                     # Nov 17: on-chain book, Yes and No bids listed separately
        book = _alpha(row["id"])
        held = book["yes" if row["side"] == "Yes" else "no"]
        asks = book["ask_yes" if row["side"] == "Yes" else "ask_no"]
        row["_ask"] = (asks[0][0] * 100, sum(q for a, q in asks if a <= asks[0][0] + 1e-9)) if asks else None   # Nov 19: real best ask
    elif site == "polymarket":
        asks, bids = _poly(row["id"])                       # the Yes token's book
        held = bids if row["side"] == "Yes" else [(round(1 - p, 4), q) for p, q in asks]
    else:
        d_asks, d_bids = _kalshi(row["id"])                 # fillable: asks = No bids mirrored
        held = d_bids if row["side"] == "Yes" else [(round(1 - p, 4), q) for p, q in d_asks]
    held = sorted((x for x in held if x[0] > 0 and x[1] > 0), reverse=True)
    if not held:
        return None
    best = held[0][0]
    lv = [(p, q) for p, q in held if p >= best - WITHIN - 1e-9]
    return sum(p * q for p, q in lv), lv[-1][0], best


def grade(usd):
    return next(g for lo, g in GRADES if usd >= lo)


TOP = 50                 # James, Nov 15: a short list, not 600 rows
ALPHA_SPOTS = 10         # the 10 busiest Alpha Arcade contracts always make the list (Alpha is the site's niche)
PX = re.compile(r"bitcoin|ethereum|solana|dogecoin|\b(btc|eth|xrp|sol|doge|bnb)\b|\bprices?\b|\b(s&p|nasdaq|dow|nikkei|ftse|wti|brent|gold|silver|treasury|yield)\b|\bclose (above|below|at)\b", re.I)
EXIT_W = {"A": 1.0, "B": 0.85, "C": 0.65}


RULES_W = {"clear": 1.0, "mixed": 0.95, "none": 0.9, "judgement": 0.85}   # rules grade A B C D; not graded yet = 0.9


def score(r):
    """Good return (capped at 10%, so steadier 90¢+ contracts compete) x easy to sell x busy market x clear rules.
    Same volume factor as the Daily Short. Nov 17 (James): the rules half of the DZ Grade counts too, as a gentle nudge
    (a stronger one pushed nearly every Polymarket geopolitics market out, since most say "consensus of credible reporting")."""
    w = EXIT_W.get((r.get("ex") or {}).get("g"), 0.6)
    rw = RULES_W.get((r.get("st") or {}).get("g"), 0.9)
    return min(r["ret"], 10) * w * rw * min(1, math.log10(max(r.get("volume") or 0, 10)) / 5.3)


def curate(rows):
    """The top 50: no daily price markets, no D (hard to sell) grades, the best contract per market,
    10 spots kept for Alpha Arcade (busiest first, even with a thin book: the page says so), the rest by score."""
    from short_crypto import short_crypto            # Nov 21 (James): no weekly/daily crypto price contracts
    ok = [r for r in rows if not (r["days"] < 3 and PX.search(r["title"] + " " + (r.get("cat") or "")))
          and not short_crypto(r["title"])
          and (r["site"] == "alpha" or (r.get("ex") or {}).get("g") != "D")]   # Nov 17 (James): Alpha keeps its 10 spots even when its book is thin
    best = {}
    for r in ok:
        k = (r["site"], r["title"])
        if k not in best or score(r) > score(best[k]):
            best[k] = r
    ok = list(best.values())
    alpha = sorted([r for r in ok if r["site"] == "alpha"], key=lambda r: -(r.get("volume") or 0))[:ALPHA_SPOTS]
    rest = sorted([r for r in ok if r["site"] != "alpha"], key=lambda r: -score(r))[:TOP - len(alpha)]
    return sorted(alpha + rest, key=lambda r: r["days"])


LO, HI = 80, 98.5        # same price window as match_markets.EXP_LO / EXP_HI


def alpha_real_prices(rows):
    """Nov 19 (James): Alpha Arcade rows used the last trade price ("est"). Now that we read Alpha's on-chain book,
    use the real best ask (what you'd pay right now) and redo the fee, return and per-year figure from it.
    No sellers at all: the row keeps the last price, stays "est" and says so. A real ask outside 80-98.5 or a
    return under 0.3% drops the row, same rules as every other site."""
    real = noask = gone = 0
    for r in list(rows):
        if r.get("site") != "alpha" or "_ask" not in r:
            continue
        got = r.pop("_ask")
        if not got:
            r["noask"] = True
            noask += 1
            continue
        ask, q = got
        p = ask / 100
        fee = 100 * r["fr"] * p * (1 - p)
        cost = ask + fee
        ret = (100 - cost) / cost * 100
        if not (LO <= ask <= HI) or ret < 0.3:
            rows.remove(r)
            gone += 1
            continue
        r.update(last=r["ask"], ask=round(ask, 1), fee=round(fee, 2), ret=round(ret, 2),
                 apr=round(ret * 365 / r["days"]), est=False, askq=round(q))
        real += 1
    if real or noask or gone:
        print("Danger Zone: Alpha real ask on %d rows, %d with no sellers (kept as est), %d dropped (real ask outside 80-98.5c or return under 0.3%%)"
              % (real, noask, gone))


def main(path="expiry.json"):
    d = json.load(open(path))
    todo = [r for r in d["rows"] if r.get("site") in ("polymarket", "kalshi", "alpha") and r.get("id")]
    t0, done, fail, empty = time.time(), 0, 0, 0
    ex = ThreadPoolExecutor(WORKERS)
    futs = {ex.submit(depth, r["site"], r): r for r in todo}
    try:
        for f in as_completed(futs, timeout=BUDGET):
            r = futs[f]
            try:
                got = f.result()
            except Exception:
                fail += 1
                continue
            if got is None:
                empty += 1
                r["ex"] = {"usd": 0, "px": None, "bid": None, "g": "D"}
            else:
                usd, px, best = got
                r["ex"] = {"usd": round(usd), "px": round(px * 100, 1), "bid": round(best * 100, 1), "g": grade(usd)}
            done += 1
    except Exception:
        print("Exit grade: time budget (%ds) reached" % BUDGET)
    ex.shutdown(wait=False, cancel_futures=True)
    vals = sorted(r["ex"]["usd"] for r in todo if "ex" in r)
    if vals:
        pct = lambda q: vals[min(len(vals) - 1, int(q * len(vals)))]
        print("Exit grade: %d of %d books read in %.0fs (%d failed, %d no bids) | $ depth p10 %s p25 %s p50 %s p75 %s p90 %s | grades %s"
              % (done, len(todo), time.time() - t0, fail, empty, pct(.1), pct(.25), pct(.5), pct(.75), pct(.9),
                 {g: sum(1 for r in todo if r.get("ex", {}).get("g") == g) for _, g in GRADES}))
        for site in ("polymarket", "kalshi", "alpha"):
            v = sorted(r["ex"]["usd"] for r in todo if "ex" in r and r["site"] == site)
            if v:
                print("  %s: n=%d median $%s p25 $%s p75 $%s" % (site, len(v), v[len(v) // 2], v[len(v) // 4], v[3 * len(v) // 4]))
    try:
        alpha_real_prices(d["rows"])
    except Exception as e:                             # never let this stop the Danger Zone building
        print("Danger Zone: Alpha real ask skipped (%s)" % e)
        for r in d["rows"]:
            r.pop("_ask", None)
    d["all"] = d["rows"]                               # the full list stays in the file (the Daily Short falls back to it)
    d["rows"] = curate(d["rows"])
    from collections import Counter
    print("Danger Zone top %d: %s | windows %s" % (len(d["rows"]), dict(Counter(r["site"] for r in d["rows"])),
          dict(Counter("<7d" if r["days"] < 7 else "<31d" if r["days"] < 31 else "1-3m" if r["days"] < 91 else "3-6m" for r in d["rows"]))))
    json.dump(d, open(path, "w"), separators=(",", ":"))


if __name__ == "__main__":
    main(*sys.argv[1:])
