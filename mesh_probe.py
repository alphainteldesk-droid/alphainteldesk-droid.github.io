"""Throwaway (Nov 21): read Mesh's public docs/terms and test the key once. Never prints the key."""
import os, re, json, urllib.request, urllib.error, html
KEY = os.environ.get("MESH_API_KEY", "").strip()
print("key present:", bool(KEY), "length:", len(KEY), "prefix:", KEY[:3] + "…" if KEY else "")
def get(url, hdr=None):
    rq = urllib.request.Request(url, headers=dict({"User-Agent": "AlphaIntelDesk/1.0", "Accept": "*/*"}, **(hdr or {})))
    try:
        with urllib.request.urlopen(rq, timeout=25) as r:
            return r.status, r.headers.get("content-type", ""), r.read(400000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("content-type", ""), e.read(3000).decode("utf-8", "replace")
    except Exception as e:
        return None, "", str(e)
def text(s):
    s = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", s); s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()
links = set()
for path in ["", "/docs", "/llms.txt", "/llms-full.txt", "/terms", "/tos", "/legal", "/pricing", "/openapi.json", "/api/openapi.json",
             "/docs/api", "/api", "/api/v1", "/v1", "/api/health", "/health", "/robots.txt", "/sitemap.xml"]:
    u = "https://meshapi.app" + path
    st, ct, body = get(u)
    t = body if ("json" in ct or "text/plain" in ct or path.endswith((".txt", ".xml"))) else text(body)
    print("\n=== %s -> %s %s (%d chars)" % (u, st, ct[:30], len(body)))
    print(t[:3500].replace(KEY, "***") if KEY else t[:3500])
    for h in re.findall(r'href="([^"#]+)"', body):
        if h.startswith("/") or "meshapi" in h: links.add(h)
print("\n=== LINKS:", sorted(links)[:120])
if KEY:
    for path in ["/api/v1/usage", "/v1/usage", "/api/usage", "/api/v1/events?limit=2", "/v1/events?limit=2", "/api/v1/speakers?limit=2", "/v1/topics?limit=2"]:
        for hn, hv in [("Authorization", "Bearer " + KEY), ("X-API-Key", KEY), ("x-api-key", KEY)]:
            st, ct, body = get("https://meshapi.app" + path, {hn: hv})
            print("AUTH TRY %-28s %-14s -> %s %s" % (path, hn, st, body[:300].replace(KEY, "***").replace("\n", " ")))
            if st == 200: break
