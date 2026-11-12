# Alpha Intel Desk: Polymarket event lists (Nov 12, 2026).
# On Nov 12 at ~7:49 AM ET Polymarket's old /events list started answering "HTTP 406 Not Acceptable"
# to GitHub, while /markets kept working. This helper:
#   1. asks for JSON explicitly (a 406 usually means the server wants an Accept header),
#   2. uses the newer /events/keyset list (cursor paging: {"events": [...], "next_cursor": "..."}),
#   3. falls back to the old /events list (offset paging) if keyset fails.
# Used by match_markets.py (Gap Scanner, Movers) and make_markets.py (New markets).
import json
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://gamma-api.polymarket.com"
HEADERS = {"User-Agent": "AlphaIntelDesk/1.0 (+https://alphainteldesk.com)", "Accept": "application/json"}
_mode = {"keyset": True}          # remembers within one run whether keyset works


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
