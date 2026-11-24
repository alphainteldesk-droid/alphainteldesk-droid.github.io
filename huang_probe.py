"""Throwaway (Nov 24): Polymarket trades on 'Jensen Huang rejoins NVIDIA by...?' via data-api v2; wallet ages."""
import json, time, urllib.parse, urllib.request
from datetime import datetime, timezone
UA = {"User-Agent": "AlphaIntelDesk/1.0 (+https://alphainteldesk.com)", "Accept": "application/json"}
def raw(u, t=30):
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=t) as r:
            return r.status, json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:200]
    except Exception as e:
        return 0, str(e)[:100]
def get(u):
    for i in range(3):
        s, d = raw(u)
        if s == 200: return d
        time.sleep(1 + i)
    return None
iso = lambda s: datetime.fromtimestamp(s, timezone.utc).strftime("%Y-%m-%d %H:%M")
V2 = "https://data-api.polymarket.com/v2"
CIDS = {"Nov 30, 2026": "0x6368d1c0daed920fb7cb4444636b605e8b02d700dfdf70bba2758a7c0c4054cb",
        "Dec 31, 2026": "0x27748e74503ff93d998d1e857980c43eca77c38efd61f642dd43d41a18525250",
        "Dec 31, 2027": "0x79a7b7c58effc4f2753011fb78f44ff59d1912eddc62f4a4ad16f7adda09eb81",
        "Mar 31, 2027": "0xf29406bd9f45effb17a902125a7480b9e15fdc7c24f1a897f543ed3799876be6"}
c0 = CIDS["Nov 30, 2026"]
for name, u in [("v2 market", V2 + "/trades?market=" + c0 + "&limit=5"), ("v2 condition_id", V2 + "/trades?condition_id=" + c0 + "&limit=5"),
                ("v2 conditionId", V2 + "/trades?conditionId=" + c0 + "&limit=5"), ("v2 markets", V2 + "/trades?markets=" + c0 + "&limit=5"),
                ("v2 activity", V2 + "/activity?user=0x0000000000000000000000000000000000000001&limit=5"), ("v1 activity", "https://data-api.polymarket.com/activity?user=0x0000000000000000000000000000000000000001&limit=5"),
                ("v2 plain", V2 + "/trades?limit=2")]:
    s, d = raw(u)
    print("PROBE", name, s, (json.dumps(d)[:600] if s == 200 else d))
# find a working market filter
param = None
for p in ("market", "condition_id", "conditionId", "markets"):
    s, d = raw(V2 + "/trades?" + p + "=" + c0 + "&limit=50")
    rows = (d.get("data") if isinstance(d, dict) else d) if s == 200 else None
    if rows and all((r.get("condition_id") or r.get("conditionId")) == c0 for r in rows):
        param = p; break
print("PARAM", param)
if not param:
    raise SystemExit
trades = []
for lab, cid in CIDS.items():
    cur, n = None, 0
    for _ in range(200):
        q = {param: cid, "limit": 200}
        if cur: q["cursor"] = cur
        d = get(V2 + "/trades?" + urllib.parse.urlencode(q)) or {}
        rows = d.get("data") or []
        for r in rows: r["_label"] = lab
        trades += rows; n += len(rows)
        cur = (d.get("pagination") or {}).get("next_cursor")
        if not rows or not cur: break
        if min(int(r.get("timestamp") or 0) for r in rows) < datetime(2026, 11, 18, tzinfo=timezone.utc).timestamp(): break
        time.sleep(0.2)
    print("TRADES", lab, n)
print("FIELDS", sorted(trades[0].keys()) if trades else None)
print("SAMPLE", json.dumps(trades[0])[:700] if trades else None)
W = lambda r: r.get("proxy_wallet") or r.get("proxyWallet")
A = datetime(2026, 11, 23, 13, 30, tzinfo=timezone.utc).timestamp()   # approx. announcement; checked against price jump
since = datetime(2026, 11, 20, tzinfo=timezone.utc).timestamp()
yes = [r for r in trades if str(r.get("outcome")).lower() == "yes" and str(r.get("side")).upper() == "BUY" and since <= int(r["timestamp"]) < A]
print("YES BUYS Nov20 -> announcement", len(yes), "usd", round(sum(float(r["size"]) * float(r["price"]) for r in yes)))
hrs = {}
for r in yes:
    h = int(r["timestamp"]) // 3600 * 3600; hrs[h] = hrs.get(h, 0) + float(r["size"]) * float(r["price"])
for h in sorted(hrs): print("  HOUR", iso(h), round(hrs[h]))
# first jump trades after announcement for timing
post = sorted([r for r in trades if int(r["timestamp"]) >= datetime(2026, 11, 23, 12, tzinfo=timezone.utc).timestamp() and int(r["timestamp"]) < datetime(2026, 11, 23, 15, tzinfo=timezone.utc).timestamp() and r["_label"] == "Nov 30, 2026"], key=lambda r: int(r["timestamp"]))
print("NOV30 TRADES 12-15 UTC Nov 23 (time, side, outcome, price, size):")
for r in post[:400]:
    if float(r["size"]) * float(r["price"]) >= 50: print("  ", iso(int(r["timestamp"])) + ":%02d" % (int(r["timestamp"]) % 60), r["side"], r["outcome"], r["price"], round(float(r["size"])))
by = {}
for r in yes:
    b = by.setdefault(W(r), {"usd": 0, "sh": 0, "n": 0, "f": 1e12, "l": 0, "lab": set(), "px": [], "name": r.get("name") or r.get("pseudonym") or ""})
    u = float(r["size"]) * float(r["price"]); b["usd"] += u; b["sh"] += float(r["size"]); b["n"] += 1
    b["f"] = min(b["f"], int(r["timestamp"])); b["l"] = max(b["l"], int(r["timestamp"])); b["lab"].add(r["_label"]); b["px"].append(float(r["price"]))
print("BUYERS", len(by))
out = []
for w, b in sorted(by.items(), key=lambda kv: -kv[1]["usd"])[:50]:
    hist, cur, pages = [], None, 0
    while pages < 6:
        q = {"user": w, "limit": 200}
        if cur: q["cursor"] = cur
        d = get(V2 + "/trades?" + urllib.parse.urlencode(q)) or {}
        rows = d.get("data") or []; hist += rows; pages += 1
        cur = (d.get("pagination") or {}).get("next_cursor")
        if not rows or not cur: break
    first = min([int(x.get("timestamp") or 9e12) for x in hist] or [0])
    mk = {(x.get("title") or x.get("slug") or x.get("condition_id")) for x in hist}
    nv = sum(1 for m in mk if m and ("huang" in str(m).lower() or "nvidia" in str(m).lower()))
    r = {"w": w, "name": b["name"], "usd": round(b["usd"]), "shares": round(b["sh"]), "n": b["n"], "first_buy": iso(b["f"]), "last_buy": iso(b["l"]),
         "lines": sorted(b["lab"]), "avg_px": round(sum(b["px"]) / len(b["px"]), 4), "wallet_first_trade": iso(first) if first < 9e12 else "?",
         "hist_trades": len(hist), "hist_capped": bool(cur), "markets": len(mk), "nvidia_markets": nv, "payout_if_yes": round(b["sh"])}
    out.append(r); print("BUYER", json.dumps(r)); time.sleep(0.2)
json.dump({"buyers": out, "hours": {iso(h): round(v) for h, v in hrs.items()}}, open("/tmp/huang_out.json", "w"))
print("DONE")
