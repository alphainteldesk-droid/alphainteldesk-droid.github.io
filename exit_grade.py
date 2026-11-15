# Alpha Intel Desk: Danger Zone "Exit grade" (Nov 15, session 19).
# "Can I get out before close?" For each Danger Zone row, read the live PUBLIC order book for the side
# you'd hold and add up how many dollars you could sell back right now within 2 cents of the best bid.
#   Yes holder sells into Yes bids. No holder sells into No bids
#   (Polymarket: No bids = the Yes token's asks mirrored, 1 - price; Kalshi lists No bids directly).
# Adds row["ex"] = {"usd": dollars, "px": lowest price counted (cents), "bid": best bid (cents), "g": "A".."D"}
# to expiry.json. Alpha Arcade's book is on-chain (Fillable phase 2): no "ex", the page says "soon".
# Public data only, read-only. Never raises: if a book can't be read the row just has no grade.
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from fillable import _poly, _kalshi

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
    if site == "polymarket":
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


def main(path="expiry.json"):
    d = json.load(open(path))
    todo = [r for r in d["rows"] if r.get("site") in ("polymarket", "kalshi") and r.get("id")]
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
        for site in ("polymarket", "kalshi"):
            v = sorted(r["ex"]["usd"] for r in todo if "ex" in r and r["site"] == site)
            if v:
                print("  %s: n=%d median $%s p25 $%s p75 $%s" % (site, len(v), v[len(v) // 2], v[len(v) // 4], v[3 * len(v) // 4]))
    json.dump(d, open(path, "w"), separators=(",", ":"))


if __name__ == "__main__":
    main(*sys.argv[1:])
