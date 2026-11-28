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


LQ, RL, LET = {"A": 4, "B": 3, "C": 2, "D": 1}, {"clear": 4, "mixed": 3, "none": 2, "judgement": 1}, ["", "D", "C", "B", "A"]


def grades(x):
    """Nov 17 (James): the DZ Grade when we listed it (same maths as the page: Liquidity + Rules, rounded toward the weaker),
    so the track record can show whether A contracts really pay out more often than C's. "-" = not graded (e.g. Alpha)."""
    e, r = x.get("ex"), x.get("st") or {}
    lg = (e.get("g") if e.get("usd") else "D") if e else None
    rg = LET[RL[r["g"]]] if r.get("g") in RL else None
    g = LET[(LQ[lg] + RL[r["g"]]) // 2] if lg and rg else "-"
    return {"g": g, "lg": lg or "-", "rg": rg or "-"}


RESULT_COLS = ["site", "title", "outcome", "side", "price", "days", "close", "g", "liq", "rules", "g2", "type_g", "flip_g",
               "type", "story", "chop_max", "won", "settled_at"]


def grades2(x):
    """Nov 27 (James): DZ Grade v2 (Liquidity + Rules + Type + Flip risk, dz_grade.py) as listed, plus its parts."""
    z = x.get("dz") or {}
    if not z.get("g"):
        return {}
    p = z.get("parts") or {}
    return {"g2": z["g"], "tg": p.get("type", "-"), "fg": p.get("flip", "-"), "ty": z.get("type") or "",
            "sto": (x.get("story") or {}).get("name") or ""}


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
    from short_crypto import short_crypto            # Nov 21 (James): weekly/daily crypto price contracts are not counted
    sc = [k for k, v in st["open"].items() if short_crypto(v["t"])]
    for k in sc:
        del st["open"][k]
    st["misses"] = [m for m in st["misses"] if not short_crypto(m["t"])]
    rows = [x for x in rows if not short_crypto(x.get("title"))]
    if sc:
        print("Track record: dropped %d weekly/daily crypto contracts still waiting" % len(sc))

    new = 0                                    # 1. log contracts the first time we list them
    for x in rows:
        if x.get("site") not in ("polymarket", "kalshi", "alpha") or not x.get("id"):
            continue
        k = "%s|%s|%s" % (x["site"], x["id"], x["side"])
        sw = (x.get("ch") or {}).get("sw")              # Nov 22 (James): Chop = 48h swing; keep the biggest seen while listed
        if k in st["open"]:
            st["open"][k]["ls"] = now
            if sw is not None:
                st["open"][k]["cm"] = max(sw, st["open"][k].get("cm", 0))
            if "g" not in st["open"][k]:              # Nov 17: contracts logged before grades were saved get today's grade
                st["open"][k].update(grades(x), gl=1)
            if "g2" not in st["open"][k] and x.get("dz"):   # Nov 27: same for DZ Grade v2 (marked g2l = graded later)
                st["open"][k].update(grades2(x), g2l=1)
            continue
        if k in st.get("done", {}):
            continue
        st["open"][k] = {"t": x["title"], "o": x["outcome"], "s": x["side"], "a": x["ask"], "f": x["fee"],
                         "r": x["ret"], "c": x["close"], "d": x["days"], "u": x["url"], "fs": now, "ls": now,
                         "px": bool(x["days"] < 3 and PX.search(x["title"] + " " + (x.get("cat") or "")))}
        st["open"][k].update(grades(x))
        st["open"][k].update(grades2(x))
        if sw is not None:
            st["open"][k].update(ch=sw, cm=sw)
        new += 1

    for x in json.load(open("expiry.json")).get("all") or []:   # Nov 17: grade older entries from the full list too
        if x.get("id"):
            v = st["open"].get("%s|%s|%s" % (x.get("site"), x["id"], x.get("side")))
            if v is not None and "g" not in v:
                v.update(grades(x), gl=1)

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
        if not v["px"] and v.get("g"):            # Nov 17: results by DZ Grade at listing ("-" = not graded)
            gg = st.setdefault("by_grade", {}).setdefault(v["g"], {"n": 0, "won": 0, "pl": 0.0})
            gg["n"] += 1
            gg["won"] += won
            gg["pl"] += v["r"] / 100 if won else -1.0
        if not v["px"] and "cm" in v:             # Nov 22: results by Chop (any 48h swing of 10c+ while listed), not shown
            cg = st.setdefault("by_chop", {}).setdefault("choppy" if v["cm"] >= 10 else "steady", {"n": 0, "won": 0, "pl": 0.0})
            cg["n"] += 1                          # on the page yet: checked once there are 30+ results
            cg["won"] += won
            cg["pl"] += v["r"] / 100 if won else -1.0
        cost = v["a"] + (v.get("f") or 0)                # Nov 27: what you paid per contract, for the break-even line
        if not v["px"] and v.get("g2"):           # Nov 27: results by DZ Grade v2, by market type and by flip risk
            for name, key in (("by_grade2", v["g2"]), ("by_type", v.get("ty") or "?"), ("by_flip", v.get("fg") or "-")):
                a = st.setdefault(name, {}).setdefault(key, {"n": 0, "won": 0, "pl": 0.0, "cost": 0.0})
                a["n"] += 1
                a["won"] += won
                a["pl"] += v["r"] / 100 if won else -1.0
                a["cost"] += cost
        if not v["px"]:                           # Nov 27 (James): keep every settled contract with its details, so we can
            st.setdefault("results", []).insert(0, [   # test which signals really predict a miss (only totals were kept)
                k.split("|")[0], v["t"][:60], v["o"][:30], v["s"], v["a"], round(v["d"], 1), v["c"][:10], v.get("g"), v.get("lg"),
                v.get("rg"), v.get("g2"), v.get("tg"), v.get("fg"), v.get("ty"), v.get("sto"), v.get("cm"), int(won), int(now)])
        settled += 1
        paid += won
        if not won:
            st["misses"].insert(0, {"t": v["t"], "o": v["o"], "s": v["s"], "a": v["a"], "c": datetime.now(timezone.utc).strftime("%Y-%m-%d"),   # the day we saw it settle (some settle early)
                                    "u": v["u"], "d": round(v["d"]), "px": v["px"]})
    st["misses"] = st["misses"][:25]
    st["results"] = (st.get("results") or [])[:1500]   # columns: RESULT_COLS
    st["result_cols"] = RESULT_COLS
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
    summ["by_grade"] = {k: {"n": g["n"], "won": g["won"], "pct": round(100 * g["won"] / g["n"], 1),
                            "ret": round(100 * g["pl"] / g["n"], 2)} for k, g in sorted((st.get("by_grade") or {}).items()) if g["n"]}
    summ["by_chop"] = {k: {"n": g["n"], "won": g["won"], "pct": round(100 * g["won"] / g["n"], 1),
                           "ret": round(100 * g["pl"] / g["n"], 2)} for k, g in sorted((st.get("by_chop") or {}).items()) if g["n"]}
    rnd = lambda g: {"n": g["n"], "won": g["won"], "pct": round(100 * g["won"] / g["n"], 1), "ret": round(100 * g["pl"] / g["n"], 2),
                     "be": round(g["cost"] / g["n"], 1)}       # be = average price paid incl. fee = the % you need to break even
    for name in ("by_grade2", "by_type", "by_flip"):
        summ[name] = {k: rnd(g) for k, g in sorted((st.get(name) or {}).items()) if g["n"]}
    summ["waiting_by_grade2"] = dict(__import__("collections").Counter(v.get("g2", "?") for v in st["open"].values() if not v["px"]))
    summ["waiting_by_grade"] = dict(__import__("collections").Counter(v.get("g", "?") for v in st["open"].values() if not v["px"]))
    if st.get("removed"):
        summ["removed"] = st["removed"]               # Nov 21: results taken out (shown on the page, so it's open about it)
    st["summary"] = summ
    json.dump(st, open("track.json", "w"), separators=(",", ":"))
    print("Track record: %d new listed, %d checked, %d settled (%d paid out, %d void), %d gave up, %d waiting; "
          "all-time %s" % (new, len(due), settled, paid, voided, gaveup, len(st["open"]), summ["all"]))


if __name__ == "__main__":
    main()
