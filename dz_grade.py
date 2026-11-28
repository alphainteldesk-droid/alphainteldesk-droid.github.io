"""Nov 27 (James): Danger Zone grade v2. "Better grades for markets that close."

The first 70 settled results showed the old grade (Liquidity + Rules) barely separated winners from losers, and that 11
of the 12 misses were one of four kinds: count / range markets (tweet counts), price-path markets (how low will Bitcoin
go), one news story taking out several contracts at once (4 Jensen Huang contracts), and live TV votes. So the DZ Grade
now has four parts:

  Liquidity  - can you sell back (exit_grade.py, unchanged)
  Rules      - how the result is decided (match_markets.settle_info, unchanged)
  Type       - what kind of market it is (market_type below)
  Flip risk  - how big the price cushion is against how much the price has been moving (flip below; replaces "Chop")

Combined: the average of the parts, rounded toward the weaker, and a D in Type or Flip risk caps the grade at C (both D
-> D). Every row also gets a "story" (story_keys): contracts that ride on the same news. The top 50 keeps one per story.

Public data only. Nothing here raises: a row that can't be graded keeps no "dz".
"""
import math
import re

N = {"A": 4, "B": 3, "C": 2, "D": 1}
LET = ["", "D", "C", "B", "A"]
RULES = {"clear": "A", "mixed": "B", "none": "C", "judgement": "D"}

# ---------------------------------------------------------------- market type
COUNT = re.compile(r"#\s*(of\s+)?(tweets|posts)|\btweets?\b|truth social|\bposts?\b.*\b(week|month)\b|how many|number of|"
                   r"\bmentions?\b|\bsay\b.*\btimes\b|\bcount\b", re.I)
RANGE_OUT = re.compile(r"^\s*\$?\d[\d,.]*\s*[kKmM]?\s*(-|–|to)\s*\$?\d[\d,.]*", re.I)
PRICE = re.compile(r"bitcoin|\bbtc\b|ethereum|\beth\b|solana|\bxrp\b|dogecoin|\bcrypto\b|\bprices?\b|all[- ]time high|"
                   r"\bhow (low|high)\b|\bclose[sd]? (above|below|at)\b|s&p|nasdaq|\bdow\b|\b(crude|oil|brent|wti)\b.*\b(high|low|hit|close)|\bgold\b|\bsilver\b|"
                   r"treasury|\byield\b|valuation|market cap|\bipo price\b|\bstock\b|\bshares?\b", re.I)
LIVE = re.compile(r"eliminat|voted off|dancing with the stars|the voice|american idol|survivor|big brother|bachelor|"
                  r"love island|traitors|\bepisode\s+\d+", re.I)
OFFICIAL = re.compile(r"\bcpi\b|inflation|jobs report|nonfarm|payrolls|unemployment rate|\bgdp\b|\bfed\b|fomc|"
                      r"interest rate|rate decision|bank of (canada|england|japan)|\becb\b|central bank|\bpce\b", re.I)


def market_type(r):
    """-> (letter, short name, plain-English reason)."""
    t, o = r.get("title") or "", r.get("outcome") or ""
    tc = t + " " + (r.get("cat") or "")
    if LIVE.search(t):
        return "D", "Live vote", "decided by a live vote or a judges' call on the night; these have missed most often for their price"
    if COUNT.search(t) or RANGE_OUT.search(o):
        return "D", "Count or range", "one more post, one more point or a few dollars can flip it; count and range markets are our most common miss"
    if PRICE.search(tc):
        return "D", "Price path", "rides on a price that can move fast (crypto, stocks, commodities); one bad day can end it"
    if OFFICIAL.search(t):
        return "A", "Scheduled official number", "settled by a scheduled official release (a rate decision or a government statistic)"
    return "B", "Event", "an event market: a headline can move it, but nothing about its type stands out"


# ---------------------------------------------------------------- flip risk (replaces Chop)
HORIZON = 30          # days: price moves are scaled to the time left, capped at a month (new information dominates after that)


def flip(r):
    """Cushion (price above 50c, the coin-flip line) against the swing we can expect before it settles.
    Expected swing = the 48h range / sqrt(2) as a daily move, x sqrt(days left, capped at 30). Ratio 3+ = A, 2+ = B,
    1+ = C, under 1 = D. Falling (5c+ under its 48h high now) = one letter worse. No 48h history = no reading."""
    c = r.get("ch")
    if not c or len(c.get("pts") or []) < 4:
        return None
    sw = max(float(c.get("sw") or 0), 1.0)                 # a flat line still gets a 1c floor
    daily = sw / math.sqrt(2)
    expect = daily * math.sqrt(max(0.5, min(r["days"], HORIZON)))
    cushion = r["ask"] - 50
    ratio = cushion / expect if expect else 9
    g = "A" if ratio >= 3 else "B" if ratio >= 2 else "C" if ratio >= 1 else "D"
    pts = c["pts"]
    falling = pts[-1] <= max(pts) - 5
    if falling:
        g = LET[max(1, N[g] - 1)]
    level = {"A": "LOW", "B": "LOW", "C": "MEDIUM", "D": "HIGH"}[g]
    txt = ("%.0f¢ cushion above 50¢ against a likely swing of about %.0f¢ before it settles (it moved %.1f¢ in the last %s)"
           % (cushion, expect, c["sw"], "48h" if c.get("h", 48) >= 46 else "%sh" % c.get("h")))
    if falling:
        txt += "; falling: %.0f¢ under its 48-hour high" % (max(pts) - pts[-1])
    return {"g": g, "lvl": level, "ratio": round(ratio, 2), "falling": falling, "t": txt}


# ---------------------------------------------------------------- stories
# A "story" = a name several contracts ride on. Names come from a short list (countries, leaders, companies, coins,
# central banks) plus people found as "First Last" in normal (not Title Case) titles and outcomes. No chaining: two rows
# are the same story only if they share a name directly, or their titles share 60%+ of their words.
ENT = [(re.compile(p, re.I), k) for p, k in [
    (r"\biran(ian)?\b|hormuz|persian gulf|\birgc\b|khamenei", "Iran"), (r"\bisrael(i)?\b|\bgaza\b|hamas|hezbollah|netanyahu", "Israel"),
    (r"\brussia(n)?\b|kremlin|\bputin\b", "Russia"), (r"\bukrain(e|ian)\b|zelensky|\bkyiv\b", "Ukraine"),
    (r"\btaiwan\b", "Taiwan"), (r"\bchina\b|\bchinese\b|\bxi jinping\b", "China"), (r"venezuela|maduro", "Venezuela"),
    (r"north korea|pyongyang|kim jong", "North Korea"), (r"\bbitcoin\b|\bbtc\b", "Bitcoin"), (r"ethereum|\beth\b", "Ethereum"),
    (r"\bsolana\b", "Solana"), (r"\bcrude\b|\boil\b|\bbrent\b|\bwti\b", "Oil"), (r"\bgold\b", "Gold"),
    (r"\bfed\b|fomc|federal reserve|\bpowell\b", "Fed"), (r"bank of canada", "Bank of Canada"), (r"bank of england", "Bank of England"),
    (r"\becb\b|european central bank", "ECB"), (r"nvidia|jensen huang|\bhuang\b", "Nvidia / Jensen Huang"),
    (r"anthropic|\bclaude\b", "Anthropic"), (r"openai|chatgpt|sam altman", "OpenAI"), (r"\btesla\b", "Tesla"),
    (r"spacex|starship", "SpaceX"), (r"avengers", "Avengers"), (r"\belon\b|\bmusk\b", "Elon Musk"), (r"gamestop", "GameStop"), (r"\bapple\b|iphone", "Apple"),
    (r"hegseth", "Hegseth"), (r"\bvance\b", "JD Vance"), (r"recession", "Recession"), (r"cpi\b|inflation", "Inflation"),
    (r"filibuster", "Filibuster"), (r"shutdown", "Shutdown"), (r"tariff", "Tariffs")]]
STOP = set("""will who what which when where how why the a an and or of in on at by to for from with x vs is be are was
yes no not above below before after between under over end ending next new first last best top highest lowest most
january february march april may june july august september october november december jan feb mar apr jun jul aug sep
sept oct nov dec week month year day today tonight us u.s usa america american trump president administration government
2025 2026 2027 2028 #1 one two three rotten tomatoes score google searched person people world global national
announces announce effective begins continues returns normal decision average price rental company model""".split())
NOT_FIRST = set("will who what which when where how why the a an by before after in on at of is does did can could next "
                "top best new end".split())


def _titlecase(t):
    ws = [w for w in re.findall(r"[A-Za-z]+", t or "") if len(w) > 3]
    return bool(ws) and sum(w[0].isupper() for w in ws) / len(ws) > 0.7


def story_tokens(r):
    o = r.get("outcome") or ""
    text = (r.get("title") or "") + " | " + ("" if RANGE_OUT.search(o) else o)
    out = {k for rx, k in ENT if rx.search(text)}
    for part in ((r.get("title") or ""), o):               # people: "Pete Hegseth", "Kevin Hassett" (not in Title Case titles)
        if not part or _titlecase(part) and part is not o:
            continue
        for a, b in re.findall(r"\b([A-Z][a-zà-ÿ'’-]+)\s+([A-Z][a-zà-ÿ'’-]{2,})\b", part):
            if a.lower() not in NOT_FIRST and b.lower() not in STOP:
                out.add(b)
    return out


def _words(t):
    return {w for w in re.findall(r"[a-z0-9]+", (t or "").lower()) if w not in STOP and len(w) > 2}


def same_story(a, b, ta=None, tb=None):
    ta = story_tokens(a) if ta is None else ta
    tb = story_tokens(b) if tb is None else tb
    if ta & tb:
        return True
    wa, wb = _words(a.get("title")), _words(b.get("title"))
    return bool(wa and wb and len(wa & wb) / len(wa | wb) >= 0.6)


# ---------------------------------------------------------------- the grade
def grade(r):
    """-> r["dz"] = {"g", "parts": {"liq","rules","type","flip"}, "why": {...}, "type": name, "flip": {...}} or None."""
    e, s = r.get("ex"), r.get("st") or {}
    parts, why = {}, {}
    if e:
        parts["liq"] = e["g"] if e.get("usd") else "D"
    if s.get("g") in RULES:
        parts["rules"] = RULES[s["g"]]
    tg, tname, ttxt = market_type(r)
    parts["type"], why["type"] = tg, tname + ": " + ttxt
    f = flip(r)
    if f:
        parts["flip"], why["flip"] = f["g"], f["t"]
    if "liq" not in parts or "rules" not in parts:
        return None
    use = [v for k, v in parts.items() if not (k == "type" and v == "B")]   # an ordinary event market is neutral: it neither lifts nor drags
    g = LET[math.floor(sum(N[v] for v in use) / len(use))]
    bad = [k for k in ("type", "flip") if parts.get(k) == "D"]
    if len(bad) == 2:
        g = "D"
    elif bad and N[g] > N["C"]:
        g = "C"
    return {"g": g, "parts": parts, "why": why, "type": tname, "flip": f, "v": 2}


def apply(rows):
    n = 0
    for r in rows:
        try:
            d = grade(r)
        except Exception as err:                    # never stop the Danger Zone
            print("DZ grade: %s skipped (%s)" % ((r.get("title") or "")[:30], err))
            d = None
        if d:
            r["dz"] = d
            n += 1
    from collections import Counter
    print("DZ grade v2: %d of %d rows graded %s | types %s | flip %s" % (
        n, len(rows), dict(Counter(r["dz"]["g"] for r in rows if r.get("dz"))),
        dict(Counter(r["dz"]["type"] for r in rows if r.get("dz"))),
        dict(Counter((r["dz"]["flip"] or {}).get("lvl", "-") for r in rows if r.get("dz")))))
