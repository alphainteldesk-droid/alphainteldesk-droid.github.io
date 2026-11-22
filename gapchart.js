/* Nov 21 (James): Live Gap Chart. Real price history for every gap (gap_chart.json, written by gap_chart.py).
   Mounts:  #gapchart      big chart for today's biggest gap (top of the Gap Scanner page)
            #board .gp      a compact chart inside every gap row (Gap Scanner page)
            #hx-chart       mini chart in the homepage first-screen "Today's biggest gap" card
   Same look as the X card: glowing lines, scan beam, radar, pulsing end dots, amber gap bracket. */
(function () {
  var C = { polymarket: '#5b8cff', kalshi: '#2fe0a0', alpha: '#ffb347' };
  var N = { polymarket: 'POLYMARKET', kalshi: 'KALSHI', alpha: 'ALPHA ARCADE' };
  var TAU = Math.PI * 2, MONO = '"JetBrains Mono",monospace';
  var calm = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
  var css = document.createElement('style');
  css.textContent =
    '.gc{position:relative;margin:18px 0 20px;border:1px solid rgba(63,219,230,.35);border-radius:10px;overflow:hidden;' +
    'background:radial-gradient(ellipse at 85% 0%,rgba(63,219,230,.12),transparent 60%),radial-gradient(ellipse at 0% 100%,rgba(255,179,71,.08),transparent 60%),' +
    'linear-gradient(rgba(63,219,230,.04) 1px,transparent 1px) 0 0/28px 28px,linear-gradient(90deg,rgba(63,219,230,.04) 1px,transparent 1px) 0 0/28px 28px,#070f19;' +
    'box-shadow:0 0 40px rgba(63,219,230,.1),inset 0 0 50px rgba(0,0,0,.45)}' +
    '.gc-h{display:flex;flex-wrap:wrap;align-items:flex-start;justify-content:space-between;gap:10px 20px;padding:16px 18px 4px}' +
    '.gc-h>div:first-child{flex:1 1 320px;min-width:0}' +
    '.gc-eb{display:flex;align-items:center;gap:8px;font:800 .78rem ' + MONO + ';letter-spacing:.2em;color:#3fdbe6}' +
    '.gc-eb i{width:9px;height:9px;border-radius:50%;background:#3fdbe6;box-shadow:0 0 8px #3fdbe6;animation:gcp 1.4s infinite}' +
    '@keyframes gcp{0%{box-shadow:0 0 0 0 rgba(63,219,230,.6)}100%{box-shadow:0 0 0 9px rgba(63,219,230,0)}}' +
    '.gc-t{margin:6px 0 0;font-size:1.15rem;font-weight:800;line-height:1.25;color:#e8eef5}.gc-t span{color:#8fa3b8;font-weight:600}' +
    '.gc-n{text-align:right;flex:none;margin-left:auto}' +
    '.gc-n b{display:block;font:800 2.1rem/1 ' + MONO + ';color:#ffb347;text-shadow:0 0 18px rgba(255,179,71,.55)}' +
    '.gc-n small{font:700 .66rem ' + MONO + ';letter-spacing:.14em;color:#c9d3dc}.gc-n .gr{margin-left:6px}' +
    '.gc canvas,.gc-row canvas,.hx-chart canvas{display:block;width:100%}' +
    '.gc-f{display:flex;flex-wrap:wrap;align-items:center;gap:8px 18px;padding:2px 18px 14px;font:700 .74rem ' + MONO + ';color:#a9bccf}' +
    '.gc-f .k{display:inline-flex;align-items:center;gap:6px;letter-spacing:.06em}.gc-f .k i{width:14px;height:4px;border-radius:2px}.gc-f .k b{color:#e8eef5}' +
    '.gc-f a{margin-left:auto;color:#3fdbe6;letter-spacing:.06em}' +
    '.gc-nt{padding:0 18px 14px;margin-top:-6px;color:#6f8399;font-size:.78rem}' +
    '.gc-row{margin:10px 0 4px;border:1px solid rgba(63,219,230,.2);border-radius:8px;background:linear-gradient(rgba(63,219,230,.035) 1px,transparent 1px) 0 0/24px 24px,rgba(5,12,20,.55);overflow:hidden}' +
    '.gc-row p{margin:0;padding:0 10px 6px;font:700 .64rem ' + MONO + ';letter-spacing:.08em;color:#6f8399}' +
    '.hx-chart{display:block !important;flex:1 1 0;min-width:0;align-self:stretch;border:1px solid rgba(63,219,230,.25);border-radius:6px;background:rgba(0,0,0,.3);overflow:hidden}' +
    '.hx-chart:empty{display:none !important}' +
    '@media(max-width:640px){.gc-h{padding:12px 12px 2px}.gc-t{font-size:1rem}.gc-n b{font-size:1.6rem}.gc-f{padding:2px 12px 12px}.gc-f a{margin-left:0}.gc-nt{padding:0 12px 12px}}';
  document.head.appendChild(css);

  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function gkey(g) { var t = g.title + '|' + g.outcome, h = 5381; for (var k = 0; k < t.length; k++) h = ((h * 33) ^ t.charCodeAt(k)) >>> 0; return h.toString(36); }
  function c1(v) { return (Math.round(v * 10) / 10).toFixed(1); }
  function sitesOf(g) { return ['polymarket', 'kalshi', 'alpha'].filter(function (s) { return g.series && g.series[s] && g.series[s].length && g.prices[s] != null; }); }

  /* ---------- one chart = one canvas; a single animation loop draws the charts that are on screen ---------- */
  var charts = [];
  function Chart(cv, g, days, mode) {
    var me = this; this.cv = cv; this.g = g; this.mode = mode; this.sites = sitesOf(g); this.seen = false; this.t0 = 0;
    this.ctx = cv.getContext('2d'); this.days = days || 7;
    var all = [], tmax = -Infinity, tmin = Infinity;
    this.sites.forEach(function (s) { g.series[s].forEach(function (p) { all.push(p[1]); tmax = Math.max(tmax, p[0]); tmin = Math.min(tmin, p[0]); }); });
    this.tmax = tmax; this.tmin = Math.max(tmin, tmax - this.days * 86400);
    var lo = Math.min.apply(null, all), hi = Math.max.apply(null, all), pad = Math.max(1.5, (hi - lo) * 0.15);
    this.lo = Math.max(0, lo - pad); this.hi = Math.min(100, hi + pad);
    var r = this.hi - this.lo; this.step = r > 40 ? 10 : r > 16 ? 5 : r > 6 ? 2 : 1;
    this.size();
    if ('IntersectionObserver' in window) {
      new IntersectionObserver(function (en) { en.forEach(function (e) { me.vis = e.isIntersecting; if (e.isIntersecting && !me.seen) { me.seen = true; me.t0 = performance.now(); } kick(); }); }).observe(cv);
    } else { this.vis = this.seen = true; this.t0 = performance.now(); }
    charts.push(this); kick();
  }
  Chart.prototype.size = function () {
    var dpr = window.devicePixelRatio || 1, W = this.cv.clientWidth || this.cv.parentNode.clientWidth;
    this.W = W; this.H = this.mode === 'big' ? (W < 600 ? 250 : 330) : this.mode === 'row' ? (W < 500 ? 130 : 150) : 80;
    this.cv.style.height = this.H + 'px'; this.cv.width = W * dpr; this.cv.height = this.H * dpr; this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  };
  Chart.prototype.draw = function (now) {
    var ctx = this.ctx, g = this.g, W = this.W, H = this.H, m = this.mode, big = m === 'big', mini = m === 'mini', small = W < 600;
    var t = (now - this.t0) / 1000, me = this;
    var PL = mini ? 6 : small ? 36 : 50, PR = mini ? 22 : small ? 88 : big ? 150 : 120, PT = mini ? 8 : 14, PB = mini ? 20 : 26;
    var CW = W - PL - PR, CH = H - PT - PB;
    var X = function (ts) { return PL + CW * (ts - me.tmin) / Math.max(1, me.tmax - me.tmin); };
    var Y = function (v) { return PT + CH * (1 - (v - me.lo) / (me.hi - me.lo)); };
    ctx.clearRect(0, 0, W, H);
    ctx.font = '600 ' + (big ? 11 : 10) + 'px ' + MONO; ctx.textBaseline = 'middle'; ctx.textAlign = 'left';
    for (var v = Math.ceil(this.lo / this.step) * this.step; v <= this.hi; v += this.step) {
      var y = Y(v); ctx.strokeStyle = 'rgba(63,219,230,.08)'; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(PL, y); ctx.lineTo(PL + CW, y); ctx.stroke();
      if (!mini) { ctx.fillStyle = 'rgba(143,163,184,.75)'; ctx.fillText(v + '¢', 4, y); }
    }
    {                                                                   // day labels (mini: short names, Nov 21 James)
      ctx.textAlign = 'center'; if (mini) ctx.font = '600 9px ' + MONO;
      for (var day = new Date(this.tmin * 1000); day.getTime() / 1000 <= this.tmax; day.setDate(day.getDate() + 1)) {
        day.setHours(0, 0, 0, 0); var ts = day.getTime() / 1000; if (ts < this.tmin) continue;
        var x = X(ts); ctx.strokeStyle = 'rgba(63,219,230,.06)'; ctx.beginPath(); ctx.moveTo(x, PT); ctx.lineTo(x, PT + CH); ctx.stroke();
        ctx.fillStyle = 'rgba(143,163,184,.7)';
        ctx.fillText(mini ? day.toLocaleDateString('en-US', { weekday: W < 220 ? 'narrow' : 'short' })
          : small ? day.toLocaleDateString('en-US', { weekday: 'narrow' }) : day.toLocaleDateString('en-US', { weekday: 'short' }) + ' ' + day.getDate(), x, H - (mini ? 8 : 11));
      }
    }
    if (!calm && m !== 'row') {                                       // scan beam
      var sx = PL + CW * ((t % 4) / 4), bw = mini ? 60 : 110, gr = ctx.createLinearGradient(sx - bw, 0, sx, 0);
      gr.addColorStop(0, 'rgba(63,219,230,0)'); gr.addColorStop(1, 'rgba(63,219,230,.14)');
      ctx.fillStyle = gr; ctx.fillRect(Math.max(PL, sx - bw), PT, Math.min(bw, sx - PL), CH);
      ctx.strokeStyle = 'rgba(63,219,230,.55)'; ctx.lineWidth = 1.2; ctx.beginPath(); ctx.moveTo(sx, PT); ctx.lineTo(sx, PT + CH); ctx.stroke();
    }
    var grow = calm ? 1 : Math.min(1, t / (big ? 1.6 : 1.1)), cut = this.tmin + (this.tmax - this.tmin) * grow;
    var pulse = calm ? 1 : 0.6 + 0.4 * Math.sin(t * 3.2);
    this.sites.forEach(function (s) {
      var pts = g.series[s].filter(function (p) { return p[0] >= me.tmin && p[0] <= cut; });
      if (!pts.length) return;
      ctx.beginPath();
      pts.forEach(function (p, i) { var px = X(p[0]), py = Y(p[1]); if (i) ctx.lineTo(px, py); else ctx.moveTo(px, py); });
      ctx.strokeStyle = C[s]; ctx.lineWidth = big ? (small ? 2.2 : 2.8) : 2; ctx.lineJoin = 'round'; ctx.shadowColor = C[s]; ctx.shadowBlur = big ? 12 : 8;
      ctx.stroke(); ctx.shadowBlur = 0;
    });
    if (grow >= 1) {
      this.sites.forEach(function (s) {                                 // pulsing end dots at today's prices
        var y = Y(g.prices[s]), x = PL + CW;
        ctx.fillStyle = C[s]; ctx.beginPath(); ctx.arc(x, y, big ? 5 : 4, 0, TAU); ctx.fill();
        ctx.strokeStyle = C[s]; ctx.globalAlpha = 0.25 + 0.4 * pulse; ctx.lineWidth = 1.5; ctx.beginPath(); ctx.arc(x, y, big ? 10 : 8, 0, TAU); ctx.stroke(); ctx.globalAlpha = 1;
      });
      var top = Y(g.high.price), bot = Y(g.low.price), bx = PL + CW + (big && !small ? 28 : 16);   // the gap bracket
      ctx.strokeStyle = '#ffb347'; ctx.lineWidth = big ? 2.5 : 2; ctx.shadowColor = '#ffb347'; ctx.shadowBlur = 16 * pulse;
      ctx.beginPath(); ctx.moveTo(bx - 7, top); ctx.lineTo(bx, top); ctx.lineTo(bx, bot); ctx.lineTo(bx - 7, bot); ctx.stroke(); ctx.shadowBlur = 0;
      ctx.setLineDash([3, 4]); ctx.strokeStyle = 'rgba(255,179,71,.45)'; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(PL + CW + 6, top); ctx.lineTo(bx - 8, top); ctx.moveTo(PL + CW + 6, bot); ctx.lineTo(bx - 8, bot); ctx.stroke(); ctx.setLineDash([]);
      if (mini) { this.done = calm; return; }                      // mini: the big number sits right next to it
      var my = Math.min(Math.max((top + bot) / 2, PT + 16), PT + CH - 16);
      ctx.textAlign = 'left'; ctx.fillStyle = '#ffb347'; ctx.globalAlpha = 0.8 + 0.2 * pulse;
      ctx.font = '800 ' + (big ? (small ? 15 : 20) : 14) + 'px ' + MONO; ctx.fillText(c1(g.net) + '¢', bx + 7, my - 8); ctx.globalAlpha = 1;
      ctx.font = '700 ' + (big && !small ? 10 : 8) + 'px ' + MONO; ctx.fillStyle = 'rgba(232,238,245,.85)'; ctx.fillText('AFTER FEES', bx + 7, my + 7);
      if (big && !small) { ctx.fillStyle = 'rgba(143,163,184,.8)'; ctx.fillText(c1(g.raw) + '¢ apart', bx + 7, my + 21); }
    }
    if (big && !small) {                                                // radar
      var rx = W - 44, ry = PT + 30, rr = 22, a = TAU * (t % 2) / 2 - Math.PI / 2;
      ctx.strokeStyle = 'rgba(63,219,230,.45)'; ctx.lineWidth = 1.2;
      [rr, rr * 0.55].forEach(function (r) { ctx.beginPath(); ctx.arc(rx, ry, r, 0, TAU); ctx.stroke(); });
      ctx.beginPath(); ctx.moveTo(rx - rr, ry); ctx.lineTo(rx + rr, ry); ctx.moveTo(rx, ry - rr); ctx.lineTo(rx, ry + rr); ctx.stroke();
      ctx.strokeStyle = '#3fdbe6'; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(rx, ry);
      ctx.lineTo(rx + rr * Math.cos(calm ? -0.8 : a), ry + rr * Math.sin(calm ? -0.8 : a)); ctx.stroke();
      this.sites.forEach(function (s, i) { ctx.fillStyle = C[s]; ctx.beginPath(); ctx.arc(rx + [0.5, -0.35, 0.15][i] * rr, ry + [-0.35, 0.45, 0.3][i] * rr, 2.5, 0, TAU); ctx.fill(); });
    }
    this.done = calm && grow >= 1;
  };
  var running = false;
  function kick() { if (!running) { running = true; requestAnimationFrame(loop); } }
  function loop(now) {
    var any = false;
    charts = charts.filter(function (c) { return document.body.contains(c.cv); });
    charts.forEach(function (c) { if (c.seen && c.vis && !c.done) { c.draw(now); any = true; } });
    if (any) requestAnimationFrame(loop); else running = false;
  }
  window.addEventListener('resize', function () { charts.forEach(function (c) { c.size(); c.done = false; }); kick(); });

  /* ---------- mounting ---------- */
  fetch('/gap_chart.json?v=' + Date.now()).then(function (r) { return r.json(); }).then(function (d) {
    var list = (d.gaps || []).filter(function (g) { return sitesOf(g).length >= 2; });
    if (!list.length) return;
    var byKey = {}; list.forEach(function (g) { byKey[gkey(g)] = g; });
    var top = d.gaps[0] && byKey[gkey(d.gaps[0])];

    var box = document.getElementById('gapchart');                     // Gap Scanner page: big chart
    if (box && top) {
      var gr = top.grade ? '<i class="gr gr-' + esc(top.grade) + '">' + esc(top.grade) + '</i>' : '';
      box.innerHTML = '<section class="gc" aria-label="Price history for today’s biggest gap">' +
        '<div class="gc-h"><div><div class="gc-eb"><i></i>TODAY’S BIGGEST GAP · LIVE</div>' +
        '<p class="gc-t">' + esc(top.title) + ' <span>· ' + esc(top.outcome) + '</span></p></div>' +
        '<div class="gc-n"><b>' + c1(top.net) + '¢</b><small>GAP AFTER FEES' + (gr ? ' · GRADED</small>' + gr : '</small>') + '</div></div>' +
        '<canvas aria-hidden="true"></canvas>' +
        '<div class="gc-f">' + sitesOf(top).map(function (s) {
          return '<span class="k"><i style="background:' + C[s] + ';box-shadow:0 0 6px ' + C[s] + '"></i>' + N[s] + ' <b>' + c1(top.prices[s]) + '¢</b></span>';
        }).join('') + '<a href="#g-' + gkey(top) + '">See this gap ↓</a></div>' +
        '<p class="gc-nt">Yes price over the last ' + (d.days || 7) + ' days. Lines end at the Gap Scanner’s latest check' +
        (top.series.alpha ? '. Alpha Arcade has no public price history, so its line is our own checks and starts when we began recording it' : '') +
        '. Not financial advice.</p></section>';
      new Chart(box.querySelector('canvas'), top, d.days, 'big');
    }

    var hx = document.getElementById('hx-chart');                      // homepage first screen: mini chart
    if (hx && top) {
      hx.innerHTML = '<canvas aria-hidden="true"></canvas>';
      new Chart(hx.querySelector('canvas'), top, d.days, 'mini');
    }

    var board = document.getElementById('board');                     // Gap Scanner page: one chart per gap row
    if (board) {
      var addRows = function () {
        board.querySelectorAll('.gp[id^="g-"]').forEach(function (row) {
          if (row.querySelector('.gc-row')) return;
          var g = byKey[row.id.slice(2)], px = row.querySelector('.gp-px');
          if (!g || !px) return;
          var w = document.createElement('div'); w.className = 'gc-row';
          w.innerHTML = '<canvas aria-hidden="true"></canvas><p>YES PRICE, LAST ' + (d.days || 7) + ' DAYS' +
            (g.series.alpha ? ' · ALPHA LINE = OUR OWN CHECKS' : '') + '</p>';
          px.parentNode.insertBefore(w, px.nextSibling);
          new Chart(w.querySelector('canvas'), g, d.days, 'row');
        });
      };
      var jump = function () {                                         // a #g= link (homepage card, shared links) lands on its row
        var m = /#g=([0-9a-z]+)/.exec(location.hash), el = m && document.getElementById('g-' + m[1]);
        if (el) el.scrollIntoView({ block: 'center' });
      };
      addRows(); setTimeout(jump, 200);
      new MutationObserver(function () { addRows(); setTimeout(jump, 200); }).observe(board, { childList: true });
    }
  }).catch(function () {});
})();
