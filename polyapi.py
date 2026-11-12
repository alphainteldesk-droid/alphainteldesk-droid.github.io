# Alpha Intel Desk: Polymarket event lists (Nov 12, 2026).
# On Nov 12 at ~7:49 AM ET Polymarket's old /events list started answering "HTTP 406 Not Acceptable"
# to GitHub, while /markets kept working. This helper:
#   1. asks for JSON explicitly (a 406 usually means the server wants an Accept header),
#   2. uses the newer /events/keyset list (cursor paging: {"events": [...], "next_cursor": "..."}),
#   3. falls back to the old /events list (offset paging) if keyset fails,
#   4. and if BOTH event lists refuse (seen Nov 12: 406 on both), rebuilds events from the /markets list,
#      which kept working: markets are grouped by the event each one belongs to.
# Used by match_markets.py (Gap Scanner, Movers) and make_markets.py (New markets).
import json
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://gamma-api.polymarket.com"
HEADERS = {"User-Agent": "AlphaIntelDesk/1.0 (+https://alphainteldesk.com)", "Accept": "application/json"}
_mode = {"keyset": True, "events": True}   # remembers within one run which lists work


def get(url):
    """GET JSON with the Accept header; retries "too many requests" (429) up to 4 times."""
    for attempt in range(4):
        req = urllib.request.Request(url, headers=HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as err:
            if err.code != 429 or attempt == 3:
                raise
            wait = float(err.headers.get("Retry-After") or 0) or 2 * (attempt + 1)
            time.sleep(min(wait, 20))


def events(params, max_events=2000, page=100):
    """Open Polymarket events matching params (dict of query filters, e.g. end_date_min, order).
    Returns a list of event objects. Raises only if BOTH the keyset and the old list fail."""
    params = dict(params, closed="false")
    if _mode["keyset"]:
        try:
            out, cur = [], None
            while len(out) < max_events:
                q = dict(params, limit=page)
                if cur:
                    q["after_cursor"] = cur
                d = get(BASE + "/events/keyset?" + urllib.parse.urlencode(q))
                evs = d.get("events") or [] if isinstance(d, dict) else d
                out += evs
                cur = d.get("next_cursor") if isinstance(d, dict) else None
                if not cur or not evs:
                    break
            return out
        except Exception as err:
            print("Polymarket: /events/keyset failed (%s) - trying the old /events list" % err)
            _mode["keyset"] = False
    if _mode["events"]:
        try:
            out, off = [], 0
            while off < max_events:
                q = dict(params, active="true", limit=page, offset=off)
                d = get(BASE + "/events?" + urllib.parse.urlencode(q))
                if not d:
                    break
                out += d
                off += len(d)
                if len(d) < page:
                    break
            return out
        except Exception as err:
            print("Polymarket: /events failed too (%s) - rebuilding events from /markets" % err)
            _mode["events"] = False
    return events_from_markets(params, max_markets=max_events * 2)


def events_from_markets(params, max_markets=4000, page=500):
    """Event-shaped dicts built from /markets: {id, slug, title, description, volume, volume24hr,
    tags, startDate, createdAt, endDate, markets: [...]}, the same fields our scripts read from /events."""
    ms, off = [], 0
    while off < max_markets:
        q = dict(params, active="true", limit=page, offset=off)
        if _mode.get("tags", True):
            try:
                d = get(BASE + "/markets?" + urllib.parse.urlencode(dict(q, include_tag="true")))
            except urllib.error.HTTPError:
                _mode["tags"] = False
                d = get(BASE + "/markets?" + urllib.parse.urlencode(q))
        else:
            d = get(BASE + "/markets?" + urllib.parse.urlencode(q))
        if not d:
            break
        ms += d
        off += len(d)
        if len(d) < page:
            break
    evs = {}
    for m in ms:
        ev = (m.get("events") or [{}])[0] or {}
        key = ev.get("id") or ev.get("slug") or m.get("slug")
        e = evs.get(key)
        if e is None:
            tags = ev.get("tags") or m.get("tags") or ([{"label": m["category"]}] if m.get("category") else [])
            e = evs[key] = {"id": key, "slug": ev.get("slug") or m.get("slug") or "",
                            "title": ev.get("title") or m.get("question") or "",
                            "description": ev.get("description") or m.get("description") or "",
                            "volume": ev.get("volume"), "volume24hr": ev.get("volume24hr"), "tags": tags,
                            "startDate": ev.get("startDate") or m.get("startDate"),
                            "createdAt": ev.get("createdAt") or m.get("createdAt"),
                            "endDate": ev.get("endDate") or m.get("endDate"), "markets": [], "_v": 0.0, "_v24": 0.0}
        e["markets"].append(m)
        e["_v"] += float(m.get("volumeNum") or m.get("volume") or 0)
        e["_v24"] += float(m.get("volume24hr") or 0)
    out = []
    for e in evs.values():
        e["volume"] = e["volume"] if e["volume"] is not None else e["_v"]
        e["volume24hr"] = e["volume24hr"] if e["volume24hr"] is not None else e["_v24"]
        del e["_v"], e["_v24"]
        out.append(e)
    out.sort(key=lambda e: float(e.get("volume24hr") or 0), reverse=True)
    print("Polymarket: %d markets -> %d events (from /markets)" % (len(ms), len(out)))
    return out
