"""Throwaway (Nov 24, 2026): who bought 'Jensen Huang rejoins NVIDIA' before the Nov 23 reinstatement?
Polymarket trades + wallet ages, Kalshi trades, Alpha Arcade on-chain buyers (owner's own list excluded), price history."""
import json, os, re, time, urllib.parse, urllib.request
from datetime import datetime, timezone
UA = {"User-Agent": "AlphaIntelDesk/1.0 (+https://alphainteldesk.com)", "Accept": "application/json"}
def get(u, t=30):
    for i in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=t) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception as e:
            err = e; time.sleep(1.5 * (i + 1))
    print("  GET failed", u[:120], str(err)[:80]); return None
iso = lambda s: datetime.fromtimestamp(s, timezone.utc).strftime("%Y-%m-%d %H:%M")
OUT = {}
SLUG = "jensen-huang-rejoins-nvidia-byptptpt"
ev = get("https://gamma-api.polymarket.com/events?slug=" + SLUG) or []
if not ev:
    s = get("https://gamma-api.polymarket.com/public-search?q=" + urllib.parse.quote("Jensen Huang rejoins NVIDIA")) or {}
    ev = [e for e in (s.get("events") or []) if "rejoin" in (e.get("title") or "").lower()]
ev = ev[0]
print("EVENT", ev.get("title"), ev.get("slug"), "created", ev.get("createdAt"), "vol", ev.get("volume"))
mk = []
for m in ev.get("markets") or []:
    tok = json.loads(m.get("clobTokenIds") or "[]")
    print("MARKET", m.get("groupItemTitle"), m.get("conditionId"), "closed", m.get("closed"), "prices", m.get("outcomePrices"), "vol", m.get("volume"), "umaStatus", m.get("umaResolutionStatus"))
    mk.append({"label": m.get("groupItemTitle"), "cid": m.get("conditionId"), "yes": tok[0] if tok else None, "no": tok[1] if len(tok) > 1 else None})
OUT["markets"] = mk
# all trades per market (data-api v1, offset paging)
trades = []
for m in mk:
    n = 0
    for off in range(0, 30000, 500):
        rows = get("https://data-api.polymarket.com/trades?" + urllib.parse.urlencode({"market": m["cid"], "limit": 500, "offset": off, "takerOnly": "false"}))
        if not rows:
            break
        for r in rows:
            r["_label"] = m["label"]
        trades += rows; n += len(rows)
        if len(rows) < 500:
            break
        time.sleep(0.3)
    print("TRADES", m["label"], n)
print("TOTAL TRADES", len(trades), "fields", sorted(trades[0].keys()) if trades else None)
json.dump(trades, open("/tmp/pm_trades.json", "w"))
# YES buys (outcome Yes, side BUY) by wallet, Nov 19 - Nov 24
since, until = datetime(2026, 11, 19, tzinfo=timezone.utc).timestamp(), datetime(2026, 11, 24, 6, tzinfo=timezone.utc).timestamp()
yes = [t for t in trades if t.get("outcome") == "Yes" and t.get("side") == "BUY" and since <= int(t["timestamp"]) <= until]
by = {}
for t in yes:
    w = t["proxyWallet"]; usd = float(t["size"]) * float(t["price"])
    b = by.setdefault(w, {"usd": 0, "shares": 0, "n": 0, "first": 1e12, "last": 0, "labels": set(), "name": t.get("name") or t.get("pseudonym") or "", "px": []})
    b["usd"] += usd; b["shares"] += float(t["size"]); b["n"] += 1; b["first"] = min(b["first"], int(t["timestamp"])); b["last"] = max(b["last"], int(t["timestamp"]))
    b["labels"].add(t["_label"]); b["px"].append(float(t["price"]))
# hourly YES buy $ for the Nov 30 + Dec 31 2026 lines
hours = {}
for t in yes:
    h = int(t["timestamp"]) // 3600 * 3600
    hours.setdefault(h, 0); hours[h] += float(t["size"]) * float(t["price"])
print("HOURLY YES-BUY $ (UTC)")
for h in sorted(hours):
    print("  ", iso(h), round(hours[h]))
top = sorted(by.items(), key=lambda kv: -kv[1]["usd"])[:60]
print("TOP YES BUYERS Nov19-24 (wallet, $, shares, n, first, last, labels, avgpx, first-ever trade, total trades)")
rows = []
for w, b in top:
    hist = get("https://data-api.polymarket.com/activity?" + urllib.parse.urlencode({"user": w, "limit": 500, "sortDirection": "ASC", "sortBy": "TIMESTAMP"})) or []
    first = min([int(x.get("timestamp") or 9e12) for x in hist] or [0])
    tr = get("https://data-api.polymarket.com/trades?" + urllib.parse.urlencode({"user": w, "limit": 500})) or []
    mk_n = len({x.get("conditionId") for x in tr})
    pos = get("https://data-api.polymarket.com/positions?" + urllib.parse.urlencode({"user": w, "limit": 50})) or []
    huang_pos = [(p.get("title"), p.get("outcome"), round(float(p.get("currentValue") or 0)), round(float(p.get("cashPnl") or 0))) for p in pos if "Huang" in (p.get("title") or "")]
    avg = sum(b["px"]) / len(b["px"])
    r = {"w": w, "name": b["name"], "usd": round(b["usd"]), "shares": round(b["shares"]), "n": b["n"], "first_buy": iso(b["first"]), "last_buy": iso(b["last"]),
         "labels": sorted(b["labels"]), "avg_px": round(avg, 3), "wallet_first": iso(first) if first else "?", "acts": len(hist), "trades_500": len(tr), "markets": mk_n, "huang_pos": huang_pos}
    rows.append(r); print(" ", json.dumps(r)); time.sleep(0.3)
OUT["pm_top_yes"] = rows
# price history per YES token
OUT["history"] = {}
for m in mk:
    if not m["yes"]:
        continue
    h = get("https://clob.polymarket.com/prices-history?" + urllib.parse.urlencode({"market": m["yes"], "startTs": int(datetime(2026, 11, 12, tzinfo=timezone.utc).timestamp()), "endTs": int(time.time()), "fidelity": 60})) or {}
    pts = h.get("history") or []
    OUT["history"][m["label"]] = pts
    print("HISTORY", m["label"], len(pts), [(iso(p["t"]), p["p"]) for p in pts[-200:] if p["t"] > datetime(2026, 11, 21, tzinfo=timezone.utc).timestamp()][:120])
# Kalshi: find Huang markets
K = "https://api.elections.kalshi.com/trade-api/v2"
found = []
for st in ("open", "closed", "settled"):
    cur = None
    for _ in range(40):
        d = get(K + "/events?" + urllib.parse.urlencode({"status": st, "limit": 200, **({"cursor": cur} if cur else {})})) or {}
        for e in d.get("events") or []:
            if "huang" in (e.get("title") or "").lower() or "nvidia ceo" in (e.get("title") or "").lower() or "nvidia" in (e.get("series_ticker") or "").lower():
                found.append(e)
        cur = d.get("cursor")
        if not cur:
            break
        time.sleep(0.2)
print("KALSHI EVENTS", [(e.get("event_ticker"), e.get("title")) for e in found])
for e in found:
    d = get(K + "/markets?" + urllib.parse.urlencode({"event_ticker": e["event_ticker"], "limit": 100})) or {}
    for m in d.get("markets") or []:
        print("  K MARKET", m.get("ticker"), m.get("title"), m.get("yes_sub_title"), "last", m.get("last_price_dollars") or m.get("last_price"), "vol", m.get("volume"), "status", m.get("status"), "result", m.get("result"))
        if not re.search(r"huang|rejoin|return", json.dumps(m), re.I):
            continue
        tr = get(K + "/markets/trades?" + urllib.parse.urlencode({"ticker": m["ticker"], "limit": 1000, "min_ts": int(since)})) or {}
        big = []
        for t in tr.get("trades") or []:
            side = (t.get("taker_side") or "yes").lower(); px = float(t.get(side + "_price_dollars") or 0)
            usd = float(t.get("count_fp") or t.get("count") or 0) * px
            big.append((t.get("created_time"), side, round(px, 3), round(usd)))
        big.sort()
        print("    K TRADES", len(big), "yes-taker $ by hour:")
        hh = {}
        for c, s, p, u in big:
            if s == "yes":
                hh[c[:13]] = hh.get(c[:13], 0) + u
        for k in sorted(hh):
            print("      ", k, hh[k])
        print("    K BIG (>= $500):", [b for b in big if b[3] >= 500][:80])
# Alpha Arcade: on-chain buyers of the three option apps (owner's list excluded, short ids only)
EX = [re.sub(r"[^a-z0-9]", "", x.lower()) for x in (os.environ.get("TRADERS_EXCLUDE") or "").split(",") if len(x) >= 4]
IDX = "https://mainnet-idx.algonode.cloud/v2"
apps = {"November 30, 2026": 3774018522, "December 31, 2026": 3774018651, "December 31, 2027": 3774018815}
for lab, app in apps.items():
    snd, nxt = {}, None
    for _ in range(20):
        d = get(IDX + "/transactions?" + urllib.parse.urlencode({"application-id": app, "limit": 1000, **({"next": nxt} if nxt else {})})) or {}
        for t in d.get("transactions") or []:
            s = t.get("sender"); rt = t.get("round-time") or 0
            x = snd.setdefault(s, [1e12, 0, 0]); x[0] = min(x[0], rt); x[1] = max(x[1], rt); x[2] += 1
        nxt = d.get("next-token")
        if not nxt or not d.get("transactions"):
            break
    print("ALPHA", lab, app, "senders", len(snd))
    for s, (f, l, n) in sorted(snd.items(), key=lambda kv: -kv[1][1]):
        if any(e and e in s.lower() for e in EX):
            print("    (excluded wallet)"); continue
        acct = get(IDX + "/accounts/" + s + "?exclude=all") or {}
        cr = (acct.get("account") or {}).get("created-at-round")
        crt = None
        if cr:
            b = get(IDX + "/blocks/" + str(cr)) or {}
            crt = b.get("timestamp")
        wt = get("https://api.alphaarcade.com/api/get-wallet-trades?" + urllib.parse.urlencode({"wallet": s})) or {}
        mine = [x for x in (wt.get("trades") or []) if "rejoin" in str(x.get("marketTitle") or "").lower() or "rejoin" in str(x.get("slug") or "").lower()]
        allt = wt.get("trades") or []
        def money(x):
            amt, px = float(x.get("totalAmount") or 0), float(x.get("pricePerShare") or 0)
            micro = px > 1.5
            return (round(amt / 1e6 if micro else amt, 2), round(px / 1e6 if micro else px, 3))
        if any(e and e in re.sub(r"[^a-z0-9]", "", json.dumps(wt).lower()) for e in EX):
            print("    (excluded wallet)"); continue
        print("   ", s[:4] + "…" + s[-2:], "app calls", n, "first", iso(f), "last", iso(l), "acct created", iso(crt) if crt else "?", "alpha trades", len(allt),
              "rejoin trades", [(x.get("createdAt"), x.get("type"), x.get("position"), x.get("marketTitle"), money(x)) for x in mine][:12])
        time.sleep(0.3)
json.dump(OUT, open("/tmp/huang_out.json", "w"), default=list)
print("DONE")
