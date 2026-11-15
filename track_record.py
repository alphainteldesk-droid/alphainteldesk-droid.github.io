# Alpha Intel Desk: Danger Zone track record (Nov 15, 2026).
# Logs every Polymarket / Kalshi contract the FIRST time it appears on The Danger Zone (expiry.json), at the price
# we listed it, then checks whether it paid out once it settles. Writes track.json:
#   "summary": what the page shows (X% paid out, and what $1 in each at our listed price would have returned),
#   "misses":  the most recent listed contracts that did NOT pay out (shown on the page, nothing hidden),
#   "open":    contracts still waiting for a result (the working list).
# Results: Kalshi /markets?tickers=... -> "result" yes/no; Polymarket gamma /markets?clob_token_ids=...&closed=true
# -> outcomePrices ["1","0"] = Yes won, once umaResolutionStatus is "resolved".
# Alpha Arcade: read on-chain from the public Algorand API (never Alpha Arcade's own site): each outcome is an app
# with global state is_resolved=1 and outcome=1 (Yes paid) / 0 (No paid). Checked Nov 15 against 4 UFC 334 fights
# settled on Polymarket. Runs after match_markets.py in the update job.
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

UA = {"User-Agent": "AlphaIntelDesk/1.0 (+https://alphainteldesk.com)", "Accept": "application/json"}
KALSHI = "https://api.elections.kalshi.com/trade-api/v2/markets?"
GAMMA = "https://gamma-api.polymarket.com/markets?"
ALGOD = "https://mainnet-api.algonode.cloud/v2/applications/"
GONE_SECS = 6 * 3600          # off the list for 6 h -> it may have settled early: check it
RECHECK_SECS = 6 * 3600       # not settled yet -> look again in 6 h
GIVE_UP_DAYS = 45             # still no result 45 days after close -> stop checking, count it nowhere
MAX_LOOKUPS = 300             # contracts checked per run (keeps the job short)
PX = re.compile(r"bitcoin|ethereum|solana|dogecoin|\b(btc|eth|xrp|sol|doge|bnb)\b|\bprices?\b|\b(s&p|nasdaq|dow|nikkei|"
                r"ftse|wti|brent|gold|silver|treasury|yield)\b|\bclose (above|below|at)\b", re.I)   # same test as the page


def ts(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return json.load(r)


def kalshi_results(tickers):
    """{ticker: 'yes'/'no'} for settled markets."""
    out = {}
    for i in range(0, len(tickers), 100):
        d = get(KALSHI + urllib.parse.urlencode({"tickers": ",".join(tickers[i:i + 100]), "limit": 1000}))
        for m in d.get("markets") or []:
            if m.get("status") in ("settled", "finalized", "determined") and m.get("result") in ("yes", "no"):
                out[m["ticker"]] = m["result"]
            elif m.get("status") in ("settled", "finalized") and m.get("result") not in ("yes", "no"):
                out[m["ticker"]] = "void"
    return out


def poly_results(tokens):
    """{yes_token: 'yes'/'no'} for resolved markets."""
    out = {}
    for i in range(0, len(tokens), 20):
        q = [("clob_token_ids", t) for t in tokens[i:i + 20]] + [("closed", "true"), ("limit", 100)]
        for m in get(GAMMA + urllib.parse.urlencode(q)) or []:
            try:
                toks = json.loads(m.get("clobTokenIds") or "[]")
                px = [float(x) for x in json.loads(m.get("outcomePrices") or "[]")]
            except (ValueError, TypeError):
                continue
            if not toks or len(px) != 2 or m.get("umaResolutionStatus") != "resolved":
                continue
            if px == [1.0, 0.0]:
                out[toks[0]] = "yes"
            elif px == [0.0, 1.0]:
                out[toks[0]] = "no"
            else:
                out[toks[0]] = "void"          # 50-50 or other split settlement
    return out


def alpha_results(apps):
    """{app_id: 'yes'/'no'} for resolved Alpha Arcade outcomes (one small request per app)."""
    import base64
    out = {}
    for a in apps:
        try:
            gs = get(ALGOD + str(int(a))).get("params", {}).get("global-state") or []
        except Exception as err:
            print("Track record: Algorand lookup for %s failed (%s)" % (a, err))
            continue
        g = {base64.b64decode(x["key"]).decode("latin-1"): (x.get("value") or {}).get("uint") for x in gs}
        if g.get("is_resolved") == 1 and g.get("outcome") in (0, 1):
            out[str(a)] = "yes" if g["outcome"] == 1 else "no"
    return out


def bucket(days):
    return "1-6 months" if days >= 30 else "under 1 month"


def main():
    now = time.time()
    try:
        st = json.load(open("track.json"))
        if st.get("v") != 2:                    # Nov 15 (James): restart once for the top-50 list (0 had settled)
            raise ValueError("restart")
    except Exception:
        st = {"v": 2, "started": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "open": {}, "misses": [], "agg": {}}
    rows = json.load(open("expiry.json")).get("rows") or []

    new = 0                                    # 1. log contracts the first time we list them
    for x in rows:
        if x.get("site") not in ("polymarket", "kalshi", "alpha") or not x.get("id"):
            continue
        k = "%s|%s|%s" % (x["site"], x["id"], x["side"])
        if k in st["open"]:
            st["open"][k]["ls"] = now
            continue
        if k in st.get("done", {}):
            continue
        st["open"][k] = {"t": x["title"], "o": x["outcome"], "s": x["side"], "a": x["ask"], "f": x["fee"],
                         "r": x["ret"], "c": x["close"], "d": x["days"], "u": x["url"], "fs": now, "ls": now,
                         "px": bool(x["days"] < 3 and PX.search(x["title"] + " " + (x.get("cat") or "")))}
        new += 1

    due = [k for k, v in st["open"].items()          # 2. which ones may have settled
           if (now > ts(v["c"]) + 3600 or now - v["ls"] > GONE_SECS) and now >= v.get("nx", 0)]
    due = sorted(due, key=lambda k: ts(st["open"][k]["c"]))[:MAX_LOOKUPS]
    res = {}
    try:
        res.update(kalshi_results([k.split("|")[1] for k in due if k.startswith("kalshi|")]))
    except Exception as err:
        print("Track record: Kalshi lookup failed (%s)" % err)
    try:
        res.update(poly_results([k.split("|")[1] for k in due if k.startswith("polymarket|")]))
    except Exception as err:
        print("Track record: Polymarket lookup failed (%s)" % err)

    try:
        res.update(alpha_results([k.split("|")[1] for k in due if k.startswith("alpha|")]))
    except Exception as err:
        print("Track record: Alpha Arcade lookup failed (%s)" % err)

    done = st.setdefault("done", {})                 # keys already scored (so a contract is never counted twice)
    settled = paid = voided = gaveup = 0
    for k in due:
        v = st["open"][k]
        r = res.get(k.split("|")[1])
        if r is None:
            if now > ts(v["c"]) + GIVE_UP_DAYS * 86400:
                del st["open"][k]
                done[k] = int(now)
                gaveup += 1
            else:
                v["nx"] = now + RECHECK_SECS
            continue
        del st["open"][k]
        done[k] = int(now)
        if r == "void":
            voided += 1
            continue
        won = (r == "yes") == (v["s"] == "Yes")
        g = st["agg"].setdefault("daily price" if v["px"] else bucket(v["d"]), {"n": 0, "won": 0, "pl": 0.0})
        g["n"] += 1
        g["won"] += won
        g["pl"] += v["r"] / 100 if won else -1.0       # $1 in at our listed price (fee included): +return or -$1
        settled += 1
        paid += won
        if not won:
            st["misses"].insert(0, {"t": v["t"], "o": v["o"], "s": v["s"], "a": v["a"], "c": datetime.now(timezone.utc).strftime("%Y-%m-%d"),   # the day we saw it settle (some settle early)
                                    "u": v["u"], "d": round(v["d"]), "px": v["px"]})
    st["misses"] = st["misses"][:25]
    for k in [k for k, t in done.items() if now - t > 200 * 86400]:   # forget scored keys after 200 days (longest window is 180)
        del done[k]

    summ = {"started": st["started"], "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "waiting": sum(1 for v in st["open"].values() if not v["px"]),
            "waiting_daily": sum(1 for v in st["open"].values() if v["px"]), "groups": {}}
    for name, g in st["agg"].items():
        summ["groups"][name] = {"n": g["n"], "won": g["won"], "pct": round(100 * g["won"] / g["n"], 1) if g["n"] else None,
                                "ret": round(100 * g["pl"] / g["n"], 2) if g["n"] else None}
    main_g = [g for n, g in st["agg"].items() if n != "daily price"]
    n_all = sum(g["n"] for g in main_g)
    summ["all"] = {"n": n_all, "won": sum(g["won"] for g in main_g),
                   "pct": round(100 * sum(g["won"] for g in main_g) / n_all, 1) if n_all else None,
                   "ret": round(100 * sum(g["pl"] for g in main_g) / n_all, 2) if n_all else None}
    st["summary"] = summ
    json.dump(st, open("track.json", "w"), separators=(",", ":"))
    print("Track record: %d new listed, %d checked, %d settled (%d paid out, %d void), %d gave up, %d waiting; "
          "all-time %s" % (new, len(due), settled, paid, voided, gaveup, len(st["open"]), summ["all"]))


if __name__ == "__main__":
    main()
