/* Market of the Week renderer (Nov 19, 2026). Used by market-of-the-week.html (tabs: This Week / Previous / Resolved)
   and by every permanent pick page in /motw/ (<body data-slug="...">). Data: /motw.json, written by motw.py. */
(function () {
  function esc(t) { return String(t == null ? '' : t).replace(/[&<>"']/g, function (c) { return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); }
  var SITES = ['alpha', 'polymarket', 'kalshi'], NAME = { alpha: 'ALPHA ARCADE', polymarket: 'POLYMARKET', kalshi: 'KALSHI' };
  var COL = { alpha: '#3fdbe6', polymarket: '#8fa8ff', kalshi: '#3ddc84' }, LONG = { alpha: 'Alpha Arcade', polymarket: 'Polymarket', kalshi: 'Kalshi' };
  var MAIN = '/market-of-the-week.html';
  function c(p) { return p == null ? '—' : (Math.round(p * 10) / 10) + '¢'; }
  function day(t, y) { return new Date(t * 1000).toLocaleDateString('en-US', y ? { month: 'short', day: 'numeric', year: 'numeric' } : { month: 'short', day: 'numeric' }); }
  function money(v) { return v >= 1e6 ? '$' + (v / 1e6).toFixed(1) + 'M' : v >= 1e3 ? '$' + (v / 1e3).toFixed(1) + 'K' : '$' + Math.round(v); }
  function closeT(e) { return new Date(e.close).getTime() / 1000 - 6 * 3600; }   /* Dec 31 11:59 PM ET is stamped Jan 1 UTC */
  function link(e) { return e.slug ? '/motw/' + e.slug + '.html' : MAIN; }
  function first(ps) { return SITES.filter(function (s) { return ps && ps[s] != null; })[0]; }
  function srcs(list) {
    return '<span class="srcs">' + (list || []).map(function (u, i) {
      var h = u.split('/')[2].replace('www.', ''); return '<a href="' + esc(u) + '" rel="nofollow noopener" target="_blank" title="' + esc(h) + '">[' + (i + 1) + ']</a>';
    }).join('') + '</span>';
  }
  var VERIFY = '<div class="verify"><b>Always verify the rules yourself.</b><p>We read every price twice and every point on this page has at least two independent sources, ' +
    'but we can still be wrong, and sites can change their rules. Read the market\'s full rules on the site before you trade. Nothing here is a tip to buy or sell.</p></div>' +
    '<p class="disc">Not financial advice. Both Sides is a summary of public reporting, not a prediction. Prices are midpoints and don\'t include spreads or fees. Referral links may earn us a commission.</p>';

  function chart(e) {
    var s = e.series || [];
    if (s.length < 2) return '<p class="cnote">The chart starts building from the moment of the pick (one point an hour). Check back in a few hours.</p>';
    var W = 1000, H = 230, L = 50, R = 20, T = 12, B = 30, t0 = s[0][0], t1 = s[s.length - 1][0], all = [];
    s.forEach(function (r) { r.slice(1).forEach(function (p) { if (p != null) all.push(p); }); });
    var lo = Math.max(0, Math.floor((Math.min.apply(null, all) - 3) / 5) * 5), hi = Math.min(100, Math.ceil((Math.max.apply(null, all) + 3) / 5) * 5);
    var X = function (t) { return L + (t - t0) / Math.max(1, t1 - t0) * (W - L - R); }, Y = function (p) { return T + (hi - p) / (hi - lo) * (H - T - B); };
    var g = '', gs = hi - lo > 40 ? 10 : 5;
    for (var v = lo; v <= hi; v += gs) g += '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + Y(v) + '" y2="' + Y(v) + '" class="g"/><text x="' + (L - 8) + '" y="' + (Y(v) + 4) + '" class="ax">' + v + '¢</text>';
    var step = Math.max(21600, Math.ceil((t1 - t0) / 5 / 86400) * 86400);
    for (var t = Math.ceil(t0 / step) * step; t < t1 - step / 3; t += step) g += '<text x="' + X(t) + '" y="' + (H - 8) + '" class="ax mid">' +
      new Date(t * 1000).toLocaleString('en-US', step < 86400 ? { month: 'short', day: 'numeric', hour: 'numeric' } : { month: 'short', day: 'numeric' }) + '</text>';
    var lines = '', leg = [];
    SITES.forEach(function (site, i) {
      var d = '', n = 0;
      s.forEach(function (r) { var p = r[i + 1]; if (p == null) return; d += (n++ ? 'L' : 'M') + X(r[0]).toFixed(1) + ',' + Y(p).toFixed(1); });
      if (n > 1) { lines += '<path d="' + d + '" fill="none" stroke="' + COL[site] + '" stroke-width="2.5"/>'; leg.push('<span><b style="color:' + COL[site] + '">━</b> ' + LONG[site] + '</span>'); }
    });
    return '<div class="legend">' + leg.join('') + '<span>Picked ' + day(e.picked) + ' · one point an hour until it settles</span></div>' +
      '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="YES price on each site since the pick">' + g + lines + '</svg>';
  }

  /* status of a pick: this week / still open / resolved */
  function status(e, cur) { return e.result ? 'resolved' : e === cur ? 'current' : 'open'; }

  function full(e, cur) {
    var st = e.story || {}, live = e === cur, ps = live ? (e.confirmed || e.prices || {}) : (e.now || e.confirmed || {});
    var have = SITES.filter(function (s) { return ps[s] != null; });
    var vals = have.map(function (s) { return ps[s]; }), mid = vals.length ? vals.reduce(function (a, b) { return a + b; }, 0) / vals.length : 50;
    var gap = vals.length ? Math.max.apply(null, vals) - Math.min.apply(null, vals) : 0, close = closeT(e);
    var left = Math.max(0, Math.round((close - Date.now() / 1000) / 86400)), sta = status(e, cur);
    var board = SITES.map(function (s) {
      if (ps[s] == null) return '<div class="px off"><span class="v">' + NAME[s] + '</span><b>Not listed</b><span>No matching market</span></div>';
      return '<div class="px"><span class="v">' + NAME[s] + '</span><b>' + c(ps[s]) + '</b><span>YES · <a href="' + esc(e.urls[s]) + '" rel="nofollow noopener" target="_blank">open on ' + LONG[s] + '</a></span></div>';
    }).join('') + (sta === 'resolved'
      ? '<div class="px sum"><span class="v">RESULT</span><b>' + esc(e.result) + '</b><div>Settled after closing <em>' + day(close, 1) + '</em><br>Picked at <em>' + c((e.picked_prices || {})[first(e.picked_prices)]) + '</em> YES</div></div>'
      : '<div class="px sum"><span class="v">THE MARKET SAYS</span><b>~' + Math.round(mid) + '% YES</b><div>Price gap: <em>' + gap.toFixed(1) + '¢</em>' +
        (gap < 3 ? ', too small to beat fees' : '') + '<br>Closes <em>' + day(close) + '</em> · ' + left + ' days left<br><span class="chk">checked twice · ' +
        (e.checked ? new Date(e.checked * 1000).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' }) : 'at pick') + '</span></div></div>');
    var side = function (k, label, p) {
      var pts = st[k] || [];
      if (!pts.length) return '<div class="side ' + k[0] + '"><h3>The case for <span>' + label + '</span> <small>~' + Math.round(p) + '¢</small></h3><p class="sum">Write-up coming. Every point needs two independent sources before it goes up.</p></div>';
      return '<div class="side ' + k[0] + '"><h3>The case for <span>' + label + '</span> <small>~' + Math.round(p) + '¢</small></h3><ul>' +
        pts.map(function (x) { return '<li>' + esc(x.t) + srcs(x.sources) + '</li>'; }).join('') + '</ul>' + (st[k + '_note'] ? '<p class="sum">' + esc(st[k + '_note']) + '</p>' : '') + '</div>';
    };
    var clock = (st.clock || []).slice(), html = '', order = { done: 0, next: 1, end: 2, after: 3 };
    clock.push({ d: day(close), t: 'This market closes', s: 'end' });
    clock.sort(function (a, b) { return order[a.s] - order[b.s]; });
    if (clock.length > 1) html = '<h2>The clock</h2><div class="panel"><div class="tl" style="grid-template-columns:repeat(' + clock.length + ',1fr)">' +
      clock.map(function (x) { return '<div class="' + x.s + '"><i></i><b>' + esc(x.d) + '</b><span>' + esc(x.t) + '</span></div>'; }).join('') + '</div></div>';
    var gd = { A: 'Grade A · same rules on each site', B: 'Grade B · checks passed, small differences' }[e.grade] || e.grade;
    var tag = { current: 'This week', open: 'Previous pick · still open', resolved: 'Resolved' }[sta];
    var out = '<span class="tag">Market of the Week · #' + (e.n || 1) + ' · picked ' + day(e.picked, 1) + ' · ' + tag + '</span>' + (sta !== 'resolved' ? '<span class="tag live"><i></i>Live prices</span>' : '') +
      '<h1>' + esc(e.title) + '</h1>' + (st.hook ? '<p class="why">' + esc(st.hook) + '</p>' : '') +
      '<div class="board">' + board + '</div>' +
      '<h2>Both sides' + (sta === 'current' ? '' : ' <small class="chk">(as written ' + esc(st.written || day(e.picked)) + ')</small>') + '</h2><div class="sides">' + side('yes', 'YES', mid) + side('no', 'NO', 100 - mid) + '</div>' + html +
      '<h2>Price since it was picked</h2><div class="panel">' + chart(e) + '</div>' +
      '<h2>What has to happen to get paid</h2><div class="two"><div class="panel pay">' +
      (st.pay_yes ? '<p><b>' + esc(st.pay_yes) + '</b></p><p>' + esc(st.pay_no) + '</p><p class="src">' + esc(st.pay_src) + ' Rules: ' + esc(gd) + '.</p>' +
        (st.watch ? '<p class="warn">' + esc(st.watch) + '</p>' : '') : '<p>Read the full rules on each site before you trade.</p><p class="src">Rules: ' + esc(gd) + '.</p>') +
      '</div><div class="panel"><ul class="ok">' +
      '<li><span>On ' + have.length + ' sites' + (ps.alpha != null ? ', Alpha included' : '') + '</span><span>' + have.map(function (s) { return LONG[s].split(' ')[0]; }).join(' · ') + '</span></li>' +
      '<li><span>A real debate (30–70¢) when picked</span><span>' + c((e.picked_prices || {})[first(e.picked_prices)]) + '</span></li>' +
      '<li><span>Settles in 2–8 weeks</span><span>' + (e.days || left) + ' days</span></li>' +
      '<li><span>Busy market</span><span>' + money(e.vol24 || 0) + ' / 24h</span></li>' +
      '<li><span>Clear rules</span><span>Grade ' + esc(e.grade) + '</span></li>' +
      '<li><span>Prices checked twice</span><span>within 3¢</span></li></ul>' +
      '<p class="cnote">Picked automatically by formula. No sports, no daily price markets, no repeats within 8 weeks.</p></div></div>' +
      '<div class="cta">' + have.map(function (s, i) { return '<a class="btn' + (i ? '' : ' solid') + '" href="' + esc(e.urls[s]) + '" rel="nofollow noopener" target="_blank">Open on ' + LONG[s] + '</a>'; }).join('') +
      '<a class="btn" href="#" data-share="' + esc(link(e)) + '" data-title="' + esc(e.title) + '">Share this pick</a><a class="btn" href="https://t.me/alphainteldesk">Get it on Telegram</a></div>';
    return out;
  }

  function moveTxt(e) {
    var pp = e.picked_prices || {}, nw = e.now || {}, f = first(pp);
    if (!f || nw[f] == null) return { txt: c(pp[f]), cls: '' };
    var d = Math.round((nw[f] - pp[f]) * 10) / 10;
    return { txt: c(pp[f]) + ' → ' + c(nw[f]) + ' <b class="' + (d > 0 ? 'up' : d < 0 ? 'dn' : '') + '">' + (d > 0 ? '▲' : d < 0 ? '▼' : '') + Math.abs(d) + '¢</b>', cls: '' };
  }

  function cards(list, kind) {
    if (!list.length) return '<p class="wait">' + (kind === 'open'
      ? 'No previous picks yet. Each Monday the current pick moves here and keeps updating until it settles.'
      : 'No picks have settled yet. Once one does, its result shows here with the scoreboard.') + '</p>';
    return '<div class="pcards">' + list.map(function (e) {
      var pp = e.picked_prices || {}, f = first(pp), m = moveTxt(e), left = Math.max(0, Math.round((closeT(e) - Date.now() / 1000) / 86400));
      var fav = pp[f] >= 50 ? 'YES' : 'NO';
      var right = kind === 'resolved'
        ? '<span class="res ' + (e.result === 'YES' ? 'y' : 'n') + '">' + esc(e.result) + '</span><small>' + (e.result === fav ? 'market favourite won' : 'underdog won') + '</small>'
        : '<span class="mv">' + m.txt + '</span><small>' + (left ? left + ' days to settle' : 'closed · waiting for result') + '</small>';
      return '<a class="pcard" href="' + esc(link(e)) + '"><span class="pn">#' + (e.n || '') + '</span><span class="pt"><b>' + esc(e.title) + '</b><i>Picked ' + day(e.picked, 1) +
        ' at ' + c(pp[f]) + ' YES' + (f ? ' on ' + LONG[f] : '') + '</i></span><span class="pr">' + right + '</span></a>';
    }).join('') + '</div>';
  }

  function scoreboard(res) {
    if (!res.length) return '';
    var fw = res.filter(function (e) { var pp = e.picked_prices || {}, f = first(pp); return (pp[f] >= 50 ? 'YES' : 'NO') === e.result; }).length;
    var ys = res.filter(function (e) { return e.result === 'YES'; }).length;
    return '<div class="rec"><div><b>' + res.length + '</b><span>picks settled</span></div><div><b>' + fw + ' of ' + res.length + '</b><span>won by the side the market favoured when we picked it</span></div>' +
      '<div><b>' + ys + ' YES · ' + (res.length - ys) + ' NO</b><span>how they settled</span></div></div>' +
      '<p class="cnote">Our picks are close debates (30–70¢), not predictions, so we don\'t score them right or wrong. This shows how often the market\'s favourite at pick time won.</p>';
  }

  function wireShare(root) {
    root.querySelectorAll('[data-share]').forEach(function (b) {
      b.onclick = function (ev) {
        ev.preventDefault(); var u = 'https://alphainteldesk.com' + b.getAttribute('data-share'), t = 'Market of the Week: ' + b.getAttribute('data-title') + ' Both sides + live prices';
        if (navigator.share) navigator.share({ title: t, url: u }).catch(function () {});
        else if (navigator.clipboard) navigator.clipboard.writeText(t + ' ' + u).then(function () { b.textContent = 'Link copied'; });
      };
    });
  }

  var m = document.getElementById('mw'), slug = document.body.getAttribute('data-slug');
  fetch('/motw.json?' + Date.now()).then(function (r) { return r.json(); }).then(function (d) {
    var cur = d.current, arch = d.archive || [];
    if (slug) {                                            /* permanent pick page */
      var e = [cur].concat(arch).filter(function (x) { return x && x.slug === slug; })[0];
      if (!e) return;                                      /* keep the static copy already on the page */
      m.innerHTML = '<p class="crumb"><a href="' + MAIN + '">&larr; Market of the Week</a></p>' + full(e, cur) + VERIFY;
      wireShare(m); return;
    }
    if (!cur) {
      m.innerHTML = '<span class="tag">Market of the Week</span><h1>This week\'s pick is being verified</h1>' +
        '<p class="wait">Our formula has a candidate. It goes live once two separate price checks, at least 30 minutes apart, agree. Usually within the hour.</p>' + VERIFY;
      return;
    }
    var open = arch.filter(function (e) { return !e.result; }), res = arch.filter(function (e) { return e.result; });
    var tab = (location.hash || '').replace('#', '');
    if (['week', 'previous', 'resolved'].indexOf(tab) < 0) tab = 'week';
    var tabs = [['week', 'This Week'], ['previous', 'Previous Picks <i>' + open.length + '</i>'], ['resolved', 'Resolved <i>' + res.length + '</i>']];
    function draw() {
      var body = tab === 'week' ? full(cur, cur)
        : tab === 'previous' ? '<h1>Previous picks</h1><p class="why">Past Markets of the Week that haven\'t settled yet. Prices keep updating until each one settles.</p>' + cards(open, 'open')
        : '<h1>Resolved picks</h1><p class="why">Every pick that has settled, and how it ended.</p>' + scoreboard(res) + cards(res, 'resolved');
      m.innerHTML = '<div class="tabs">' + tabs.map(function (t) { return '<a href="#' + t[0] + '" class="' + (t[0] === tab ? 'on' : '') + '" data-t="' + t[0] + '">' + t[1] + '</a>'; }).join('') + '</div>' + body + VERIFY;
      m.querySelectorAll('[data-t]').forEach(function (a) { a.onclick = function (ev) { ev.preventDefault(); tab = a.getAttribute('data-t'); history.replaceState(null, '', '#' + tab); draw(); }; });
      wireShare(m);
    }
    window.addEventListener('hashchange', function () { var h = location.hash.replace('#', ''); if (['week', 'previous', 'resolved'].indexOf(h) >= 0 && h !== tab) { tab = h; draw(); } });
    document.title = 'Market of the Week: ' + cur.title + ' | Alpha Intel Desk';
    draw();
  }).catch(function () { if (!slug) m.innerHTML = '<h1>Market of the Week</h1><p class="wait">Couldn\'t load this week\'s pick. Try again in a minute.</p>'; });
})();
