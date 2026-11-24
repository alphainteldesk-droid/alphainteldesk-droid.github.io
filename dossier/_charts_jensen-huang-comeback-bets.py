"""Chart for Dossier No. 2 (Jensen Huang comeback bets), drawn from Polymarket's public trade records
read Nov 24, 2026 (frozen: this is the receipt). data.json = hourly YES price of "rejoin NVIDIA by Dec 31, 2026"
(Polymarket CLOB price history) + YES dollars bought per hour across the event's four contracts (data-api v2 trades)."""
import json, datetime as dt, sys
D = json.load(open(sys.argv[1] if len(sys.argv) > 1 else 'data.json'))
UTC = dt.timezone.utc
ET = dt.timezone(dt.timedelta(hours=-5))
T0 = dt.datetime(2026, 11, 21, 0, tzinfo=UTC).timestamp()
ANN = dt.datetime(2026, 11, 23, 13, 56, tzinfo=UTC).timestamp()      # Nov 30 contract jumps 13:55:56 UTC
T1 = dt.datetime(2026, 11, 23, 23, tzinfo=UTC).timestamp()   # room on the right for the labels


def esc(s):
    return s.replace('&', '&amp;').replace('<', '&lt;')


def chart():
    W, H, L, Rm, T, B = 760, 340, 50, 24, 34, 40
    bh = 70                                       # bar band height (bottom)
    X = lambda t: L + (t - T0) / (T1 - T0) * (W - L - Rm)
    PY0, PY1 = T, H - B - bh - 14                 # price band
    Y = lambda v: PY0 + (16 - v) / 16 * (PY1 - PY0)
    o = [f'<svg viewBox="0 0 {W} {H}" class="chart" role="img" aria-label="Polymarket YES price for Jensen Huang rejoining Nvidia by Dec 31, 2026, and YES dollars bought per hour, Nov 21 to Nov 23, 2026">']
    for v in (0, 4, 8, 12, 16):
        o.append(f'<line x1="{L}" x2="{W-Rm}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" class="g"/><text x="{L-8}" y="{Y(v)+4:.1f}" text-anchor="end" class="ax">{v}¢</text>')
    d = dt.datetime(2026, 11, 21, 12, tzinfo=ET)
    while d.timestamp() <= T1:
        if d.timestamp() >= T0:
            o.append(f'<text x="{X(d.timestamp()):.1f}" y="{H-12}" text-anchor="middle" class="ax">{d.strftime("%a %b %-d")}</text>')
        d += dt.timedelta(days=1)
    # bars: YES $ per hour (all four contracts), before the announcement only
    hrs = [(t, v) for t, v in D['hours'] if T0 <= t < ANN]
    mx = max(v for _, v in hrs)
    bw = (W - L - Rm) / ((T1 - T0) / 3600) * 0.8
    base = H - B
    for t, v in hrs:
        h = v / mx * bh
        o.append(f'<rect x="{X(t):.1f}" y="{base-h:.1f}" width="{bw:.1f}" height="{h:.1f}" fill="rgba(63,219,230,.45)"/>')
    o.append(f'<text x="{L}" y="{base-bh-2:.1f}" class="ax">YES $ bought per hour (bars, max ${mx:,})</text>')
    # events
    ev = [(dt.datetime(2026, 11, 21, 5, tzinfo=UTC).timestamp(), 'White House calls board'),
          (dt.datetime(2026, 11, 23, 2, 54, tzinfo=UTC).timestamp(), 'Trump post'),
          (ANN, 'Announced')]
    for i, (t, lab) in enumerate(ev):
        o.append(f'<line x1="{X(t):.1f}" x2="{X(t):.1f}" y1="{T}" y2="{base}" class="ev"/>'
                 f'<text x="{X(t)+(-4 if i == 1 else 4):.1f}" y="{T-10}" text-anchor="{"end" if i == 1 else "start"}" class="evt">{esc(lab)}</text>')
    pts = [(t, v * 100) for t, v in D['dec26'] if T0 <= t < ANN]
    o.append('<polyline points="' + ' '.join(f'{X(t):.1f},{Y(v):.1f}' for t, v in pts) + '" fill="none" stroke="#6f8cff" stroke-width="2.4" stroke-linejoin="round"/>')
    t, v = pts[-1]
    o.append(f'<circle cx="{X(t):.1f}" cy="{Y(v):.1f}" r="4" fill="#6f8cff"/>'
             f'<text x="{X(t)-8:.1f}" y="{Y(v)-10:.1f}" text-anchor="end" class="lab" fill="#6f8cff">{v:.1f}¢ just before</text>'
             f'<text x="{X(ANN)+6:.1f}" y="{Y(13):.1f}" class="lab" fill="#3ee88a">→ 99.5¢</text>'
             f'<text x="{X(ANN)+6:.1f}" y="{Y(13)+16:.1f}" class="ax">after the news</text>')
    o.append('</svg>')
    return ''.join(o)


if __name__ == '__main__':
    json.dump({'chart': chart()}, open(sys.argv[2] if len(sys.argv) > 2 else 'charts.json', 'w'))
    print('chart ok')
