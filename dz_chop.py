"""Nov 22 (James): Danger Zone "Chop" = how much a contract's price has swung in the last 48 hours.

For every contract on the Danger Zone list (expiry.json "rows", the top 50), read the last 48 h of prices for the
side the row lists and add row["ch"] = {"sw": high - low (cents), "hi", "lo", "pts": [up to 25 prices, one every 2 h],
"src": "hist" | "snap", "h": hours of data}. A swing of 10 cents or more = CHOPPY (the page shows a flag and the
mini-chart). It is NOT part of the DZ Grade yet: the track record logs it, and after 30+ results we check whether
choppy contracts miss more often.
  - Polymarket: CLOB prices-history for the row's token (hourly)
  - Kalshi: hourly candlesticks (midpoint of yes bid/ask, else last trade)
  - Alpha Arcade: no public history, so our own record: dz_alpha_hist.json (the feed price from alpha_hist.json,
    one point per run, kept 50 h; the first run copies the ~26 h alpha_hist.json already holds)
Public data only. Never raises: a row with no readable history just has no "ch".
"""
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from gap_chart import poly_hist, kalshi_hist

HOURS = 48
CHOPPY = 10.0            # cents, high - low over 48 h
KEEP = 50 * 3600
STEP = 2 * 3600          # mini-chart: one point every 2 h
BUDGET = 60
NOW = time.time()


def load(path, default):
    try:
        return json.load(open(path))
    except Exception:
        return default


def side_px(p, side):
    return round(p if side == "Yes" else 100 - p, 2)


def alpha_series(rows):
    """Keep our own 50-hour record of the Alpha feed price of every Alpha contract on the Danger Zone."""
    hist = load("alpha_hist.json", [])
    slug = {m.get("slug"): m.get("id") for m in (load("alpha_live.json", {}).get("markets") or [])}
    own = load("dz_alpha_hist.json", {})
    for r in rows:
        mid = slug.get((r.get("url") or "").rstrip("/").split("/")[-1])
        if not mid:
            continue
        k = "%s|%s" % (r["id"], r["side"])
        pts = own.get(k) or []
        have = {p[0] for p in pts}
        for h in (hist if not pts else hist[-1:]):          # first time: copy the whole ~26 h backlog
            v = (h.get("p", {}).get(mid) or {}).get(r["outcome"])
            if v is not None and int(h["t"]) not in have:
                pts.append([int(h["t"]), side_px(float(v), r["side"])])
        own[k] = sorted(p for p in pts if NOW - p[0] <= KEEP)
    own = {k: v for k, v in own.items() if v}
    json.dump(own, open("dz_alpha_hist.json", "w"), separators=(",", ":"))
    return own


def series(r, own):
    if r["site"] == "polymarket":
        return [[t, side_px(p, r["side"])] for t, p in poly_hist(r["id"])], "hist"
    if r["site"] == "kalshi":
        return [[t, side_px(p, r["side"])] for t, p in kalshi_hist(r["id"])], "hist"
    return list(own.get("%s|%s" % (r["id"], r["side"])) or []), "snap"


def chop(r, own):
    pts, src = series(r, own)
    pts = sorted([t, v] for t, v in pts if NOW - t <= HOURS * 3600)   # history only: mixing in the live ask
    if len(pts) < 2:                                                  # (not the mid) would add a fake swing
        return None
    vals = [v for _, v in pts]
    hi, lo = max(vals), min(vals)
    spark, t0 = [], NOW - HOURS * 3600
    for i in range(HOURS * 3600 // STEP + 1):              # last price in each 2-hour slot, carried forward
        cut = t0 + i * STEP
        before = [v for t, v in pts if t <= cut]
        if before:
            spark.append(round(before[-1], 1))
    return {"sw": round(hi - lo, 1), "hi": round(hi, 1), "lo": round(lo, 1), "pts": spark, "src": src,
            "h": round((NOW - pts[0][0]) / 3600)}


def main(path="expiry.json"):
    d = json.load(open(path))
    rows = d.get("rows") or []
    try:
        own = alpha_series([r for r in (d.get("all") or rows) if r.get("site") == "alpha" and r.get("id")])
    except Exception as e:
        print("Chop: Alpha record skipped (%s)" % e)
        own = {}
    done = fail = 0
    ex = ThreadPoolExecutor(6)
    futs = {ex.submit(chop, r, own): r for r in rows if r.get("id")}
    try:
        for f in as_completed(futs, timeout=BUDGET):
            r = futs[f]
            try:
                c = f.result()
            except Exception:
                fail += 1
                continue
            if c:
                r["ch"] = c
                done += 1
    except Exception:
        print("Chop: time budget (%ds) reached" % BUDGET)
    ex.shutdown(wait=False, cancel_futures=True)
    choppy = [r for r in rows if (r.get("ch") or {}).get("sw", 0) >= CHOPPY]
    print("Chop: %d of %d rows have 48h history (%d failed) | %d choppy (>= %.0fc swing): %s"
          % (done, len(rows), fail, len(choppy), CHOPPY,
             "; ".join("%s %s %s %.1fc" % (r["site"], r["title"][:30], r["side"], r["ch"]["sw"]) for r in choppy[:8])))
    json.dump(d, open(path, "w"), separators=(",", ":"))


if __name__ == "__main__":
    main()
