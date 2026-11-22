# Alpha Intel Desk: week_gaps.py (Nov 22, 2026). Runs after make_gaps.py in every "Update markets" run.
# Keeps an 8-day log of every gap the Gap Scanner listed (its biggest net gap after fees, when, which sites),
# so the Sunday weekly recap (recap.py) can say "biggest gaps this week" without digging through git history.
# Writes week_gaps.json. Never raises: a problem here must not break the update.
import json, time

KEEP = 8 * 86400


def name(g):
    t, o = g["title"].strip(), (g.get("outcome") or "").strip()
    if not o or o in ("Yes", t):
        return t
    for tail in ("...?", "…?"):
        if t.endswith(tail):
            return t[: -len(tail)].rstrip() + " " + o + "?"
    return t + " — " + o


def main():
    now = int(time.time())
    try:
        log = json.load(open("week_gaps.json"))
    except Exception:
        log = {}
    gaps = (json.load(open("gaps.json")).get("gaps") or [])
    for g in gaps:
        k = g["title"] + "|" + g["outcome"]
        net = float(g.get("net") or 0)
        old = log.get(k)
        row = {"name": name(g), "first": old["first"] if old else now, "last": now,
               "net": net, "at": now, "low": [g["low"]["name"], g["low"]["price"]],
               "high": [g["high"]["name"], g["high"]["price"]], "grade": g.get("grade"),
               "alpha": g.get("prices", {}).get("alpha") is not None}
        if old and old["net"] >= net:   # keep the moment the gap was biggest
            for f in ("net", "at", "low", "high", "grade", "alpha"):
                row[f] = old[f]
        log[k] = row
    log = {k: v for k, v in log.items() if now - v["last"] < KEEP}
    json.dump(log, open("week_gaps.json", "w"), separators=(",", ":"))
    print(f"Week gaps: {len(gaps)} listed now, {len(log)} in the 8-day log")


try:
    main()
except Exception as err:
    print("Week gaps skipped:", err)
