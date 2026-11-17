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


def _alpha(app_id):
    """Nov 17: Alpha Arcade's book is on-chain. Every order is a small app created by the market app, so the
    market app's address lists them (public Algorand indexer, no Alpha API key). Open limit orders only, as the
    Alpha SDK reads them: position 1 = Yes, 0 = No; side 1 = buy, 0 = sell; price and quantity in millionths.
    -> {"yes": [(price $, shares) high->low], "no": [...]} = what a holder of that side can sell into right now:
    direct buyers of that side + sellers of the other side at 1 - price (Alpha's "complementary matching",
    alpha-sdk utils/matching.ts). Wallet addresses are never read or kept."""
    import base64, hashlib
    pk = hashlib.new("sha512_256", b"appID" + int(app_id).to_bytes(8, "big")).digest()
    addr = base64.b32encode(pk + hashlib.new("sha512_256", pk).digest()[-4:]).decode().rstrip("=")
    out, nxt = {"yes": [], "no": []}, ""
    for _ in range(10):                                     # 1,000 orders a page; 10 pages is far more than any market has
        d = _get("https://mainnet-idx.algonode.cloud/v2/accounts/%s/created-applications?limit=1000%s"
                 % (addr, "&next=" + nxt if nxt else ""))
        apps = d.get("applications") or []
        for a in apps:
            if a.get("deleted"):
                continue
            g = {}
            for kv in (a.get("params") or {}).get("global-state") or []:
                k = base64.b64decode(kv["key"]).decode("latin1")
                if k in ("price", "quantity", "quantity_filled", "side", "position", "slippage"):
                    g[k] = kv["value"].get("uint", 0)
            left = g.get("quantity", 0) - g.get("quantity_filled", 0)
            if left <= 0 or g.get("slippage") != 0 or not g.get("price"):
                continue
            pos, p = ("yes" if g.get("position") == 1 else "no"), g["price"] / 1e6
            if g.get("side") == 1:                          # a buy order: a holder of that side can sell to it
                out[pos].append((p, left / 1e6))
            else:                                           # a sell order: a holder of the OTHER side gets 1 - p (merge)
                out["no" if pos == "yes" else "yes"].append((round(1 - p, 6), left / 1e6))
        nxt = d.get("next-token") or ""
        if len(apps) < 1000 or not nxt:
            break
    for k in out:
        out[k].sort(reverse=True)
    return out


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
