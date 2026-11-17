"""Nov 17 (James): links in posts land on the Danger Zone page with that contract highlighted (#c=<key>).
ckey() is the same as the page's JavaScript ckey() (djb2-xor of site|id-or-url|side over UTF-16 code units, base 36)."""
import json, os

PAGE = "https://alphainteldesk.com/expiry-returns.html"


def ckey(r):
    t = "%s|%s|%s" % (r["site"], r.get("id") or r.get("url"), r["side"])
    h, b = 5381, t.encode("utf-16-le")
    for k in range(0, len(b), 2):
        h = ((h * 33) ^ (b[k] | b[k + 1] << 8)) & 0xFFFFFFFF
    s = ""
    while True:
        h, d = divmod(h, 36)
        s = "0123456789abcdefghijklmnopqrstuvwxyz"[d] + s
        if not h:
            return s


def url(r, top=None):
    """The highlighted-row link if the contract is in today's top 50 (the page only shows those), else the page itself."""
    if top is None:
        top = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "expiry.json"))).get("rows") or []
    return PAGE + "#c=" + ckey(r) if any(ckey(x) == ckey(r) for x in top) else PAGE
