"""Gas Watch (Nov 24, 2026, James): US pump prices by region + where they're heading, for traders of gas-price markets.

  EIA weekly retail survey (every Monday, free): US average + 5 regions (East Coast, Midwest, Gulf Coast, Rockies, West Coast)
  AAA national average (daily): what Kalshi's gas markets settle on
  RBOB gasoline futures (Yahoo, ~15 min delay): moves days before pump prices -> "pump pressure"
  Gas-price markets on Kalshi, Polymarket and Alpha Arcade
Writes gas.json. Every source is optional: if one fails, the last good reading is kept.
"""
import io, json, re, time, urllib.parse, urllib.request
from datetime import datetime, timezone, timedelta

NOW = time.time()
UA = {"User-Agent": "Mozilla/5.0 (compatible; AlphaIntelDesk/1.0; +https://alphainteldesk.com)"}


def get(url, timeout=30, raw=False):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
            b = r.read()
        return b if raw else json.loads(b)
    except Exception as e:
        print("  GAS feed failed:", url[:90], str(e)[:80])
        return None


try:
    prev = json.load(open("gas.json"))
except Exception:
    prev = {}
out = dict(prev)

# ---------------------------------------------------------------- 1. EIA weekly regional prices (refresh every 6 h)
REG = [("us", "U.S."), ("east", "East Coast"), ("midwest", "Midwest"), ("gulf", "Gulf Coast"),
       ("rockies", "Rocky Mountain"), ("west", "West Coast"), ("california", "California")]
if NOW - (prev.get("eia") or {}).get("at", 0) > 6 * 3600:
    b = get("https://www.eia.gov/petroleum/gasdiesel/xls/pswrgvwall.xls", 60, raw=True)
    try:
        import xlrd
        wb = xlrd.open_workbook(file_contents=b)
        cols = {}
        for sh in wb.sheets():
            if sh.nrows < 5:
                continue
            hdr = [str(sh.cell_value(2, c)) for c in range(sh.ncols)]
            for c, h in enumerate(hdr):
                if "Regular All Formulations Retail Gasoline" not in h:
                    continue
                for k, name in REG:
                    if re.search(r"Weekly " + re.escape(name) + r" Regular All", h) and k not in cols:
                        cols[k] = (sh, c)
        series = {}
        for k, (sh, c) in cols.items():
            pts = []
            for r in range(3, sh.nrows):
                d, v = sh.cell_value(r, 0), sh.cell_value(r, c)
                if isinstance(d, float) and isinstance(v, float):
                    pts.append((xlrd.xldate_as_datetime(d, wb.datemode).strftime("%Y-%m-%d"), round(v, 3)))
            series[k] = pts[-60:]
        if series.get("us"):
            out["eia"] = {"at": NOW, "week": series["us"][-1][0],
                          "now": {k: v[-1][1] for k, v in series.items() if v},
                          "week_ago": {k: v[-2][1] for k, v in series.items() if len(v) > 1},
                          "year_ago": {k: v[-53][1] for k, v in series.items() if len(v) > 52},
                          "series": {k: v[-26:] for k, v in series.items()}}
            print("GAS EIA:", out["eia"]["week"], out["eia"]["now"])
        else:
            print("  GAS EIA: no regional columns found", [str(s.name) for s in wb.sheets()][:12])
    except Exception as e:
        print("  GAS EIA parse failed:", str(e)[:120])

# ---------------------------------------------------------------- 2. AAA national average (refresh hourly)
if NOW - (prev.get("aaa") or {}).get("at", 0) > 3600:
    b = get("https://gasprices.aaa.com/", 30, raw=True)
    if b:
        t = b.decode("utf-8", "ignore")
        m = re.search(r"National Average[^$]{0,200}\$\s*([0-9]\.[0-9]{2,3})", t, re.S)
        if m:
            out["aaa"] = {"at": NOW, "price": float(m.group(1))}
            print("GAS AAA:", m.group(1))
        else:
            print("  GAS AAA: price not found (page %d bytes)" % len(t))

# ---------------------------------------------------------------- 3. RBOB gasoline futures -> pump pressure (every run)
d = get("https://query1.finance.yahoo.com/v8/finance/chart/RB%3DF?range=1mo&interval=1d")
try:
    r = d["chart"]["result"][0]
    cl = [c for c in r["indicators"]["quote"][0]["close"]]
    ts = r["timestamp"]
    pts = [(datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d"), round(c, 4)) for t, c in zip(ts, cl) if c]
    px = float(r["meta"]["regularMarketPrice"])
    prevc = float(r["meta"].get("chartPreviousClose") or pts[-2][1])
    five = pts[-6][1] if len(pts) >= 6 else pts[0][1]
    out["rbob"] = {"price": round(px, 4), "chg1d": round((px - pts[-2][1]) * 100, 1) if len(pts) > 1 else None,
                   "chg5d": round((px - five) * 100, 1), "series": pts[-22:]}
    # Retail follows wholesale with a lag of about 1-2 weeks; a 10¢+ futures move over 5 days is a strong push
    c5 = out["rbob"]["chg5d"]
    out["pressure"] = {"cents": c5, "dir": "up" if c5 >= 3 else "down" if c5 <= -3 else "flat",
                       "strength": min(1.0, abs(c5) / 10)}
    print("GAS RBOB: $%.3f, 1d %+.1f¢, 5d %+.1f¢" % (px, out["rbob"]["chg1d"] or 0, c5))
except Exception as e:
    print("  GAS RBOB failed:", str(e)[:80])

# ---------------------------------------------------------------- 4. gas-price markets (every run)
mk = []
for series in ("KXAAAGASW", "KXAAAGASM", "KXAAAGASD"):
    d = get("https://api.elections.kalshi.com/trade-api/v2/markets?status=open&limit=60&series_ticker=" + series)
    for m in (d or {}).get("markets") or []:
        yes = None
        for k in ("last_price_dollars", "yes_bid_dollars"):          # Kalshi now sends prices as dollar strings
            try:
                yes = round(float(m[k]) * 100, 1) if m.get(k) not in (None, "") and float(m[k]) > 0 else yes
            except (TypeError, ValueError):
                pass
            if yes:
                break
        if yes is None and isinstance(m.get("last_price"), (int, float)) and m["last_price"] > 0:
            yes = m["last_price"]
        try:
            vol = round(float(m.get("volume_24h_fp") or m.get("volume_24h") or 0))
        except (TypeError, ValueError):
            vol = 0
        mk.append({"site": "kalshi", "title": {"KXAAAGASW": "US gas price (AAA) at the end of this week", "KXAAAGASM": "US gas price (AAA) at the end of the month",
                                               "KXAAAGASD": "US gas price (AAA) tomorrow"}[series], "sub": m.get("yes_sub_title") or m.get("subtitle"),
                   "price": yes, "vol": vol, "close": m.get("close_time"),
                   "url": "https://kalshi.com/markets/" + series.lower() + "/" + (m.get("event_ticker") or "").lower()})
d = get("https://gamma-api.polymarket.com/public-search?" + urllib.parse.urlencode({"q": "gas prices", "limit_per_type": 10}))
for ev in (d or {}).get("events") or []:
    if ev.get("closed") or not re.search(r"\bgas(oline)? price", ev.get("title") or "", re.I):
        continue
    for m in ev.get("markets") or []:
        if m.get("closed"):
            continue
        try:
            yes = round(float(json.loads(m.get("outcomePrices") or "[]")[0]) * 100, 1)
        except Exception:
            yes = None
        mk.append({"site": "polymarket", "title": ev.get("title"), "sub": m.get("groupItemTitle") or m.get("question"),
                   "price": yes, "vol": round(float(m.get("volume24hr") or 0)), "close": m.get("endDate"),
                   "url": "https://polymarket.com/event/" + (ev.get("slug") or "")})
try:
    for m in json.load(open("alpha_live.json")).get("markets") or []:
        if not m.get("hidden") and re.search(r"\bgas(oline)?\b.*\$|\bgas prices?\b", m.get("title") or "", re.I):
            o = sorted(m.get("options") or [], key=lambda x: -(x.get("yesProb") or 0))
            mk.append({"site": "alpha", "title": m["title"], "sub": o[0]["label"] if len(o) > 1 else None,
                       "price": round(o[0]["yesProb"] / 1e4, 1) if o and o[0].get("yesProb") is not None else None,
                       "vol": round(m.get("twentyFourHrVolume") or 0), "close": None,
                       "url": "https://www.alphaarcade.com/market/" + (m.get("slug") or "")})
except Exception as e:
    print("  GAS alpha failed:", str(e)[:80])
# one row per market (event): its most likely outcome, closing soonest first
ev = {}
for x in mk:
    e = ev.setdefault(x["url"], {"site": x["site"], "title": x["title"], "close": x["close"], "url": x["url"], "n": 0, "vol": 0, "opts": []})
    e["n"] += 1; e["vol"] += x["vol"] or 0
    if x["price"] is not None:
        e["opts"].append((x["sub"], x["price"]))
for e in ev.values():
    th = [(float(re.search(r"[\d.]+", o[0]).group()), o[1]) for o in e["opts"] if o[0] and re.match(r"Above", o[0]) and re.search(r"[\d.]+", o[0])]
    if th:                                            # Kalshi ladder "Above $X": the market's expected level = highest X still at 50¢+
        th.sort(); yes50 = [t for t in th if t[1] >= 50]
        t = yes50[-1] if yes50 else th[0]
        e["lead"] = {"sub": "Above $%.2f" % t[0], "price": t[1]}
    elif e["opts"]:
        o = max(e["opts"], key=lambda o: o[1]); e["lead"] = {"sub": o[0], "price": o[1]}
    del e["opts"]
evs = sorted(ev.values(), key=lambda e: (e["close"] or "9999", -e["vol"]))
if evs:
    out["markets"] = evs[:12]
print("GAS markets:", {s: sum(1 for x in mk if x["site"] == s) for s in ("kalshi", "polymarket", "alpha")})

out["updated"] = datetime.fromtimestamp(NOW, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
out["sources"] = ("Weekly prices: U.S. Energy Information Administration · National average: AAA · "
                  "Gasoline futures (RBOB): Yahoo Finance, delayed · Markets: Kalshi, Polymarket, Alpha Arcade")
json.dump(out, open("gas.json", "w"), separators=(",", ":"))
