"""Fresh Wallets (Nov 14): large trades by brand-new Polymarket wallets on markets that close soon.

Writes  fresh.json        what the site shows: alerts, how each one turned out, the running record
        fresh_state.json  working memory between runs (wallet ages, market details, recent candidate trades)

How it works, in order:
  1. read the newest large BUY trades from Polymarket's public trade feed
  2. keep trades on non-sports markets that close soon
  3. check how old each wallet is (its whole trade history)
  4. after a waiting window, group new wallets that took the same side of the same market into ONE alert
  5. follow every alert until its market settles and record whether that side won

The model's settings come from the FRESH_PARAMS secret (JSON) when it is set, so the live numbers need not be
the ones written here. Polymarket only for now: Kalshi has no wallets, Alpha Arcade has no public feed of
large trades across wallets.
"""
import json
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

P = {"usd": 2500, "close_days": 7, "wallet_days": 30, "wait_min": 10, "max_price": 0.95}
try:
    P.update(json.loads(os.environ.get("FRESH_PARAMS") or "{}"))
except Exception:
    print("Fresh wallets: FRESH_PARAMS is not valid JSON, using the built-in settings")

UA = {"User-Agent": "AlphaIntelDesk/1.0 (+https://alphainteldesk.com)", "Accept": "application/json"}
PM = "https://data-api.polymarket.com/v2"
GAMMA = "https://gamma-api.polymarket.com"
SPORTY = re.compile(r"\bvs\.?\b|^spread:|\bo/u\b|over/under|moneyline|\bgame \d|win on 20\d\d-|\bhandicap\b|"
                    r"\bmap \d|both teams|\btotal (kills|points|goals|runs|sets|games)|^1h |\bset \d|exact score", re.I)
SPORT_TAGS = ("sport", "esports", "soccer", "football", "nfl", "nba", "mls", "nhl", "mlb", "ufc", "tennis", "golf",
              "cricket", "f1", "formula", "boxing", "mma", "rugby", "games", "league of legends", "counter-strike",
              "dota", "valorant", "ncaa", "basketball", "baseball", "hockey")
MAX_PAGES, MAX_WALLET_CHECKS, KEEP_ALERTS, KEEP_DAYS = 10, 40, 300, 120
NOW = time.time()
iso = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get(url, timeout=20):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def ts(s):
    try:
        return datetime.strptime((s or "")[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return 0


def load(path, default):
    try:
        return json.load(open(path))
    except Exception:
        return default


def big_trades(since):
    """Newest first; stop once we are back at `since`."""
    out, cursor = [], None
    for _ in range(MAX_PAGES):
        q = {"limit": 200, "filter_type": "CASH", "filter_amount": P["usd"]}
        if cursor:
            q["cursor"] = cursor
        d = get(PM + "/trades?" + urllib.parse.urlencode(q)) or {}
        rows = d.get("data") or []
        out += rows
        cursor = (d.get("pagination") or {}).get("next_cursor")
        if not rows or not cursor or min(int(r.get("timestamp") or 0) for r in rows) < since:
            break
        time.sleep(0.25)
    seen, uniq = set(), []
    for r in out:
        k = (r.get("transaction_hash"), r.get("proxy_wallet"), r.get("token_id"), r.get("size"))
        if k not in seen and int(r.get("timestamp") or 0) >= since:
            seen.add(k)
            uniq.append(r)
    return uniq


def market_info(cids, cache):
    """condition id -> {end, sport, closed, prices, title, slug}; asks Polymarket only for ids not asked recently."""
    need = [c for c in cids if c and NOW - (cache.get(c) or {}).get("at", 0) > 1500]
    for i in range(0, len(need), 15):
        part = need[i:i + 15]
        try:
            rows = get(GAMMA + "/markets?" + urllib.parse.urlencode(
                [("include_tag", "true"), ("limit", 50)] + [("condition_ids", c) for c in part]))
        except Exception as err:
            print("  Fresh wallets: market lookup failed:", str(err)[:70])
            rows = []
        for m in rows or []:
            tags = " ".join((t.get("label") or "") + " " + (t.get("slug") or "") for t in m.get("tags") or []).lower()
            try:
                prices = [float(x) for x in json.loads(m.get("outcomePrices") or "[]")]
            except (ValueError, TypeError):
                prices = []
            ev = (m.get("events") or [{}])[0] or {}
            cache[m.get("conditionId")] = {
                "at": round(NOW), "end": round(ts(m.get("endDate"))), "closed": bool(m.get("closed")),
                "sport": bool(m.get("sportsMarketType") or m.get("gameStartTime") or any(t in tags for t in SPORT_TAGS)),
                "prices": prices, "title": m.get("question") or "", "event": ev.get("slug") or m.get("slug") or ""}
        time.sleep(0.25)
    return cache


def wallet_age(w, cache):
    """(first trade time, number of trades) for a wallet; 200+ trades = an established account."""
    c = cache.get(w)
    if c and (c["n"] >= 200 or NOW - c["first"] > P["wallet_days"] * 86400 or NOW - c["at"] < 3 * 3600):
        return c
    d = get(PM + "/trades?" + urllib.parse.urlencode({"user": w, "limit": 200})) or {}
    rows = d.get("data") or []
    more = bool((d.get("pagination") or {}).get("has_more")) or len(rows) >= 200
    first = min([int(r.get("timestamp") or NOW) for r in rows] or [NOW])
    c = cache[w] = {"first": 0 if more else round(first), "n": 200 if more else len(rows), "at": round(NOW)}
    return c


def main():
    st = load("fresh_state.json", {})
    pub = load("fresh.json", {})
    wallets, markets, recent = st.get("wallets") or {}, st.get("markets") or {}, st.get("recent") or []
    alerts = pub.get("alerts") or []
    since = max(int(st.get("since") or 0) - 900, int(NOW) - 6 * 3600)

    try:
        trades = big_trades(since)
    except Exception as err:
        print("Fresh wallets: trade feed failed, keeping the last file:", str(err)[:90])
        return
    buys = [t for t in trades if (t.get("side") or "").upper() == "BUY" and not SPORTY.search(t.get("title") or "")
            and float(t.get("price") or 0) <= P["max_price"]]
    market_info(sorted({t.get("condition_id") for t in buys}), markets)

    def closes_soon(cid):
        m = markets.get(cid) or {}
        return m and not m["sport"] and not m["closed"] and NOW < m["end"] <= NOW + P["close_days"] * 86400

    cand = [t for t in buys if closes_soon(t.get("condition_id"))]
    checked = 0
    known = {(r["tx"], r["w"]) for r in recent}
    for t in sorted(cand, key=lambda t: -float(t["size"]) * float(t["price"])):
        w = t.get("proxy_wallet") or ""
        if (t.get("transaction_hash"), w) in known:
            continue
        if w not in wallets and checked >= MAX_WALLET_CHECKS:
            continue
        try:
            if w not in wallets:
                checked += 1
                time.sleep(0.25)
            age = wallet_age(w, wallets)
        except Exception as err:
            print("  Fresh wallets: one wallet lookup failed:", str(err)[:70])
            continue
        if not age["first"] or NOW - age["first"] > P["wallet_days"] * 86400:
            continue
        recent.append({"tx": t.get("transaction_hash"), "w": w, "cid": t["condition_id"], "o": t.get("outcome") or "",
                       "oi": int(t.get("outcome_index") or 0), "ts": int(t["timestamp"]), "px": float(t["price"]),
                       "usd": round(float(t["size"]) * float(t["price"])), "first": age["first"], "n": age["n"],
                       "name": (t.get("name") or t.get("pseudonym") or "").strip()})
    recent = [r for r in recent if NOW - r["ts"] < 24 * 3600]

    # one alert per market side: every new wallet that came in within the waiting window of the first one
    have = {a["id"] for a in alerts}
    groups = {}
    for r in sorted(recent, key=lambda r: r["ts"]):
        groups.setdefault((r["cid"], r["oi"]), []).append(r)
    new = 0
    for (cid, oi), rows in groups.items():
        t0 = rows[0]["ts"]
        aid = "%s-%d-%d" % (cid[2:12], oi, t0)
        if NOW < t0 + P["wait_min"] * 60 or aid in have or any(a["cid"] == cid and a["oi"] == oi and t0 - a["ts"] < 86400 for a in alerts):
            continue
        rows = [r for r in rows if r["ts"] <= t0 + P["wait_min"] * 60]
        m = markets.get(cid) or {}
        usd = sum(r["usd"] for r in rows)
        by = {}
        for r in rows:
            b = by.setdefault(r["w"], {"usd": 0, "first": r["first"], "n": r["n"], "name": r["name"]})
            b["usd"] += r["usd"]
        named = lambda w, b: b["name"] if b["name"] and not re.match(r"0x[0-9a-fA-F]{8}", b["name"]) else w[:6] + "…" + w[-4:]
        alerts.append({
            "id": aid, "cid": cid, "oi": oi, "ts": t0, "when": iso(t0), "site": "Polymarket",
            "title": m.get("title") or "", "outcome": rows[0]["o"], "usd": usd,
            "price": round(sum(r["px"] * r["usd"] for r in rows) / max(usd, 1) * 100, 1),
            "close": iso(m["end"]) if m.get("end") else "", "url": "https://polymarket.com/event/" + (m.get("event") or ""),
            "wallets": [{"name": named(w, b), "url": "https://polymarket.com/profile/" + w, "usd": b["usd"],
                         "age_days": round(max(0, t0 - b["first"]) / 86400, 1), "trades": b["n"]}
                        for w, b in sorted(by.items(), key=lambda kv: -kv[1]["usd"])],
            "now": None, "result": None})
        new += 1

    # follow every open alert: latest price, and the result once the market settles
    open_ids = sorted({a["cid"] for a in alerts if not a.get("result")})
    market_info(open_ids, markets)
    for a in alerts:
        m = markets.get(a["cid"]) or {}
        pr = m.get("prices") or []
        if a.get("result") or a["oi"] >= len(pr):
            continue
        a["now"] = round(pr[a["oi"]] * 100, 1)
        if m.get("closed") and (pr[a["oi"]] >= 0.99 or pr[a["oi"]] <= 0.01):
            a["result"] = "won" if pr[a["oi"]] >= 0.99 else "lost"
            a["settled"] = iso(NOW)
    alerts = sorted([a for a in alerts if NOW - a["ts"] < KEEP_DAYS * 86400], key=lambda a: -a["ts"])[:KEEP_ALERTS]
    done = [a for a in alerts if a.get("result")]
    won = sum(a["result"] == "won" for a in done)
    json.dump({"updated": iso(NOW), "site": "Polymarket",
               "stats": {"alerts": len(alerts), "open": len(alerts) - len(done), "settled": len(done), "won": won},
               "alerts": alerts}, open("fresh.json", "w"), separators=(",", ":"))
    keep = {a["cid"] for a in alerts if not a.get("result")} | {r["cid"] for r in recent}
    json.dump({"since": int(NOW), "recent": recent,
               "wallets": {w: c for w, c in wallets.items() if NOW - c["at"] < 3 * 86400},
               "markets": {c: m for c, m in markets.items() if c in keep or NOW - m["at"] < 6 * 3600}},
              open("fresh_state.json", "w"), separators=(",", ":"))
    print("Fresh wallets: %d large trades read, %d buys outside sports, %d on markets closing soon, %d wallets checked, "
          "%d new-wallet trades in the last 24h, %d new alerts, %d alerts on file (%d settled, %d won)"
          % (len(trades), len(buys), len(cand), checked, len(recent), new, len(alerts), len(done), won))


if __name__ == "__main__":
    main()
