# Alpha Intel Desk: posts the daily digest from markets.json to the Telegram channel.
# The bot token comes from the GitHub secret TELEGRAM_BOT_TOKEN. Never put it in this file.
import json, os, urllib.request
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo
from topics import topic

CHANNEL = "@alphainteldesk"
SITE = "https://alphainteldesk.com"
ET = ZoneInfo("America/New_York")

def when(s):
    t = datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(ET)
    return t.strftime("%b %-d, %-I:%M %p ET")

def line(m, tail):
    name = escape(m["event"])
    mk = m.get("market") or ""
    if mk and mk != m["event"] and len(mk) <= 40:
        name += " (" + escape(mk) + ")"
    icon = topic(m["event"] + " " + mk, m.get("url", ""))
    return f'{icon} <a href="{escape(m["url"])}">{name}</a>\n   <b>{m["yes"]}% Yes</b> · {tail}'

d = json.load(open("markets.json"))
venues = (("polymarket", "Polymarket"), ("kalshi", "Kalshi"))
parts = ["🛰 <b>THE DESK IS OPEN</b> · " + datetime.now(ET).strftime("%a, %b %-d")]

parts.append("\n⏳ <b>Closing soon</b>")
for key, label in venues:
    for m in (d.get("closing_soon") or {}).get(key, []):
        parts.append(line(m, label + " · ⏰ closes " + when(m["closes"])))

new = d.get("new_markets") or {}
if any(new.get(k) for k, _ in venues):
    parts.append("\n🆕 <b>Just listed</b>")
    for key, label in venues:
        for m in new.get(key, []):
            parts.append(line(m, label + " · ✨ new"))

parts.append(f'\n📡 Live board, updated hourly: <a href="{SITE}">alphainteldesk.com</a>')
parts.append("<i>Not financial advice.</i>")

body = json.dumps({"chat_id": CHANNEL, "text": "\n".join(parts), "parse_mode": "HTML",
                   "link_preview_options": {"url": SITE, "prefer_large_media": True}}).encode()
token = os.environ["TELEGRAM_BOT_TOKEN"]
req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=body,
                             headers={"Content-Type": "application/json"})
r = json.load(urllib.request.urlopen(req, timeout=30))
print("Posted to Telegram:", r.get("ok"))
