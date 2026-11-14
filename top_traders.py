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

OUT = "traders.json"
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


def polymarket():
    rows = (get(q(PM + "/leaderboard", time_period="week", sort_by="PNL", limit=TOP)) or {}).get("data") or []
    since = int(time.time()) - 7 * 86400
    out = []
    for r in rows[:TOP]:
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


def kalshi():
    d = get(q(KA, metric_name="projected_pnl", limit=TOP, since_day_before=7)) or {}
    out = []
    for r in (d.get("rank_list") or [])[:TOP]:
        if r.get("is_anonymous") or not r.get("nickname"):
            name = "Anonymous trader"
        else:
            name = r["nickname"]
        out.append({"name": name, "pnl": round(float(r.get("value") or 0)), "url": "https://kalshi.com/social/leaderboard"})
    return out


def norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def alpha(exclude):
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
    out = out[:TOP]
    since = time.time() - 7 * 86400
    for t in out:                                    # Nov 14: public username + biggest trade of the last 7 days
        w = t.pop("_w", "")
        if not w:
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
                and all(old.get(k) for k in ("polymarket", "kalshi", "alpha")):       # an empty board is retried on the next run
            print("Top traders: fresh enough, skipped")
            return
    except Exception:
        pass
    exclude = [norm(x) for x in (os.environ.get("TRADERS_EXCLUDE") or "").split(",") if len(norm(x)) >= 4]
    out = {"updated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "window": "7 days"}
    for site, fn in (("polymarket", polymarket), ("kalshi", kalshi)):
        try:
            out[site] = fn()
        except Exception as err:
            print("Top traders: %s failed: %s" % (site, str(err)[:120]))
            out[site] = old.get(site) or []          # keep the last good board rather than an empty card
    try:                                             # Nov 14: owner's call - the public board is shown as is;
        out["alpha"] = alpha(exclude)                # TRADERS_EXCLUDE stays as an optional private list
    except Exception as err:
        print("Top traders: alpha failed: %s" % str(err)[:120])
        out["alpha"] = old.get("alpha") or []
    json.dump(out, open(OUT, "w"), ensure_ascii=False, indent=1)
    print("Top traders: Polymarket %d, Kalshi %d, Alpha Arcade %d"
          % (len(out["polymarket"]), len(out["kalshi"]), len(out["alpha"])))


if __name__ == "__main__":
    main()
