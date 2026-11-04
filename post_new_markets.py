# Alpha Intel Desk: posts "Just listed" alerts to Telegram for new markets not posted before.
# Runs every hour right after make_markets.py. Remembers what it posted in posted.json.
# The bot token comes from the GitHub secret TELEGRAM_BOT_TOKEN. Never put it in this file.
import json, os, urllib.request
from datetime import datetime, timedelta, timezone
from html import escape
from zoneinfo import ZoneInfo
from topics import topic

CHANNEL = "@alphainteldesk"
SITE = "https://alphainteldesk.com"
ET = ZoneInfo("America/New_York")
QUIET = (23, 7)   # no posts from 11 PM to 7 AM Eastern (the 7 AM digest covers the night)
MAX_POSTS = 3     # at most this many markets per hourly post
KEEP_DAYS = 14    # forget posted markets after two weeks

def key(site, m):
    return site + "|" + m["event"] + "|" + (m.get("market") or "")

try:
    posted = json.load(open("posted.json"))
except (OSError, ValueError):
    posted = None   # first run: remember what's there now, post nothing

now = datetime.now(timezone.utc)
d = json.load(open("markets.json"))
fresh = []
for site, label in (("polymarket", "Polymarket"), ("kalshi", "Kalshi")):
    for m in (d.get("new_markets") or {}).get(site, []):
        if posted is None or key(site, m) not in posted:
            fresh.append((site, label, m))

seen = posted or {}
for site, _, m in fresh:
    seen[key(site, m)] = now.strftime("%Y-%m-%d")
cut = (now - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
seen = {k: v for k, v in seen.items() if v >= cut}

hour = now.astimezone(ET).hour
quiet = hour >= QUIET[0] or hour < QUIET[1]
if posted is None:
    print("First run: remembered", len(fresh), "markets, posted nothing.")
elif not fresh:
    print("No new markets to post.")
elif quiet:
    print("Quiet hours: skipped", len(fresh), "markets.")
else:
    lines = ["🆕 <b>JUST LISTED</b>"]
    for site, label, m in fresh[:MAX_POSTS]:
        name = escape(m["event"])
        mk = m.get("market") or ""
        if mk and mk != m["event"] and len(mk) <= 40:
            name += " (" + escape(mk) + ")"
        lines.append(f'\n{topic(m["event"] + " " + mk, m.get("url", ""))} <a href="{escape(m["url"])}">{name}</a>'
                     f'\n   <b>{m["yes"]}% Yes</b> · {label} · ✨ new')
    lines.append(f'\n📡 More on the live board: <a href="{SITE}">alphainteldesk.com</a>')
    body = json.dumps({"chat_id": CHANNEL, "text": "\n".join(lines), "parse_mode": "HTML",
                       "link_preview_options": {"is_disabled": True}}).encode()
    try:
        req = urllib.request.Request(
            "https://api.telegram.org/bot" + os.environ["TELEGRAM_BOT_TOKEN"] + "/sendMessage",
            data=body, headers={"Content-Type": "application/json"})
        r = json.load(urllib.request.urlopen(req, timeout=30))
        print("Posted", min(len(fresh), MAX_POSTS), "new markets to Telegram:", r.get("ok"))
    except Exception as err:
        print("Telegram post failed, will retry next hour:", err)
        raise SystemExit(0)   # don't save, so these get another try; don't break the site update

json.dump(seen, open("posted.json", "w"), indent=1, ensure_ascii=False)
