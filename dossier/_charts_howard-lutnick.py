"""Charts for the Lutnick Dossier, drawn from the Nov 22, 2026 data (frozen: this is the receipt)."""
import json, datetime as dt
R = json.load(open('/home/claude/dossier/lutnick_rules.json'))
G = [g for g in json.load(open('/home/claude/dossier/gap_chart.json'))['gaps'] if 'Lutnick' in g['title']][0]
C = {'polymarket': '#6f8cff', 'kalshi': '#3ee88a'}
UTC = dt.timezone.utc


def esc(s):
    return s.replace('&', '&amp;').replace('<', '&lt;')


def history():
    W, H, L, Rm, T, B = 760, 300, 46, 128, 26, 34
    pts = {s: [(t, v) for t, v in G['series'][s]] for s in ('polymarket', 'kalshi')}
    t0 = min(p[0][0] for p in pts.values()); t1 = max(p[-1][0] for p in pts.values())
    lo, hi = 30, 70
    X = lambda t: L + (t - t0) / (t1 - t0) * (W - L - Rm)
    Y = lambda v: T + (hi - v) / (hi - lo) * (H - T - B)
    o = [f'<svg viewBox="0 0 {W} {H}" class="chart" role="img" aria-label="YES price for Lutnick out by March 31, 2027 on Polymarket and Kalshi, Nov 15 to Nov 22, 2026">']
    for v in range(30, 71, 10):
        o.append(f'<line x1="{L}" x2="{W-Rm}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" class="g"/><text x="{L-8}" y="{Y(v)+4:.1f}" text-anchor="end" class="ax">{v}¢</text>')
    d = dt.datetime.fromtimestamp(t0, UTC).replace(hour=12, minute=0, second=0)
    while d.timestamp() <= t1:
        if d.timestamp() >= t0:
            o.append(f'<text x="{X(d.timestamp()):.1f}" y="{H-10}" text-anchor="middle" class="ax">{d.strftime("%b %-d")}</text>')
        d += dt.timedelta(days=1)
    for t, lab in ((dt.datetime(2026, 11, 16, 17, tzinfo=UTC).timestamp(), 'Trump: not replacing him'),
                   (dt.datetime(2026, 11, 21, 15, tzinfo=UTC).timestamp(), 'WSJ: $25M gift')):
        if t0 <= t <= t1:
            o.append(f'<line x1="{X(t):.1f}" x2="{X(t):.1f}" y1="{T}" y2="{H-B}" class="ev"/><text x="{X(t)+4:.1f}" y="{T-8}" class="evt">{esc(lab)}</text>')
    for s, p in pts.items():
        o.append('<polyline points="' + ' '.join(f'{X(t):.1f},{Y(v):.1f}' for t, v in p) + f'" fill="none" stroke="{C[s]}" stroke-width="2.4" stroke-linejoin="round"/>')
        t, v = p[-1]
        o.append(f'<circle cx="{X(t):.1f}" cy="{Y(v):.1f}" r="4" fill="{C[s]}"/><text x="{X(t)+9:.1f}" y="{Y(v)+4:.1f}" class="lab" fill="{C[s]}">{"Kalshi" if s == "kalshi" else "Polymarket"} {v:.1f}¢</text>')
    o.append('</svg>')
    return ''.join(o)


def ladder():
    k = []
    for m in R['kalshi_markets']:
        c = dt.datetime.fromisoformat(m[6].replace('Z', '+00:00'))
        if c < dt.datetime(2026, 11, 28, tzinfo=UTC):
            continue
        k.append((c, (float(m[4]) + float(m[5])) / 2 * 100))
    k.sort()
    p = []
    for name, pr, end, vol in R['poly_markets']:
        c = dt.datetime.fromisoformat(end.replace('Z', '+00:00'))
        if c > dt.datetime(2026, 11, 25, tzinfo=UTC):
            p.append((c, float(json.loads(pr)[0]) * 100))
    p.sort()
    W, H, L, Rm, T, B = 760, 300, 46, 30, 22, 40
    a = dt.datetime(2026, 11, 22, tzinfo=UTC); z = dt.datetime(2029, 1, 20, tzinfo=UTC)
    X = lambda c: L + (c - a).total_seconds() / (z - a).total_seconds() * (W - L - Rm)
    Y = lambda v: T + (100 - v) / 100 * (H - T - B)
    o = [f'<svg viewBox="0 0 {W} {H}" class="chart" role="img" aria-label="Chance Lutnick is out by each deadline, Kalshi and Polymarket, Nov 22, 2026">']
    for v in range(0, 101, 25):
        o.append(f'<line x1="{L}" x2="{W-Rm}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" class="g"/><text x="{L-8}" y="{Y(v)+4:.1f}" text-anchor="end" class="ax">{v}%</text>')
    for yr, mo, lab in ((2027, 1, 'Jan 2027'), (2027, 7, 'Jul 2027'), (2028, 1, 'Jan 2028'), (2028, 7, 'Jul 2028'), (2029, 1, 'Jan 2029')):
        o.append(f'<text x="{X(dt.datetime(yr, mo, 1, tzinfo=UTC)):.1f}" y="{H-14}" text-anchor="middle" class="ax">{lab}</text>')
    cd = dt.datetime(2027, 4, 1, tzinfo=UTC)
    o.append(f'<line x1="{X(cd):.1f}" x2="{X(cd):.1f}" y1="{T}" y2="{H-B}" class="call"/><text x="{X(cd)+6:.1f}" y="{T+10}" class="callt">Our call: still in office Mar 31, 2027</text>')
    sd = dt.datetime(2027, 1, 3, tzinfo=UTC)
    o.append(f'<line x1="{X(sd):.1f}" x2="{X(sd):.1f}" y1="{T+20}" y2="{H-B}" class="ev"/><text x="{X(sd)+5:.1f}" y="{T+36}" class="evt">Dem. Senate, Jan 3</text>')
    o.append('<polyline points="' + ' '.join(f'{X(c):.1f},{Y(v):.1f}' for c, v in k) + f'" fill="none" stroke="{C["kalshi"]}" stroke-width="2.4"/>')
    for c, v in k:
        o.append(f'<circle cx="{X(c):.1f}" cy="{Y(v):.1f}" r="3.8" fill="{C["kalshi"]}"><title>Kalshi: out before {c.strftime("%b %-d, %Y")} = {v:.1f}%</title></circle>')
    for c, v in p:
        o.append(f'<rect x="{X(c)-4.5:.1f}" y="{Y(v)-4.5:.1f}" width="9" height="9" fill="{C["polymarket"]}"><title>Polymarket: out by {c.strftime("%b %-d, %Y")} = {v:.1f}%</title></rect>')
    o.append(f'<g class="leg"><rect x="{W-Rm-130}" y="{H-B-50}" width="9" height="9" fill="{C["polymarket"]}"/><text x="{W-Rm-114}" y="{H-B-42}">Polymarket</text>'
             f'<circle cx="{W-Rm-125.5}" cy="{H-B-25}" r="4.2" fill="{C["kalshi"]}"/><text x="{W-Rm-114}" y="{H-B-21}">Kalshi</text></g>')
    o.append('</svg>')
    return ''.join(o), k, p


h = history(); l, k, p = ladder()
json.dump({'history': h, 'ladder': l}, open('/home/claude/dossier/charts.json', 'w'))
for c, v in k: print('K', c.date(), round(v, 1))
for c, v in p: print('P', c.date(), round(v, 1))
