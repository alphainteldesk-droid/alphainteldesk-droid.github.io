# Alpha Intel Desk: recap.py (Nov 22, 2026). The Sunday weekly recap, "This week on the desk".
# James decided (Nov 22): Telegram = posted automatically; X = a ready-to-paste draft sent to James (he has X Premium: long posts OK)
# (the workflow opens a GitHub issue with it, which GitHub pushes to his phone/email); no Reddit for now.
#
#   python3 recap.py          -> preview only: prints both versions, writes recap_x.md, posts nothing
#   python3 recap.py --post   -> also posts to Telegram and saves the week's baseline in recap_state.json
#
# Reads: week_gaps.json (week_gaps.py), track.json, motw.json, calendar.json, recap_state.json.
# Public data only: gaps, Danger Zone results, Market of the Week, calendar. Nothing about private trading.
import json, os, sys, time, urllib.request
from datetime import datetime, timedelta, timezone
from html import escape
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
SITE = "https://alphainteldesk.com"
CHANNEL = "@alphainteldesk"
WEEK = 7 * 86400
POST = "--post" in sys.argv
now = int(time.time())
since = now - WEEK


def load(f, default):
    try:
        return json.load(open(f))
    except Exception:
        return default


def c(x):        # 34.5 -> "34.5¢", 46.0 -> "46¢"
    return f"{x:.1f}".rstrip("0").rstrip(".") + "¢"


def short(s, n):
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def et(ts):
    return datetime.fromtimestamp(ts, ET)


state = load("recap_state.json", {})
start, end = et(since + 3600), et(now)
label = f"{start:%b %-d}–{end:%-d}" if start.month == end.month else f"{start:%b %-d}–{end:%b %-d}"

# 1. Biggest gaps this week (largest net gap after fees each one reached)
log = load("week_gaps.json", {})
if POST and (not log or min(v["first"] for v in log.values()) > now - 5 * 86400):
    print("Weekly recap skipped: the gap log has under 5 days of data (it started Nov 22, 2026). First recap: Sun Nov 29.")
    sys.exit(0)
week = sorted((v for v in log.values() if v["last"] >= since), key=lambda v: -v["net"])
top = week[:3]
open_now = lambda v: now - v["last"] < 2 * 3600

# 2. Danger Zone: results settled since last Sunday's baseline + the overall record
track = load("track.json", {})
allr = (track.get("summary") or {}).get("all") or {}
base = state.get("track")
dz_week = None
if base and allr:
    n, won = allr["n"] - base["n"], allr["won"] - base["won"]
    if n >= 0 and 0 <= won <= n:
        dz_week = (n, won)
cut = et(since).strftime("%Y-%m-%d")
misses = [m for m in track.get("misses", []) if m.get("c", "") >= cut]

# 3. Market of the Week
mw = (load("motw.json", {}) or {})
cur = mw.get("current") or {}
nxt = mw.get("next") or {}

# 4. Next week: medium/high-impact calendar events in the coming 8 days
cal = load("calendar.json", {}).get("items") or []
ahead = []
for i in cal:
    try:
        t = datetime.fromisoformat(i["date"].replace("Z", "+00:00")).timestamp()
    except Exception:
        continue
    if now < t <= now + 8 * 86400 and (i.get("impact") or 0) >= 2:
        ahead.append((t, i))
ahead = sorted(ahead, key=lambda x: x[0])[:5]


def gap_line(v, n=None):
    nm = v["name"] if n is None else short(v["name"], n)
    (lo, lp), (hi, hp) = v["low"], v["high"]
    return nm, f"{lo} {c(lp)} vs {hi} {c(hp)}, {c(v['net'])} after fees"


def motw_moves():
    pp, lr = cur.get("picked_prices") or {}, cur.get("last_read") or cur.get("prices") or {}
    out = []
    for site, lab in (("polymarket", "Polymarket"), ("kalshi", "Kalshi"), ("alpha", "Alpha Arcade")):
        if pp.get(site) is not None and lr.get(site) is not None:
            out.append((lab, pp[site], lr[site]))
    return out


# ---------- Telegram (HTML) ----------
tg = [f"📊 <b>THIS WEEK ON THE DESK</b> · {label}"]
if top:
    tg.append(f"\n🔍 <b>Biggest price gaps</b> ({len(week)} listed this week)")
    for i, v in enumerate(top, 1):
        nm, detail = gap_line(v)
        tag = "still open" if open_now(v) else "closed"
        tg.append(f"{i}. {escape(nm)}\n   {escape(detail)} · {tag}")
if allr:
    tg.append("\n🚨 <b>Danger Zone</b>")
    if dz_week and dz_week[0]:
        tg.append(f"This week: {dz_week[1]} of {dz_week[0]} settled contracts paid out.")
    elif dz_week:
        tg.append("This week: no listed contracts settled.")
    for m in (misses[:3] if dz_week and dz_week[0] else []):   # misses only next to the week's paid count
        nm = m["t"] + ("" if m["o"] in ("Yes", m["t"]) else " — " + m["o"])
        tg.append(f"❌ Missed: {escape(short(nm, 70))} ({m['s']} at {c(m['a'])})")
    tg.append(f"Track record: {allr['won']} of {allr['n']} paid out ({allr['pct']:.1f}%), "
              f"{allr['ret']:+.1f}% overall after fees.")
if cur:
    tg.append(f"\n⭐ <b>Market of the Week:</b> {escape(cur['title'])}" + ("" if cur.get("outcome") in (None, "Yes") else f" — {escape(cur['outcome'])}"))
    for lab, a, b in motw_moves():
        tg.append(f"   {lab}: {c(a)} at the pick → {c(b)} now ({b - a:+.1f}¢)")
    if nxt.get("approved") and nxt.get("title"):
        tg.append(f"   New pick goes live Monday 4 AM ET: {escape(nxt['title'])}")
if ahead:
    tg.append("\n📅 <b>Coming up</b>")
    for t, i in ahead:
        d = et(t)
        when = d.strftime("%a %b %-d") + ("" if i.get("allday") else d.strftime(", %-I:%M %p ET").replace(":00 ", " "))
        tg.append(f"• {when}: {escape(i['name'])}" + (" (expected)" if i.get("est") else ""))
tg.append(f'\n📡 Free, no sign-up: <a href="{SITE}">alphainteldesk.com</a>')
tg.append("<i>Not financial advice.</i>")
tg_text = "\n".join(tg)


# ---------- X (plain text; James has X Premium, so no 280 limit) ----------
# The first ~280 characters show before "Show more" in the timeline, so the strongest lines go first.
def xlen(s):   # X's own counting: Latin text and basic punctuation count 1; emoji, arrows, "…" and the rest count 2
    one = lambda p: p <= 4351 or 8192 <= p <= 8205 or 8208 <= p <= 8223 or 8242 <= p <= 8247
    return sum(1 if one(ord(ch)) else 2 for ch in s)


xl = [f"📊 This week on the desk ({label})"]
if top:
    xl.append("\n🔍 Biggest price gaps after fees:")
    for i, v in enumerate(top, 1):
        nm, detail = gap_line(v)
        xl.append(f"{i}. {nm}\n   {detail}" + ("" if open_now(v) else " (closed)"))
if allr:
    xl.append("\n🚨 Danger Zone (80¢+ contracts):")
    if dz_week and dz_week[0]:
        xl.append(f"This week: {dz_week[1]} of {dz_week[0]} paid out.")
    for m in (misses[:3] if dz_week and dz_week[0] else []):
        nm = m["t"] + ("" if m["o"] in ("Yes", m["t"]) else " — " + m["o"])
        xl.append(f"❌ Missed: {short(nm, 70)} ({m['s']} at {c(m['a'])})")
    xl.append(f"Track record: {allr['won']} of {allr['n']} paid out, {allr['ret']:+.1f}% after fees. We show the misses too.")
mv = motw_moves()
if cur and mv:
    xl.append(f"\n⭐ Market of the Week: {cur['title']}")
    for lab, a, b in mv:
        xl.append(f"{lab}: {c(a)} at the pick, {c(b)} now ({b - a:+.1f}¢)")
if ahead:
    xl.append("\n📅 Coming up:")
    for t, i in ahead:
        d = et(t)
        xl.append(f"• {d:%a %b %-d}: {i['name']}" + (" (expected)" if i.get("est") else ""))
xl.append("\nFull board in the reply 👇")
x_text = "\n".join(xl)
x_reply = f"Free gap scanner, Danger Zone and calendar for Polymarket, Kalshi and Alpha Arcade: {SITE}\nNot financial advice."

md = (f"Weekly recap for X ({label}). Copy each box into X: the post first, then the reply under it.\n\n"
      f"**Post** ({xlen(x_text)} characters; X Premium)\n\n```\n{x_text}\n```\n\n**Reply (with the link)**\n\n```\n{x_reply}\n```\n\n"
      f"Telegram got its own version automatically." + ("" if POST else " (Preview only: nothing was posted.)"))
open("recap_x.md", "w").write(md)
print("=== TELEGRAM ===\n" + tg_text + "\n\n=== X POST (" + str(xlen(x_text)) + " chars) ===\n" + x_text + "\n\n=== X REPLY ===\n" + x_reply)

if POST:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    body = json.dumps({"chat_id": CHANNEL, "text": tg_text, "parse_mode": "HTML",
                       "link_preview_options": {"url": SITE, "prefer_large_media": True}}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=body,
                                 headers={"Content-Type": "application/json"})
    print("Posted to Telegram:", json.load(urllib.request.urlopen(req, timeout=30)).get("ok"))
    if allr:
        state["track"] = {"n": allr["n"], "won": allr["won"], "at": now}
    state["last_post"] = now
    json.dump(state, open("recap_state.json", "w"), indent=1)
