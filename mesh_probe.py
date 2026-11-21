"""Throwaway (Nov 21) round 2: docs in full, business/licensing page, a few authenticated calls. Never prints the key."""
import os, re, json, urllib.request, urllib.error, html
KEY = os.environ.get("MESH_API_KEY", "").strip()
def get(url, hdr=None):
    rq = urllib.request.Request(url, headers=dict({"User-Agent": "AlphaIntelDesk/1.0", "Accept": "*/*"}, **(hdr or {})))
    try:
        with urllib.request.urlopen(rq, timeout=25) as r:
            return r.status, r.read(600000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read(3000).decode("utf-8", "replace")
    except Exception as e:
        return None, str(e)
def text(s):
    s = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", s); s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()
safe = lambda s: s.replace(KEY, "***") if KEY else s
for u, n in [("https://meshapi.app/docs", 40000), ("https://meshapi.app/business", 8000), ("https://meshapi.app/contact", 2000)]:
    st, b = get(u); print("\n=== %s -> %s\n%s" % (u, st, text(b)[:n]))
H = {"X-API-Key": KEY}
for p in ["/health", "/v1/usage", "/v1/events?limit=2", "/v1/speakers?limit=3", "/v1/topics?limit=3", "/v1/event-types"]:
    st, b = get("https://api.meshapi.app" + p, H if p != "/health" else None)
    print("\n=== API %s -> %s\n%s" % (p, st, safe(b)[:2500]))
