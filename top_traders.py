#!/usr/bin/env python3
"""Top Traders (Nov 14): who is making the most this week on each site, and their biggest move.

Writes traders.json for the homepage. Public leaderboards only:
  Polymarket  data-api v2 /leaderboard (week, by profit) + each trader's biggest trade of the last 7 days
  Kalshi      public social leaderboard (last 7 days, by profit)
  Alpha Arcade  the site's own leaderboard (by profit)

The Alpha Arcade board is the site's public leaderboard, shown as is. The optional TRADERS_EXCLUDE
secret (comma-separated names / wallet addresses) keeps listed accounts off it.
Nothing from the Alpha board is printed to the log except field names.
"""
import json, os, re, sys, time, urllib.parse, urllib.request
from datetime import datetime, timezone

OUT = "traders.json"             # homepage: top 5 per site
FULL = "traders_full.json"       # /top-traders.html: longer boards + Polymarket boards by subject
LONG = 20
CATEGORIES = ("politics", "crypto", "economy", "finance", "culture", "tech", "geopolitics", "world")
MIN_AGE = 50 * 60            # leaderboards move slowly: refresh about once an hour
TOP = 5
UA = {"User-Agent": "AlphaIntelDesk/1.0 (+https://alphainteldesk.com)", "Accept": "application/json"}
PM = "https://data-api.polymarket.com/v2"
KA = "https://api.elections.kalshi.com/v1/social/leaderboard"
AAPI = "https://api.alphaarcade.com/api"
AA = AAPI + "/leaderboard-new"


def get(url, timeout=20):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def q(base, **params):
    return base + "?" + urllib.parse.urlencode(params)


def polymarket(n=TOP, category=None):
    prm = {"time_period": "week", "sort_by": "PNL", "limit": n}
    if category:
        prm["category"] = category
    rows = (get(q(PM + "/leaderboard", **prm)) or {}).get("data") or []
    since = int(time.time()) - 7 * 86400
    out = []
    for r in rows[:n]:
        wallet = r.get("user_id") or ""
        t = {"name": (r.get("user_name") or "").strip() or wallet[:6] + "…" + wallet[-4:],
             "pnl": round(float(r.get("pnl") or 0)), "volume": round(float(r.get("volume") or 0)),
             "url": "https://polymarket.com/profile/" + wallet}
        if re.fullmatch(r"0x[0-9a-fA-F]{40}.*", t["name"]):      # unnamed accounts show as a long address
            t["name"] = wallet[:6] + "…" + wallet[-4:]
        try:
            tr = (get(q(PM + "/trades", user=wallet, limit=200, start=since, filter_type="CASH", filter_amount=1000))
                  or {}).get("data") or []
            best = max(tr, key=lambda x: float(x.get("size") or 0) * float(x.get("price") or 0), default=None)
            if best:
                t["move"] = {"side": (best.get("side") or "").upper(), "outcome": best.get("outcome") or "",
                             "title": best.get("title") or "", "price": round(float(best.get("price") or 0) * 100, 1),
                             "usd": round(float(best.get("size") or 0) * float(best.get("price") or 0)),
                             "when": datetime.fromtimestamp(int(best.get("timestamp") or 0), timezone.utc).isoformat(),
                             "url": "https://polymarket.com/event/" + (best.get("event_slug") or best.get("slug") or "")}
        except Exception as err:
            print("  Polymarket trades for one trader failed:", str(err)[:80])
        out.append(t)
        time.sleep(0.3)
    return out


def kalshi(n=TOP):
    d = get(q(KA, metric_name="projected_pnl", limit=n, since_day_before=7)) or {}
    out = []
    for r in (d.get("rank_list") or [])[:n]:
        if r.get("is_anonymous") or not r.get("nickname"):
            name = "Anonymous trader"
        else:
            name = r["nickname"]
        out.append({"name": name, "pnl": round(float(r.get("value") or 0)), "url": "https://kalshi.com/social/leaderboard"})
    return out


KT = "https://api.elections.kalshi.com/trade-api/v2/markets/trades"
BIG_MARKETS = 12


def kalshi_big(n=5, per_market=2):
    """Nov 14: Kalshi hides who trades, and its top traders hide their positions. What IS public is every trade.
    So: the biggest single trades of the last 7 days in the busiest Kalshi markets the desk already matches
    across sites (tickers come from matches.json). Anonymous by nature: what was bought, at what price, how much."""
    rows = json.load(open("matches.json")).get("matches") or []
    seen, picks = set(), []
    for r in sorted(rows, key=lambda r: -float(((r.get("sites") or {}).get("kalshi") or {}).get("volume24h") or 0)):
        k = (r.get("sites") or {}).get("kalshi") or {}
        lab = k.get("matched_outcome")
        tick = (k.get("book") or {}).get(r.get("outcome")) or next(iter((k.get("book") or {}).values()), None)
        if not tick or tick in seen:
            continue
        seen.add(tick)
        picks.append((tick, k.get("title") or r.get("title") or "", lab or "", k.get("url") or ""))
        if len(picks) >= BIG_MARKETS:
            break
    since, out = int(time.time()) - 7 * 86400, []
    for tick, title, lab, url in picks:
        try:
            d = get(q(KT, ticker=tick, limit=1000, min_ts=since)) or {}
        except Exception as err:
            print("  Kalshi trades for one market failed:", str(err)[:60])
            continue
        for t in d.get("trades") or []:
            side = (t.get("taker_side") or "yes").lower()
            px = float(t.get(side + "_price_dollars") or 0)
            usd = float(t.get("count_fp") or t.get("count") or 0) * px
            if usd >= 1000:
                out.append({"usd": round(usd), "side": side.upper(), "price": round(px * 100, 1), "title": title,
                            "outcome": lab, "when": t.get("created_time") or "", "url": url})
        time.sleep(0.25)
    out.sort(key=lambda x: -x["usd"])
    top, per = [], {}
    for x in out:                                    # at most 2 per market so one market can't fill the list
        if per.get(x["url"], 0) < per_market:
            per[x["url"]] = per.get(x["url"], 0) + 1
            top.append(x)
        if len(top) >= n:
            break
    print("  Kalshi big trades: %d markets read, %d trades of $1,000+, kept %d" % (len(picks), len(out), len(top)))
    return top


def norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def alpha(exclude, n=TOP, moves=TOP):
    d = get(AA)
    rows = d if isinstance(d, list) else next((v for v in (d or {}).values() if isinstance(v, list)), [])
    if not rows or not isinstance(rows[0], dict):
        print("  Alpha Arcade board: unexpected shape (%s)" % type(d).__name__)
        return []
    keys = sorted(rows[0].keys())
    print("  Alpha Arcade board: %d rows, fields: %s" % (len(rows), ", ".join(keys)))      # field names only, never values
    pick = lambda r, *names: next((r[k] for k in keys for nm in names if nm == k.lower() and r.get(k) not in (None, "")), None)
    out, hidden = [], 0
    for r in rows:
        blob = norm(json.dumps(r))
        if any(x and x in blob for x in exclude):
            hidden += 1
            continue
        wallet = str(pick(r, "wallet", "address", "walletaddress", "user", "account") or "")
        name = str(pick(r, "username", "name", "nfd", "displayname", "nickname") or "")
        if not name or re.fullmatch(r"[A-Z2-7]{58}", name):
            w = wallet or name
            name = w[:4] + "…" + w[-2:] if w else "Trader"
        num = lambda *n: float(pick(r, *n) or 0)
        out.append({"name": name[:28], "pnl": round(num("profitlossusd", "pnl", "pl", "profit", "totalpnl", "realizedpnl")),
                    "volume": round(num("volumeusd", "volume", "totalvolume", "vol")),
                    "url": "https://www.alphaarcade.com/leaderboard", "_w": wallet})
    print("  Alpha Arcade board: %d rows kept out by the private list" % hidden)
    out.sort(key=lambda t: -t["pnl"])
    out = out[:n]
    since = time.time() - 7 * 86400
    for i, t in enumerate(out):                      # Nov 14: public username + biggest trade of the last 7 days
        w = t.pop("_w", "")
        if not w or i >= moves:
            continue
        try:
            u = (get(q(AAPI + "/get-username-by-wallet", walletAddress=w), timeout=10) or {}).get("username")
            if u and not any(x and x in norm(u) for x in exclude):
                t["name"] = str(u)[:28]
        except Exception:
            pass
        try:
            trades = (get(q(AAPI + "/get-wallet-trades", wallet=w), timeout=15) or {}).get("trades") or []
            def stamp(x):
                c = x.get("createdAt")
                if isinstance(c, (int, float)):
                    return c / 1000 if c > 1e11 else c
                try:
                    return datetime.fromisoformat(str(c).replace("Z", "+00:00")).timestamp()
                except Exception:
                    return 0
            def money(x):                            # amounts may come in millionths of a dollar
                amt, px = float(x.get("totalAmount") or 0), float(x.get("pricePerShare") or 0)
                micro = px > 1.5
                return (amt / 1e6 if micro else amt), (px / 1e6 if micro else px)
            week = [x for x in trades if stamp(x) >= since]
            best = max(week, key=lambda x: money(x)[0], default=None)
            if best and money(best)[0] >= 1:
                usd, px = money(best)
                t["move2"] = {"side": "SELL" if "sell" in str(best.get("type") or "").lower() else "BUY",
                              "outcome": str(best.get("position") or ""), "title": str(best.get("marketTitle") or ""),
                              "price": round(px * 100, 1), "usd": round(usd),
                              "when": datetime.fromtimestamp(stamp(best), timezone.utc).isoformat(),
                              "url": "https://www.alphaarcade.com/market/" + str(best.get("slug") or "")}
        except Exception as err:
            print("  Alpha Arcade trades for one trader failed:", str(err)[:60])
        time.sleep(0.3)
    return out


def main():
    old = {}
    try:
        old = json.load(open(OUT))
        if time.time() - datetime.fromisoformat(old["updated"]).timestamp() < MIN_AGE and "--force" not in sys.argv \
                and all(old.get(k) for k in ("polymarket", "kalshi", "alpha")) and "kalshi_big" in old and os.path.exists(FULL):       # an empty board is retried on the next run
            print("Top traders: fresh enough, skipped")
            return
    except Exception:
        pass
    exclude = [norm(x) for x in (os.environ.get("TRADERS_EXCLUDE") or "").split(",") if len(norm(x)) >= 4]
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        oldf = json.load(open(FULL))
    except Exception:
        oldf = {}
    full = {"updated": now, "window": "7 days"}

    def board(key, fn):                              # keep the last good board rather than an empty one
        try:
            full[key] = fn()
        except Exception as err:
            print("Top traders: %s failed: %s" % (key, str(err)[:120]))
            full[key] = oldf.get(key) or []

    board("polymarket", lambda: polymarket(LONG))
    cats = {}
    for cat in CATEGORIES:                           # Nov 14: boards by subject, so it isn't all sports
        try:
            rows = polymarket(10, cat)
            if len(rows) >= 3 and [r["url"] for r in rows[:3]] != [r["url"] for r in (full["polymarket"] or [])[:3]]:
                cats[cat] = rows
            else:
                print("  Polymarket category '%s': no separate board" % cat)
        except Exception as err:
            print("  Polymarket category '%s' failed: %s" % (cat, str(err)[:60]))
    full["polymarket_by"] = cats or oldf.get("polymarket_by") or {}
    board("kalshi", lambda: kalshi(LONG))
    board("kalshi_big", lambda: kalshi_big(10, 3))
    board("alpha", lambda: alpha(exclude, LONG, 10))   # owner's call: the public board is shown as is; TRADERS_EXCLUDE is optional
    json.dump(full, open(FULL, "w"), ensure_ascii=False, indent=1)
    out = {"updated": now, "window": "7 days", "polymarket": full["polymarket"][:TOP], "kalshi": full["kalshi"][:TOP],
           "kalshi_big": full["kalshi_big"][:5], "alpha": full["alpha"][:TOP]}
    json.dump(out, open(OUT, "w"), ensure_ascii=False, indent=1)
    print("Top traders: Polymarket %d, Kalshi %d, Alpha Arcade %d"
          % (len(out["polymarket"]), len(out["kalshi"]), len(out["alpha"])))


if __name__ == "__main__":
    main()
