/* Nov 21 (James): Live Gap Chart. Real price history for today's biggest gap (gap_chart.json, written by gap_chart.py).
   Mount: <div id="gapchart"></div>. Same look as the X card: glowing lines, scan beam, radar, pulsing end dots, gap bracket. */
(function () {
  var box = document.getElementById('gapchart');
  if (!box) return;
  var C = { polymarket: '#5b8cff', kalshi: '#2fe0a0', alpha: '#ffb347' };
  var N = { polymarket: 'POLYMARKET', kalshi: 'KALSHI', alpha: 'ALPHA ARCADE' };
  var css = document.createElement('style');
  css.textContent =
    '.gc{position:relative;margin:18px 0 20px;border:1px solid rgba(63,219,230,.35);border-radius:10px;overflow:hidden;' +
    'background:radial-gradient(ellipse at 85% 0%,rgba(63,219,230,.12),transparent 60%),radial-gradient(ellipse at 0% 100%,rgba(255,179,71,.08),transparent 60%),' +
    'linear-gradient(rgba(63,219,230,.04) 1px,transparent 1px) 0 0/28px 28px,linear-gradient(90deg,rgba(63,219,230,.04) 1px,transparent 1px) 0 0/28px 28px,#070f19;' +
    'box-shadow:0 0 40px rgba(63,219,230,.1),inset 0 0 50px rgba(0,0,0,.45)}' +
    '.gc-h{display:flex;flex-wrap:wrap;align-items:flex-start;justify-content:space-between;gap:10px 20px;padding:16px 18px 4px}' +
    '.gc-eb{display:flex;align-items:center;gap:8px;font:800 .78rem "JetBrains Mono",monospace;letter-spacing:.2em;color:var(--cyan,#3fdbe6)}' +
    '.gc-eb i{width:9px;height:9px;border-radius:50%;background:#3fdbe6;box-shadow:0 0 8px #3fdbe6;animation:gcp 1.4s infinite}' +
    '@keyframes gcp{0%{box-shadow:0 0 0 0 rgba(63,219,230,.6)}100%{box-shadow:0 0 0 9px rgba(63,219,230,0)}}' +
    '.gc-t{margin:6px 0 0;font-size:1.15rem;font-weight:800;line-height:1.25;color:#e8eef5}' +
    '.gc-t span{color:#8fa3b8;font-weight:600}' +
    '.gc-h>div:first-child{flex:1 1 320px;min-width:0}.gc-n{text-align:right;flex:none;margin-left:auto}' +
    '.gc-n b{display:block;font:800 2.1rem/1 "JetBrains Mono",monospace;color:#ffb347;text-shadow:0 0 18px rgba(255,179,71,.55)}' +
    '.gc-n small{font:700 .66rem "JetBrains Mono",monospace;letter-spacing:.14em;color:#c9d3dc}' +
    '.gc-n .gr{margin-left:6px}' +
    '.gc canvas{display:block;width:100%}' +
    '.gc-f{display:flex;flex-wrap:wrap;align-items:center;gap:8px 18px;padding:2px 18px 14px;font:700 .74rem "JetBrains Mono",monospace;color:#a9bccf}' +
    '.gc-f .k{display:inline-flex;align-items:center;gap:6px;letter-spacing:.06em}' +
    '.gc-f .k i{width:14px;height:4px;border-radius:2px}' +
    '.gc-f .k b{color:#e8eef5}' +
    '.gc-f a{margin-left:auto;color:#3fdbe6;letter-spacing:.06em}' +
    '.gc-nt{padding:0 18px 14px;margin-top:-6px;color:#6f8399;font-size:.78rem}' +
    '@media(max-width:640px){.gc-h{padding:12px 12px 2px}.gc-t{font-size:1rem}.gc-n b{font-size:1.6rem}.gc-f{padding:2px 12px 12px}.gc-f a{margin-left:0}.gc-nt{padding:0 12px 12px}}';
  document.head.appendChild(css);

  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function gkey(g) { var t = g.title + '|' + g.outcome, h = 5381; for (var k = 0; k < t.length; k++) h = ((h * 33) ^ t.charCodeAt(k)) >>> 0; return h.toString(36); }
  function c1(v) { return (Math.round(v * 10) / 10).toFixed(1); }

  fetch('/gap_chart.json?v=' + Date.now()).then(function (r) { return r.json(); }).then(function (d) {
    var sites = ['polymarket', 'kalshi', 'alpha'].filter(function (s) { return d.series && d.series[s] && d.series[s].length; });
    if (sites.length < 2) return;
    var gr = d.grade ? '<i class="gr gr-' + esc(d.grade) + '">' + esc(d.grade) + '</i>' : '';
    box.innerHTML = '<section class="gc" aria-label="Price history for today’s biggest gap">' +
      '<div class="gc-h"><div><div class="gc-eb"><i></i>TODAY’S BIGGEST GAP · LIVE</div>' +
      '<p class="gc-t">' + esc(d.title) + ' <span>· ' + esc(d.outcome) + '</span></p></div>' +
      '<div class="gc-n"><b>' + c1(d.net) + '¢</b><small>GAP AFTER FEES' + (gr ? ' · GRADED</small>' + gr : '</small>') + '</div></div>' +
      '<canvas aria-hidden="true"></canvas>' +
      '<div class="gc-f">' + sites.map(function (s) {
        return '<span class="k"><i style="background:' + C[s] + ';box-shadow:0 0 6px ' + C[s] + '"></i>' + N[s] + ' <b>' + c1(d.prices[s]) + '¢</b></span>';
      }).join('') + '<a href="#g-' + gkey(d) + '">See this gap ↓</a></div>' +
      '<p class="gc-nt">Yes price over the last ' + (d.days || 7) + ' days. Lines end at the Gap Scanner’s latest check' +
      (d.series.alpha ? '. Alpha Arcade has no public price history, so its line is our own checks and starts when we began recording it' : '') +
      '. Not financial advice.</p></section>';
    draw(d, sites, box.querySelector('canvas'));
  }).catch(function () {});

  function draw(d, sites, cv) {
    var ctx = cv.getContext('2d'), dpr = window.devicePixelRatio || 1, W, H, t0 = performance.now();
    var calm = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
    var all = [], tmin = Infinity, tmax = -Infinity;
    sites.forEach(function (s) { d.series[s].forEach(function (p) { all.push(p[1]); tmin = Math.min(tmin, p[0]); tmax = Math.max(tmax, p[0]); }); });
    tmin = Math.max(tmin, tmax - (d.days || 7) * 86400);
    var lo = Math.min.apply(null, all), hi = Math.max.apply(null, all), pad = Math.max(2, (hi - lo) * 0.15);
    lo = Math.max(0, lo - pad); hi = Math.min(100, hi + pad);
    var step = (hi - lo) > 40 ? 10 : (hi - lo) > 16 ? 5 : (hi - lo) > 6 ? 2 : 1;
    function size() {
      W = cv.clientWidth; H = W < 600 ? 250 : 330;
      cv.style.height = H + 'px'; cv.width = W * dpr; cv.height = H * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    size(); window.addEventListener('resize', function () { size(); if (calm) requestAnimationFrame(frame); });
    var TAU = Math.PI * 2;
    function frame(now) {
      var t = (now - t0) / 1000, phone = W < 600;
      var PL = phone ? 38 : 52, PR = phone ? 92 : 150, PT = 16, PB = 30, CW = W - PL - PR, CH = H - PT - PB;
      var X = function (ts) { return PL + CW * (ts - tmin) / Math.max(1, tmax - tmin); };
      var Y = function (v) { return PT + CH * (1 - (v - lo) / (hi - lo)); };
      ctx.clearRect(0, 0, W, H);
      ctx.font = '600 11px "JetBrains Mono",monospace'; ctx.textBaseline = 'middle'; ctx.textAlign = 'left';
      for (var v = Math.ceil(lo / step) * step; v <= hi; v += step) {
        var y = Y(v); ctx.strokeStyle = 'rgba(63,219,230,.09)'; ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(PL, y); ctx.lineTo(PL + CW, y); ctx.stroke();
        ctx.fillStyle = 'rgba(143,163,184,.75)'; ctx.fillText(v + '¢', 6, y);
      }
      ctx.textAlign = 'center';
      for (var day = new Date(tmin * 1000); day.getTime() / 1000 <= tmax; day.setDate(day.getDate() + 1)) {
        day.setHours(0, 0, 0, 0); var ts = day.getTime() / 1000; if (ts < tmin) continue;
        var x = X(ts); ctx.strokeStyle = 'rgba(63,219,230,.06)'; ctx.beginPath(); ctx.moveTo(x, PT); ctx.lineTo(x, PT + CH); ctx.stroke();
        ctx.fillStyle = 'rgba(143,163,184,.7)';
        ctx.fillText(phone ? day.toLocaleDateString('en-US', { weekday: 'narrow' }) : day.toLocaleDateString('en-US', { weekday: 'short' }) + ' ' + day.getDate(), x, H - 12);
      }
      // scan beam
      if (!calm) {
        var sx = PL + CW * ((t % 4) / 4), g = ctx.createLinearGradient(sx - 110, 0, sx, 0);
        g.addColorStop(0, 'rgba(63,219,230,0)'); g.addColorStop(1, 'rgba(63,219,230,.14)');
        ctx.fillStyle = g; ctx.fillRect(Math.max(PL, sx - 110), PT, Math.min(110, sx - PL), CH);
        ctx.strokeStyle = 'rgba(63,219,230,.55)'; ctx.lineWidth = 1.2; ctx.beginPath(); ctx.moveTo(sx, PT); ctx.lineTo(sx, PT + CH); ctx.stroke();
      }
      // lines (draw in over the first 1.6 s)
      var grow = calm ? 1 : Math.min(1, t / 1.6), cut = tmin + (tmax - tmin) * grow, pulse = calm ? 1 : 0.6 + 0.4 * Math.sin(t * 3.2);
      sites.forEach(function (s) {
        var pts = d.series[s].filter(function (p) { return p[0] >= tmin && p[0] <= cut; });
        if (!pts.length) return;
        ctx.beginPath();
        pts.forEach(function (p, i) { var px = X(p[0]), py = Y(p[1]); if (i) ctx.lineTo(px, py); else ctx.moveTo(px, py); });
        ctx.strokeStyle = C[s]; ctx.lineWidth = phone ? 2.2 : 2.8; ctx.lineJoin = 'round'; ctx.shadowColor = C[s]; ctx.shadowBlur = 12;
        ctx.stroke(); ctx.shadowBlur = 0;
        if (pts.length === 1) { ctx.fillStyle = C[s]; ctx.beginPath(); ctx.arc(X(pts[0][0]), Y(pts[0][1]), 3, 0, TAU); ctx.fill(); }
      });
      if (grow >= 1) {
        // pulsing end dots at today's prices
        sites.forEach(function (s) {
          var y = Y(d.prices[s]), x = PL + CW;
          ctx.fillStyle = C[s]; ctx.beginPath(); ctx.arc(x, y, 5, 0, TAU); ctx.fill();
          ctx.strokeStyle = C[s]; ctx.globalAlpha = 0.25 + 0.4 * pulse; ctx.lineWidth = 1.5; ctx.beginPath(); ctx.arc(x, y, 10, 0, TAU); ctx.stroke(); ctx.globalAlpha = 1;
        });
        // gap bracket: lowest vs highest price now
        var top = Y(d.high.price), bot = Y(d.low.price), bx = PL + CW + (phone ? 18 : 28);
        ctx.strokeStyle = '#ffb347'; ctx.lineWidth = 2.5; ctx.shadowColor = '#ffb347'; ctx.shadowBlur = 16 * pulse;
        ctx.beginPath(); ctx.moveTo(bx - 8, top); ctx.lineTo(bx, top); ctx.lineTo(bx, bot); ctx.lineTo(bx - 8, bot); ctx.stroke(); ctx.shadowBlur = 0;
        ctx.setLineDash([3, 4]); ctx.strokeStyle = 'rgba(255,179,71,.45)'; ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(PL + CW + 7, top); ctx.lineTo(bx - 9, top); ctx.moveTo(PL + CW + 7, bot); ctx.lineTo(bx - 9, bot); ctx.stroke(); ctx.setLineDash([]);
        var my = Math.min(Math.max((top + bot) / 2, PT + 22), PT + CH - 22);
        ctx.textAlign = 'left'; ctx.fillStyle = '#ffb347'; ctx.globalAlpha = 0.8 + 0.2 * pulse;
        ctx.font = '800 ' + (phone ? 15 : 20) + 'px "JetBrains Mono",monospace'; ctx.fillText(c1(d.net) + '¢', bx + 9, my - 9); ctx.globalAlpha = 1;
        ctx.font = '700 ' + (phone ? 8 : 10) + 'px "JetBrains Mono",monospace'; ctx.fillStyle = 'rgba(232,238,245,.85)';
        ctx.fillText('AFTER FEES', bx + 9, my + 9);
        if (!phone) { ctx.fillStyle = 'rgba(143,163,184,.8)'; ctx.fillText(c1(d.raw) + '¢ apart', bx + 9, my + 23); }
      }
      // radar
      if (!phone) {
        var rx = W - 44, ry = PT + 30, rr = 22, a = TAU * (t % 2) / 2 - Math.PI / 2;
        ctx.strokeStyle = 'rgba(63,219,230,.45)'; ctx.lineWidth = 1.2;
        [rr, rr * 0.55].forEach(function (r) { ctx.beginPath(); ctx.arc(rx, ry, r, 0, TAU); ctx.stroke(); });
        ctx.beginPath(); ctx.moveTo(rx - rr, ry); ctx.lineTo(rx + rr, ry); ctx.moveTo(rx, ry - rr); ctx.lineTo(rx, ry + rr); ctx.stroke();
        ctx.strokeStyle = '#3fdbe6'; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(rx, ry);
        ctx.lineTo(rx + rr * Math.cos(calm ? -0.8 : a), ry + rr * Math.sin(calm ? -0.8 : a)); ctx.stroke();
        sites.forEach(function (s, i) { ctx.fillStyle = C[s]; ctx.beginPath(); ctx.arc(rx + [0.5, -0.35, 0.15][i] * rr, ry + [-0.35, 0.45, 0.3][i] * rr, 2.5, 0, TAU); ctx.fill(); });
      }
      if (!calm || grow < 1) requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  }
})();
