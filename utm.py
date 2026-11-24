"""Nov 24, 2026 (James): tag every link we post with where it was posted, so Google Analytics / GoatCounter show
which channel each visit came from. tag("https://alphainteldesk.com/x.html#c=1", "telegram", "digest")
-> "https://alphainteldesk.com/x.html?utm_source=telegram&utm_medium=digest#c=1". Only our own site's links get tagged;
any old utm_ tags are replaced."""
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode


def tag(url, source, medium=None):
    p = urlsplit(url)
    if "alphainteldesk.com" not in p.netloc:
        return url
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not k.startswith("utm_")]
    q.append(("utm_source", source))
    if medium:
        q.append(("utm_medium", medium))
    return urlunsplit((p.scheme, p.netloc, p.path or "/", urlencode(q), p.fragment))
