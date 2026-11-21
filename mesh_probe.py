"""Throwaway (Nov 21) round 3: test the meshapi.app key. Never prints the key."""
import os, json, urllib.request, urllib.error
KEY = os.environ.get("MESH_API_KEY", "").strip()
print("key looks like mesh_:", KEY.startswith("mesh_"), "length:", len(KEY))
def get(p):
    rq = urllib.request.Request("https://api.meshapi.app" + p, headers={"X-API-Key": KEY, "User-Agent": "AlphaIntelDesk/1.0"})
    try:
        with urllib.request.urlopen(rq, timeout=25) as r:
            return r.status, r.read(300000).decode("utf-8", "replace"), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(3000).decode("utf-8", "replace"), dict(e.headers)
for p in ["/v1/usage", "/v1/events?limit=3&has_transcript=true", "/v1/speakers?limit=5", "/v1/topics?limit=5",
          "/v1/segments/search?q=tariff&limit=3"]:
    st, b, h = get(p)
    b = b.replace(KEY, "***")
    print("\n=== %s -> %s | quota headers: %s" % (p, st, {k: v for k, v in h.items() if "limit" in k.lower() or "budget" in k.lower() or "remaining" in k.lower()}))
    try:
        print(json.dumps(json.loads(b), indent=1)[:2500])
    except Exception:
        print(b[:800])
