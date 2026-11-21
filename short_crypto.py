"""Nov 21, 2026 (James): weekly and daily crypto price contracts were swamping the Danger Zone track record
(a 3-day Bitcoin/ETH price bracket is a coin flip on one week's swing). They are no longer listed on the
Danger Zone and are not counted in the track record. Monthly and longer crypto markets stay
("What price will Bitcoin hit in November?", "...in 2026?", "Bitcoin $150K by December 31?").

Rule: a crypto coin in the title AND a specific day, day range, time of day or "today/this week" in the title,
unless it is a "by <month>" deadline market."""
import re

COIN = re.compile(r"\b(bitcoin|btc|ethereum|eth|ether|solana|sol|xrp|ripple|dogecoin|doge|bnb|cardano|litecoin|ltc|"
                  r"hyperliquid|algorand|algo|crypto|cryptocurrency)\b", re.I)
_MON = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
SHORT = re.compile(r"\b%s\s+\d{1,2}\b|\b\d{1,2}/\d{1,2}\b|\btoday\b|\btomorrow\b|\btonight\b|\bthis week\b|\bweekly\b|"
                   r"\bdaily\b|\bhourly\b|\d\s*(?:am|pm)\b" % _MON, re.I)
BY = re.compile(r"\bby\s+(?:the\s+)?(?:end\s+of\s+)?%s" % _MON, re.I)


def short_crypto(title):
    t = title or ""
    return bool(COIN.search(t) and SHORT.search(t) and not BY.search(t))


if __name__ == "__main__":
    for t, want in [("What price will Bitcoin hit November 16-22?", True), ("BTC price on Nov 20, 2026 at 5pm EST?", True),
                    ("Bitcoin above ___ on November 20?", True), ("ETH price on Nov 20, 2026 at 5pm EST?", True),
                    ("Bitcoin price today at 5pm EST?", True), ("What price will Bitcoin hit in November?", False),
                    ("How low will BTC get in November?", False), ("What price will Bitcoin hit in 2026?", False),
                    ("Will Bitcoin hit $150K by December 31, 2026?", False), ("Dancing with the Stars · Episode 11 Elimination", False),
                    ("Elon Musk # tweets November 13 - November 20, 2026?", False), ("Fed decision on December 9?", False)]:
        assert short_crypto(t) == want, t
    print("short_crypto: all checks pass")
