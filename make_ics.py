"""Nov 21 (James): "Add to my calendar" feed for the Catalyst Calendar.

Reads calendar.json (written by make_gaps.py) and writes catalyst-calendar.ics, a standard iCalendar feed
that Google Calendar, Apple Calendar (iPhone/Mac) and Outlook can subscribe to. Subscribers' apps re-read it
on their own (Google roughly every 8-24 h), so new and changed dates reach them automatically.
Only scheduled events (data releases, Fed, politics, world, market hours, worth-knowing); market settlement
items stay on the site. No prices in the feed (they would go stale in a calendar): every event links back
to the live calendar instead. Never raises.
"""
import json, hashlib
from datetime import datetime, timedelta, timezone

SITE = "https://alphainteldesk.com"
CAL = SITE + "/?utm_source=calendar&utm_medium=ics#calendar"   # Nov 24: tagged so calendar clicks show in analytics
OUT = "catalyst-calendar.ics"
CATS = {"econ": "Economy", "fed": "Fed", "earnings": "Earnings", "politics": "Politics", "world": "World",
        "markets": "Market hours", "fyi": "Worth knowing"}
F = "%Y-%m-%dT%H:%M:%SZ"


def esc(s):
    return (s or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r", "").replace("\n", "\\n")


def fold(line):
    """iCalendar lines are at most 75 bytes; longer ones continue on the next line after one space."""
    b, out = line.encode("utf-8"), []
    while len(b) > 75:
        cut = 75 if not out else 74
        while (b[cut] & 0xC0) == 0x80:                     # never split a UTF-8 character
            cut -= 1
        out.append(b[:cut].decode("utf-8"))
        b = b[cut:]
    out.append(b.decode("utf-8"))
    return "\r\n ".join(out)


def main():
    try:
        items = json.load(open("calendar.json")).get("items") or []
    except Exception as err:
        print("Calendar feed: calendar.json not readable (%s), feed left as it was" % err)
        return
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    L = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Alpha Intel Desk//Catalyst Calendar//EN", "CALSCALE:GREGORIAN",
         "METHOD:PUBLISH", "X-WR-CALNAME:Alpha Intel Desk: Catalyst Calendar",
         "X-WR-CALDESC:" + esc("Dates that move prediction markets: economic data, the Fed, politics, world events "
                               "and more. Live odds on Polymarket, Kalshi and Alpha Arcade at " + CAL),
         "X-WR-TIMEZONE:America/New_York", "REFRESH-INTERVAL;VALUE=DURATION:PT6H", "X-PUBLISHED-TTL:PT6H"]
    n = 0
    for x in items:
        if x.get("kind") != "scheduled" or not x.get("date"):
            continue
        try:
            start = datetime.strptime(x["date"], F).replace(tzinfo=timezone.utc)
            end = datetime.strptime(x["end"], F).replace(tzinfo=timezone.utc) if x.get("end") else None
        except ValueError:
            continue
        uid = hashlib.sha1((x.get("name", "") + "|" + x["date"][:10]).encode()).hexdigest()[:16] + "@alphainteldesk.com"
        name = x.get("name", "") + (" (expected date)" if x.get("est") else "")
        desc = [x.get("note") or ""]
        m = x.get("market")
        if m and m.get("title"):
            desc.append("Related market: %s (%s)" % (m["title"], m.get("outcome") or "Yes"))
        desc += ["Live odds on Polymarket, Kalshi and Alpha Arcade: " + CAL,
                 "Not financial advice. Always check each site's rules."]
        L += ["BEGIN:VEVENT", "UID:" + uid, "DTSTAMP:" + now]
        if x.get("allday"):
            d0 = start.date()
            d1 = (end.date() if end else d0) + timedelta(days=1)
            L += ["DTSTART;VALUE=DATE:" + d0.strftime("%Y%m%d"), "DTEND;VALUE=DATE:" + d1.strftime("%Y%m%d"),
                  "TRANSP:TRANSPARENT"]
        else:
            L += ["DTSTART:" + start.strftime("%Y%m%dT%H%M%SZ"),
                  "DTEND:" + (end or start + timedelta(minutes=30)).strftime("%Y%m%dT%H%M%SZ"), "TRANSP:TRANSPARENT"]
        L += ["SUMMARY:" + esc(name), "DESCRIPTION:" + esc("\n\n".join(d for d in desc if d)),
              "URL:" + CAL, "CATEGORIES:" + esc(CATS.get(x.get("cat"), "Catalyst")), "END:VEVENT"]
        n += 1
    L.append("END:VCALENDAR")
    if n == 0:
        print("Calendar feed: no scheduled events found, feed left as it was")
        return
    body = "\r\n".join(fold(l) for l in L) + "\r\n"
    try:
        old = open(OUT, encoding="utf-8").read()
    except Exception:
        old = ""
    strip = lambda s: "\n".join(l for l in s.splitlines() if not l.startswith("DTSTAMP:"))
    if strip(old) == strip(body.replace("\r\n", "\n")):           # nothing changed but the stamp: don't churn git
        print("Calendar feed: %d events, unchanged" % n)
        return
    open(OUT, "w", encoding="utf-8", newline="").write(body)
    print("Calendar feed: %d events written to %s" % (n, OUT))


if __name__ == "__main__":
    main()
