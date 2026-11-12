# Alpha Intel Desk: watchdog (Nov 12, 2026). Runs at the end of every "Update markets" run.
#  1. Checks every feed: did it bring in data, and how fresh is it?  -> health.json (+ "All feeds live" line on the site)
#  2. Fixes what it safely can by itself: if Polymarket or Kalshi came back empty and the Gap Scanner went empty
#     with it, it puts back the last good gaps.json (its "last checked" time stays old, so the site shows it's delayed).
#  3. Tells James straight away when something breaks: opens a GitHub issue (GitHub emails / pushes it to his phone)
#     saying what broke and what to do. When it works again, it comments "fixed" and closes the issue.
# Never raises: a watchdog problem must not break the update.
import json
import os
import subprocess
import urllib.request
from datetime import datetime, timezone

now = datetime.now(timezone.utc)
F = "%Y-%m-%dT%H:%M:%SZ"
OWNER = "alphainteldesk-droid"


def load(p, default=None):
    try:
        return json.load(open(p))
    except Exception:
        return default if default is not None else {}


def age_h(stamp):
    try:
        return (now - datetime.strptime(stamp[:19] + "Z", F).replace(tzinfo=timezone.utc)).total_seconds() / 3600
    except Exception:
        return 99.0


SEED = {"Polymarket": [10400] * 6, "Kalshi": [21000] * 6, "Polymarket-Kalshi matches": [128] * 6}


def baseline(old, name, value):
    """Nov 12: compare a count with its own recent normal (median of the last 50 good runs).
    Returns (ok, note). Below 40% of normal = not OK, even if it isn't zero (a half-broken feed)."""
    hist = ((old.get("feeds") or {}).get(name) or {}).get("hist") or []
    if len(hist) < 6:
        hist = SEED.get(name, []) + hist                    # normal levels seen Nov 11, until our own history builds up
    if len(hist) < 6:
        return True, ""
    med = sorted(hist)[len(hist) // 2]
    if med and value < 0.4 * med:
        return False, " (normal is about %d)" % med
    return True, ""


def checks():
    m, desk, gaps, mk, al = load("matches.json"), load("desk.json"), load("gaps.json"), load("markets.json"), load("alpha_live.json")
    c = m.get("counts") or {}
    nm = mk.get("new_markets") or {}
    pk = c.get("poly_kalshi")
    return {
        # name: (ok?, what we saw, what to do if it's down, count to track against normal or None)
        "Polymarket-Kalshi matches": (pk is None or pk >= 10, "%s pairs" % pk,
                                      "Far fewer Polymarket-Kalshi matches than normal: one feed is only partly working. "
                                      "Ask Claude to check the matcher log.", pk),
        "Polymarket": (c.get("polymarket", 0) >= 200, "%s events" % c.get("polymarket", 0),
                       "Polymarket may have changed its data feed. Open a session and ask Claude to fix the Polymarket feed.",
                       c.get("polymarket")),
        "Kalshi": (c.get("kalshi", 0) >= 3000, "%s events" % c.get("kalshi", 0),
                   "Kalshi may be limiting us or changed its data. Open a session and ask Claude to fix the Kalshi feed.",
                   c.get("kalshi")),
        "Alpha Arcade (Courier)": (age_h(al.get("updated", "")) <= 3 and c.get("alpha", 0) > 0,
                                   "data %.1f h old, %s markets" % (age_h(al.get("updated", "")), c.get("alpha", 0)),
                                   "Courier on the Chromebook has stopped. Open a Linux terminal and type: courier", None),
        "News line": (len(desk.get("news") or []) >= 3, "%d headlines" % len(desk.get("news") or []),
                      "The news feeds stopped. Ask Claude to check make_desk.py news().", None),
        "Conflict Radar": (len(desk.get("conflict") or []) >= 3, "%d headlines" % len(desk.get("conflict") or []),
                           "Conflict Radar headlines stopped. Ask Claude to check make_desk.py.", None),
        "Google Trends": (len(desk.get("trends") or []) >= 3, "%d trends" % len(desk.get("trends") or []),
                          "Trends stopped. Ask Claude to check make_desk.py.", None),
        "New markets": (len(nm.get("kalshi") or []) + len(nm.get("polymarket") or []) > 0,
                        "%d Polymarket, %d Kalshi" % (len(nm.get("polymarket") or []), len(nm.get("kalshi") or [])),
                        "New markets came back empty. Ask Claude to check make_markets.py.", None),
        "Gap Scanner": (age_h(gaps.get("updated", "")) <= 2, "updated %.1f h ago, %d gaps" % (age_h(gaps.get("updated", "")),
                        len(gaps.get("gaps") or [])), "The Gap Scanner stopped updating. Ask Claude to check the run log.", None),
    }


def self_fix(res):
    """If Polymarket or Kalshi failed and the scanner went empty, keep the last good gaps.json."""
    if res["Polymarket"][0] and res["Kalshi"][0]:   # (zero-count check; baseline drops are alerted, not self-fixed)
        return None
    cur = load("gaps.json")
    if cur.get("gaps"):
        return None
    try:
        prev = json.loads(subprocess.run(["git", "show", "HEAD:gaps.json"], capture_output=True, text=True).stdout)
    except Exception:
        return None
    if not prev.get("gaps"):
        return None
    json.dump(prev, open("gaps.json", "w"), indent=1)          # its "updated" stays old -> site shows "last checked N min ago"
    return "kept the last good Gap Scanner list (%d gaps) instead of showing it empty" % len(prev["gaps"])


def gh(method, path, body=None):
    tok = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY", OWNER + "/" + OWNER + ".github.io")
    if not tok:
        return None
    req = urllib.request.Request("https://api.github.com/repos/%s%s" % (repo, path), method=method,
                                 data=json.dumps(body).encode() if body else None,
                                 headers={"Authorization": "Bearer " + tok, "Accept": "application/vnd.github+json",
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def main():
    res = checks()
    old = load("health.json", {"feeds": {}})
    fixed = self_fix(res)
    feeds, down = {}, []
    for name, (ok, seen, todo, count) in res.items():
        was = (old.get("feeds") or {}).get(name) or {}
        hist = list(was.get("hist") or [])
        if ok and count is not None:
            ok, note = baseline(old, name, count)
            seen += note
        if ok and count is not None:
            hist = (hist + [count])[-50:]                       # only normal runs build the baseline
        f = {"ok": ok, "seen": seen, "last_good": now.strftime(F) if ok else was.get("last_good"),
             "since": was.get("since") if was.get("ok") == ok and was.get("since") else now.strftime(F),
             "issue": was.get("issue"), "hist": hist}
        try:
            if not ok and not was.get("issue"):                     # just broke -> alert now
                body = ("**%s is down** (checked %s UTC)\n\nWhat we saw: %s\nLast worked: %s\n\n**What to do:** %s\n\n"
                        "%s\n\nThis issue closes itself when the feed works again. @%s"
                        % (name, now.strftime("%b %d %H:%M"), seen, was.get("last_good") or "unknown", todo,
                           ("Self-fix: " + fixed) if fixed else "", OWNER))
                iss = gh("POST", "/issues", {"title": "⚠ Alpha Intel Desk: %s is down" % name, "body": body})
                f["issue"] = iss and iss.get("number")
            elif ok and was.get("issue"):                           # working again -> "fixed" note + close
                gh("POST", "/issues/%s/comments" % was["issue"],
                   {"body": "✅ Fixed: %s is working again (%s, checked %s UTC). @%s" % (name, seen, now.strftime("%b %d %H:%M"), OWNER)})
                gh("PATCH", "/issues/%s" % was["issue"], {"state": "closed"})
                f["issue"] = None
        except Exception as err:
            print("Watchdog: GitHub alert failed for", name, "-", err)
        feeds[name] = f
        if not ok:
            down.append(name)
        print("Watchdog: %-24s %s | %s" % (name, "OK  " if ok else "DOWN", seen))
    json.dump({"updated": now.strftime(F), "all_ok": not down, "down": down, "self_fix": fixed, "feeds": feeds},
              open("health.json", "w"), indent=1)
    print("Watchdog:", "all feeds live" if not down else "DOWN: " + ", ".join(down), "| self-fix:", fixed or "none")


if __name__ == "__main__":
    try:
        main()
    except Exception as err:
        print("Watchdog failed (update not affected):", err)
