# Alpha Intel Desk: tell Bing / Yandex / Seznam / Naver (IndexNow) about our pages, once a day (Nov 10).
# The key is public by design: it's served at https://alphainteldesk.com/b36f51a58a439d1193c67cb6bd469c1f.txt to prove we own the site.
import json, re, urllib.request
from datetime import datetime, timezone

KEY = "b36f51a58a439d1193c67cb6bd469c1f"
today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
try:
    last = json.load(open("indexnow_state.json")).get("last")
except Exception:
    last = None
if last == today:
    print("IndexNow: already pinged today")
else:
    urls = re.findall(r"<loc>([^<]+)</loc>", open("sitemap.xml").read())
    body = json.dumps({"host": "alphainteldesk.com", "key": KEY,
                       "keyLocation": "https://alphainteldesk.com/%s.txt" % KEY, "urlList": urls}).encode()
    req = urllib.request.Request("https://api.indexnow.org/indexnow", data=body, method="POST",
                                 headers={"Content-Type": "application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            print("IndexNow: pinged %d pages, HTTP %s" % (len(urls), r.status))
        json.dump({"last": today}, open("indexnow_state.json", "w"))
    except Exception as err:
        print("IndexNow: ping failed (will try again next run):", err)
