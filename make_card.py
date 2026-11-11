# Alpha Intel Desk: share-preview images ("Today on the desk") for X, Telegram, iMessage etc.
# Reads gaps.json, calendar.json, movers.json and draws:
#   card.jpg       homepage preview: top price gap (all 3 sites first) + next calendar event + biggest mover
#   card-gaps.jpg  Gap Scanner page preview: top 3 price gaps
# Then points og:image / twitter:image in index.html and gap-scanner.html at the new images (?v=time),
# so X fetches the fresh picture when a link is shared. To keep the repo small it redraws at most
# every MIN_HOURS unless the top gap or the next event changed.
# Fonts in fonts/ (JetBrains Mono, Space Grotesk; SIL Open Font License). Public market data only.
import hashlib, json, os, re, textwrap
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1200, 630
MIN_HOURS = 3
ET = ZoneInfo("America/New_York")
NAVY, PANEL, LINE = (11, 20, 32), (17, 29, 44), (31, 48, 68)
CYAN, AMBER, TEXT, MUTED = (63, 219, 230), (255, 179, 71), (232, 238, 245), (143, 163, 184)
GREEN, RED = (62, 232, 138), (255, 122, 122)
SITE = {"polymarket": "POLY", "kalshi": "KALSHI", "alpha": "ALPHA"}
n = datetime.now(timezone.utc)


def font(name, size):
    return ImageFont.truetype(os.path.join("fonts", name), size)


MONO, MONO_B = "JetBrainsMono-Bold.ttf", "JetBrainsMono-ExtraBold.ttf"
SANS, SANS_B = "SpaceGrotesk-Medium.ttf", "SpaceGrotesk-Bold.ttf"


def load(name):
    try:
        return json.load(open(name))
    except Exception:
        return {}


def fit(d, text, fnt, width):
    """Cut text with … so it fits in width pixels."""
    if d.textlength(text, font=fnt) <= width:
        return text
    while text and d.textlength(text + "…", font=fnt) > width:
        text = text[:-1]
    return text.rstrip() + "…"


def wrap(d, text, fnt, width, lines):
    words, out, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textlength(t, font=fnt) <= width:
            cur = t
        else:
            out.append(cur); cur = w
    out.append(cur)
    if len(out) > lines:
        out = out[:lines]
        out[-1] = fit(d, out[-1] + " …", fnt, width)
    return out


def background():
    img = Image.new("RGB", (W, H), NAVY)
    try:                                           # the desk photo, darkened, on the right
        b = Image.open("banner.jpg").convert("RGB")
        b = b.resize((int(b.width * H / b.height), H))
        b = b.crop((b.width - 760, 0, b.width, H)).filter(ImageFilter.GaussianBlur(1.2))
        b = Image.blend(Image.new("RGB", b.size, NAVY), b, 0.38)
        img.paste(b, (W - 760, 0))
    except Exception:
        pass
    shade = Image.new("L", (W, 1))                 # fade the photo into the navy on the left
    for x in range(W):
        shade.putpixel((x, 0), 255 if x < 440 else max(0, int(255 - (x - 440) * 255 / 520)))
    img.paste(Image.new("RGB", (W, H), NAVY), (0, 0), shade.resize((W, H)))
    d = ImageDraw.Draw(img, "RGBA")
    for x in range(0, W, 30):                       # faint desk grid
        d.line([(x, 0), (x, H)], fill=(63, 219, 230, 10))
    for y in range(0, H, 30):
        d.line([(0, y), (W, y)], fill=(63, 219, 230, 10))
    for (x, y, dx, dy) in ((14, 14, 1, 1), (W - 15, 14, -1, 1), (14, H - 15, 1, -1), (W - 15, H - 15, -1, -1)):
        d.line([(x, y), (x + 26 * dx, y)], fill=AMBER, width=3)   # amber corner brackets
        d.line([(x, y), (x, y + 26 * dy)], fill=AMBER, width=3)
    return img, d


def header(d, sub):
    cx, cy, r = 62, 62, 22                          # α in a crosshair
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=CYAN, width=3)
    for a, b in (((cx - r - 7, cy), (cx - r + 7, cy)), ((cx + r - 7, cy), (cx + r + 7, cy)),
                 ((cx, cy - r - 7), (cx, cy - r + 7)), ((cx, cy + r - 7), (cx, cy + r + 7))):
        d.line([a, b], fill=CYAN, width=3)
    d.text((cx, cy - 1), "α", font=font(MONO_B, 34), fill=TEXT, anchor="mm")   # JetBrains Mono has the Greek α
    d.text((100, 44), "ALPHA INTEL DESK", font=font(MONO_B, 26), fill=AMBER)
    d.text((100, 76), sub, font=font(MONO, 15), fill=MUTED)
    stamp = n.astimezone(ET).strftime("%b %-d · %-I:%M %p ET").upper()
    f = font(MONO_B, 17)
    w = d.textlength(stamp, font=f)
    d.ellipse([W - 70 - w - 22, 52, W - 70 - w - 10, 64], fill=CYAN)
    d.text((W - 62 - w, 47), stamp, font=f, fill=CYAN)


def footer(d):
    d.text((44, H - 46), "alphainteldesk.com", font=font(MONO_B, 20), fill=CYAN)
    d.text((W - 44, H - 44), "Polymarket · Kalshi · Alpha Arcade  ·  Not financial advice",
           font=font(MONO, 15), fill=MUTED, anchor="ra")


def price_boxes(d, g, x, y, bw=150, bh=78, gap=12):
    for i, s in enumerate(("polymarket", "kalshi", "alpha")):
        bx = x + i * (bw + gap)
        p = (g.get("prices") or {}).get(s)
        edge = AMBER if s == "alpha" else LINE
        d.rounded_rectangle([bx, y, bx + bw, y + bh], 8, fill=(5, 12, 20, 220), outline=edge, width=2)
        d.text((bx + bw / 2, y + 16), SITE[s], font=font(MONO_B, 14), fill=AMBER if s == "alpha" else MUTED, anchor="mm")
        if p is None:
            d.text((bx + bw / 2, y + 50), "NOT LISTED", font=font(MONO, 15), fill=(86, 104, 124), anchor="mm")
        else:
            col = GREEN if s == g["low"]["site"] else RED if s == g["high"]["site"] else TEXT
            d.text((bx + bw / 2, y + 50), "%d¢" % round(p), font=font(MONO_B, 34), fill=col, anchor="mm")
    return x + 3 * (bw + gap)


def gap_pill(d, g, x, y, h=78):
    d.rounded_rectangle([x, y, x + 168, y + h], 8, fill=AMBER)
    d.text((x + 84, y + 32), "%.1f¢" % g["net"], font=font(MONO_B, 34), fill=(17, 17, 17), anchor="mm")
    d.text((x + 84, y + 61), "GAP AFTER FEES", font=font(MONO_B, 12), fill=(17, 17, 17), anchor="mm")


def until(iso):
    s = int((datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) - n).total_seconds())
    if s <= 0:
        return "now"
    dd, hh, mm = s // 86400, s % 86400 // 3600, s % 3600 // 60
    return ("in %dd %dh" % (dd, hh)) if dd else ("in %dh %dm" % (hh, mm))


def next_event(cal):
    best = None
    for x in cal.get("items") or []:
        if x.get("allday") or x.get("kind") == "resolves" or (x.get("impact") or 1) < 2:
            continue
        try:
            t = datetime.strptime(x["date"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except (KeyError, ValueError):
            continue
        if t > n and (best is None or t < best[0]):
            best = (t, x)
    return best[1] if best else None


def featured(gl):
    """Nov 10: rotate the featured gap every 3 hours among the top 6, so share previews change.
    Skips gaps the order books showed aren't really there ($0 fillable)."""
    real = [x for x in gl if not (x.get("fill") and not x["fill"].get("usd"))] or gl
    pool = real[:6]
    return pool[int(n.timestamp() // 10800) % len(pool)] if pool else None


def home_card(gaps, cal, mov):
    img, d = background()
    header(d, "TODAY ON THE DESK · REAL-TIME PREDICTION MARKET INTEL")
    gl = gaps.get("gaps") or []
    g = featured(gl)
    y = 128
    if g:
        d.text((44, y), "PRICE GAP · " + ("ALL 3 SITES" if g.get("all3") else "ACROSS SITES"), font=font(MONO_B, 17), fill=CYAN)
        lines = wrap(d, g["title"], font(SANS_B, 40), 1110, 2)
        for i, ln in enumerate(lines):
            d.text((44, y + 26 + i * 46), ln, font=font(SANS_B, 40), fill=TEXT)
        y2 = y + 30 + len(lines) * 46
        d.text((44, y2), fit(d, "Outcome: " + g["outcome"], font(SANS, 20), 700), font=font(SANS, 20), fill=MUTED)
        xe = price_boxes(d, g, 44, y2 + 36)
        gap_pill(d, g, xe + 8, y2 + 36)
        y = y2 + 140
    else:
        d.text((44, y), "PRICE GAPS ACROSS POLYMARKET, KALSHI & ALPHA ARCADE", font=font(MONO_B, 17), fill=CYAN)
        d.text((44, y + 30), "Live price-gap scanner, updated every 20 minutes", font=font(SANS_B, 36), fill=TEXT)
        y += 120
    # bottom row: next event (left) and biggest mover (right)
    yb = max(y + 8, 420)
    ev = next_event(cal)
    d.rounded_rectangle([44, yb, 590, yb + 118], 8, fill=(5, 12, 20, 215), outline=(255, 179, 71, 150), width=2)
    d.text((62, yb + 14), "NEXT UP · CATALYST CALENDAR", font=font(MONO_B, 14), fill=CYAN)
    if ev:
        d.text((62, yb + 38), fit(d, ev["name"], font(SANS_B, 26), 510), font=font(SANS_B, 26), fill=TEXT)
        when = datetime.strptime(ev["date"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).astimezone(ET)
        d.text((62, yb + 76), when.strftime("%a %b %-d · %-I:%M %p ET"), font=font(MONO, 17), fill=MUTED)
        d.text((572, yb + 76), until(ev["date"]).upper(), font=font(MONO_B, 20), fill=AMBER, anchor="ra")
    else:
        d.text((62, yb + 40), "Economic data, the Fed, earnings & more", font=font(SANS_B, 24), fill=TEXT)
    ml = (mov.get("movers") or [])[:3]                 # Nov 10: rotate among the top 3 movers every 3 hours
    mv = ml[int(n.timestamp() // 10800) % len(ml)] if ml else None
    d.rounded_rectangle([610, yb, W - 44, yb + 118], 8, fill=(5, 12, 20, 215), outline=LINE, width=2)
    d.text((628, yb + 14), "BIGGEST MOVER · 24H", font=font(MONO_B, 14), fill=CYAN)
    if mv:
        ch = mv["change"]
        d.text((628, yb + 38), fit(d, mv["title"], font(SANS_B, 24), 510), font=font(SANS_B, 24), fill=TEXT)
        d.text((628, yb + 76), fit(d, mv["outcome"] + " · " + mv["name"], font(MONO, 16), 360), font=font(MONO, 16), fill=MUTED)
        d.text((W - 62, yb + 72), "%+d¢" % round(ch), font=font(MONO_B, 30), fill=GREEN if ch > 0 else RED, anchor="ra")
    footer(d)
    return img


def gaps_card(gaps):
    img, d = background()
    header(d, "GAP SCANNER · SAME QUESTION, DIFFERENT PRICE")
    gl = (gaps.get("gaps") or [])[:3]
    d.text((44, 120), "TOP PRICE GAPS AFTER FEES · POLYMARKET · KALSHI · ALPHA ARCADE", font=font(MONO_B, 16), fill=CYAN)
    y = 152
    for g in gl:
        d.rounded_rectangle([44, y, W - 44, y + 132], 10, fill=(5, 12, 20, 215),
                            outline=(255, 179, 71, 170) if g.get("all3") else LINE, width=2)
        tag = "ALL 3 SITES  " if g.get("all3") else ""
        if tag:
            d.rounded_rectangle([62, y + 14, 62 + d.textlength("ALL 3", font=font(MONO_B, 13)) + 14, y + 34], 3, fill=AMBER)
            d.text((69, y + 17), "ALL 3", font=font(MONO_B, 13), fill=(17, 17, 17))
        tx = 62 + (d.textlength("ALL 3", font=font(MONO_B, 13)) + 24 if tag else 0)
        d.text((tx, y + 12), fit(d, g["title"], font(SANS_B, 24), W - 44 - 18 - tx), font=font(SANS_B, 24), fill=TEXT)
        d.text((62, y + 98), fit(d, g["outcome"], font(SANS, 18), 230), font=font(SANS, 18), fill=MUTED)
        price_boxes(d, g, 300, y + 46, bw=170, bh=72)
        gap_pill(d, g, W - 44 - 18 - 168, y + 46, h=72)
        y += 146
    if not gl:
        d.text((44, 200), "Prices are lined up right now. Checked every 20 minutes.", font=font(SANS_B, 34), fill=TEXT)
    footer(d)
    return img


def point(page, img_url):
    """Point a page's og:image / twitter:image at the new picture."""
    try:
        h = open(page).read()
    except Exception:
        return
    h2 = re.sub(r'(<meta property="og:image" content=")[^"]*(")', r"\g<1>" + img_url + r"\2", h)
    if 'name="twitter:image"' in h2:
        h2 = re.sub(r'(<meta name="twitter:image" content=")[^"]*(")', r"\g<1>" + img_url + r"\2", h2)
    else:
        h2 = h2.replace('<meta name="twitter:card"', '<meta name="twitter:image" content="' + img_url + '">\n<meta name="twitter:card"', 1)
    if h2 != h:
        open(page, "w").write(h2)


def main():
    gaps, cal, mov = load("gaps.json"), load("calendar.json"), load("movers.json")
    gl = gaps.get("gaps") or []
    top = featured(gl) or {}
    ev = next_event(cal) or {}
    key = hashlib.md5(json.dumps([top.get("title"), top.get("outcome"), ev.get("name"), int(n.timestamp() // 10800),
                                  [g.get("title") for g in gl[:3]]]).encode()).hexdigest()[:10]
    st = load("card_state.json")
    age = (n.timestamp() - st.get("ts", 0)) / 3600
    if st.get("key") == key and age < MIN_HOURS and os.path.exists("card.jpg"):
        print("Card: unchanged, %.1fh old - not redrawn" % age)
        return
    home_card(gaps, cal, mov).save("card.jpg", quality=84, optimize=True, progressive=True)
    gaps_card(gaps).save("card-gaps.jpg", quality=84, optimize=True, progressive=True)
    v = n.strftime("%Y%m%d%H%M")
    point("index.html", "https://alphainteldesk.com/card.jpg?v=" + v)
    point("gap-scanner.html", "https://alphainteldesk.com/card-gaps.jpg?v=" + v)
    json.dump({"key": key, "ts": n.timestamp(), "v": v}, open("card_state.json", "w"))
    print("Card: redrawn (v=%s) | top gap: %s | next: %s" % (v, top.get("title", "-")[:50], ev.get("name", "-")))


if __name__ == "__main__":
    main()
