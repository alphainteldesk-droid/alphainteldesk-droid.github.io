# Alpha Intel Desk: "Fillable size" for Gap Scanner gaps (Nov 10, phase 1: Polymarket + Kalshi).
# For each gap shown, read the two sites' PUBLIC order books and walk the real prices:
#   buy Yes on the cheap site at its asks, buy No on the expensive site (= its Yes bids, mirrored).
# Keep going while the gap after both fees stays >= MIN_NET cents. Result: about how many dollars
# could be traded at a real gap after fees, and the best real (executable) gap right now.
# Public data only. Alpha Arcade's book is on-chain (phase 2, next session). No trades, no keys.
import json
import urllib.request

MIN_NET = 1.0            # cents per $1 share left after fees, same floor as make_gaps.py
UA = {"User-Agent": "AlphaIntelDesk/1.0 (+https://alphainteldesk.com)", "Accept": "application/json"}


def _get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=12) as r:
        return json.load(r)


def _poly(token):
    """Polymarket CLOB book for one outcome token -> (asks low->high, bids high->low) as [(price $, shares)]."""
    d = _get("https://clob.polymarket.com/book?token_id=" + str(token))
    asks = sorted((float(x["price"]), float(x["size"])) for x in d.get("asks") or [])
    bids = sorted(((float(x["price"]), float(x["size"])) for x in d.get("bids") or []), reverse=True)
    return asks, bids


def _kalshi(ticker):
    """Kalshi book: only bids are listed, for Yes and for No. A No bid at q is a Yes ask at 1 - q."""
    d = _get("https://api.elections.kalshi.com/trade-api/v2/markets/%s/orderbook" % ticker)
    ob = d.get("orderbook_fp") or d.get("orderbook") or {}

    def side(dollars_key, cents_key):
        if ob.get(dollars_key):
            return [(float(p), float(q)) for p, q in ob[dollars_key]]
        return [(float(p) / 100, float(q)) for p, q in (ob.get(cents_key) or [])]
    yes, no = side("yes_dollars", "yes"), side("no_dollars", "no")
    bids = sorted(yes, reverse=True)
    asks = sorted((round(1 - p, 4), q) for p, q in no)
    return asks, bids


READ = {"polymarket": _poly, "kalshi": _kalshi}


def walk(asks, bids, r_lo, r_hi):
    """Pair the cheap site's asks with the expensive site's bids while the gap after fees >= MIN_NET.
    Returns (dollars needed for both sides, shares, best executable gap in cents after fees)."""
    i = j = 0
    a = [list(x) for x in asks]
    b = [list(x) for x in bids]
    usd = shares = 0.0
    best = None
    while i < len(a) and j < len(b):
        pa, pb = a[i][0], b[j][0]
        net = 100 * (pb - pa - r_lo * pa * (1 - pa) - r_hi * pb * (1 - pb))
        if best is None:
            best = round(net, 1)
        if net < MIN_NET:
            break
        q = min(a[i][1], b[j][1])
        usd += q * (pa + (1 - pb))           # Yes at pa on one site + No at (1 - pb) on the other
        shares += q
        a[i][1] -= q
        b[j][1] -= q
        if a[i][1] <= 1e-9:
            i += 1
        if b[j][1] <= 1e-9:
            j += 1
    return round(usd), round(shares), best


def add_fillable(gaps, matches):
    """Adds g['fill'] = {'usd', 'shares', 'exec'} where both books could be read. Never raises."""
    rows = {(m["title"], m.get("close")): m for m in matches}
    done = 0
    for g in gaps:
        try:
            lo, hi = g["low"]["site"], g["high"]["site"]
            if lo not in READ or hi not in READ:
                print("  FILL skip (Alpha Arcade book: phase 2) | %s" % g["title"][:50])
                continue
            row = rows.get((g["title"], g.get("close")))
            if not row:
                continue
            tl = (row["sites"][lo].get("book") or {}).get(g["outcome"])
            th = (row["sites"][hi].get("book") or {}).get(g["outcome"])
            if not tl or not th:
                print("  FILL no book id | %s | %s=%s %s=%s" % (g["title"][:44], lo, bool(tl), hi, bool(th)))
                continue
            asks, _ = READ[lo](tl)
            _, bids = READ[hi](th)
            usd, sh, best = walk(asks, bids, g.get("rate_low") or 0, g.get("rate_high") or 0)
            g["fill"] = {"usd": usd, "shares": sh, "exec": best}
            done += 1
            print("  FILL $%-7s %6s sh | exec gap %s¢ (mid gap %s¢) | best ask %s %s, best bid %s %s | %s" % (
                usd, sh, best, g["net"], lo, asks[0][0] if asks else "-", hi, bids[0][0] if bids else "-",
                g["title"][:40]))
        except Exception as err:
            print("  FILL failed | %s | %s" % (g.get("title", "")[:44], err))
    print("Fillable: order books read for %d of %d gaps" % (done, len(gaps)))
