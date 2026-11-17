# Alpha Intel Desk: post the daily Short to the Telegram channel as a playable video (Nov 15, 2026).
# Usage: python3 send_short.py short.mp4   (caption comes from short.txt, written by make_short.py)
# Needs the TELEGRAM_BOT_TOKEN secret (same bot as the 7 AM digest).
import json, os, sys, urllib.request, uuid

CHANNEL = "@alphainteldesk"
video = sys.argv[1]
txt = open(video.rsplit(".", 1)[0] + ".txt").read()
title = txt.split("TITLE\n", 1)[1].split("\n", 1)[0].strip()
desc = txt.split("DESCRIPTION\n", 1)[1].split("\n\nHASHTAGS", 1)[0].strip()
link = txt.split("LINK\n", 1)[1].split("\n", 1)[0].strip() if "LINK\n" in txt else "https://alphainteldesk.com"   # Nov 17: the contract's own row
desc = desc.split("\nSee it on Alpha Intel Desk:", 1)[0].replace("Not financial advice. https://alphainteldesk.com", "").strip()
esc = lambda s: s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
caption = ("🎬 <b>%s</b>\n\n%s\n\n👉 <a href=\"%s\">See this contract on Alpha Intel Desk</a> · free, no sign-up\n"
           "<i>Not financial advice. Always check each site's rules before you trade.</i>" % (esc(title), esc(desc), esc(link)))

fields = {"chat_id": CHANNEL, "caption": caption, "parse_mode": "HTML", "width": "1080", "height": "1920",
          "duration": "15", "supports_streaming": "true"}
b = uuid.uuid4().hex
body = b"".join(("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n" % (b, k, v)).encode() for k, v in fields.items())
body += ("--%s\r\nContent-Disposition: form-data; name=\"video\"; filename=\"alpha-intel-desk-short.mp4\"\r\n"
         "Content-Type: video/mp4\r\n\r\n" % b).encode() + open(video, "rb").read() + ("\r\n--%s--\r\n" % b).encode()
req = urllib.request.Request("https://api.telegram.org/bot%s/sendVideo" % os.environ["TELEGRAM_BOT_TOKEN"], data=body,
                             headers={"Content-Type": "multipart/form-data; boundary=" + b})
r = json.load(urllib.request.urlopen(req, timeout=120))
print("Telegram:", "posted the Short" if r.get("ok") else r)
