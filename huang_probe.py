import json, time, urllib.parse, urllib.request
from datetime import datetime, timezone
UA = {"User-Agent": "AlphaIntelDesk/1.0 (+https://alphainteldesk.com)", "Accept": "application/json"}
def get(u):
    for i in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=30) as r: return json.loads(r.read())
        except Exception as e: print("fail", u[:100], e); time.sleep(1 + i)
iso = lambda s: datetime.fromtimestamp(s, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
V2 = "https://data-api.polymarket.com/v2"
s = get("https://gamma-api.polymarket.com/public-search?" + urllib.parse.urlencode({"q": "Jensen Huang", "limit_per_type": 40, "events_status": "all"})) or {}
evs = [e for e in (s.get("events") or [])]
for e in evs:
    print("EVENT", e.get("slug"), "|", e.get("title"), "| vol", round(float(e.get("volume") or 0)), "| created", e.get("createdAt"))
T0, T1 = datetime(2026, 11, 20, tzinfo=timezone.utc).timestamp(), datetime(2026, 11, 23, 13, 56, tzinfo=timezone.utc).timestamp()
for e in evs:
    t = (e.get("title") or "").lower()
    if not any(k in t for k in ("return", "rejoin", "next ceo", "reinstat", "back as")): continue
    for m in e.get("markets") or []:
        cid = m.get("conditionId"); rows, cur = [], None
        for _ in range(120):
            q = {"condition_id": cid, "limit": 200}
            if cur: q["cursor"] = cur
            d = get(V2 + "/trades?" + urllib.parse.urlencode(q)) or {}
            r = d.get("data") or []; rows += r; cur = (d.get("pagination") or {}).get("next_cursor")
            if not r or not cur or min(int(x["timestamp"]) for x in r) < T0: break
            time.sleep(0.15)
        yb = [x for x in rows if x.get("outcome") == "Yes" and x.get("side") == "BUY" and T0 <= int(x["timestamp"]) < T1]
        if not yb: continue
        print("MARKET", m.get("question"), "| yes buys pre-announcement", len(yb), "$", round(sum(float(x["size"]) * float(x["price"]) for x in yb)))
        for x in sorted(yb, key=lambda x: -float(x["size"]) * float(x["price"]))[:12]:
            print("   ", iso(int(x["timestamp"])), (x.get("name") or "")[:16], x["proxy_wallet"][:10], "px", round(float(x["price"]), 4), "sh", round(float(x["size"])), "$", round(float(x["size"]) * float(x["price"])))
        for x in yb:
            if "ljhggk" in (x.get("name") or "").lower() + (x.get("pseudonym") or "").lower():
                print("   LJHGGK", iso(int(x["timestamp"])), x["proxy_wallet"], x["price"], x["size"])
print("DONE")
