# Alpha Intel Desk: daily 15-second YouTube Short (Nov 15, 2026). Run by .github/workflows/daily-short.yml, which posts
# the video to the Telegram channel and puts it + the YouTube text on the "daily-short" release (fixed download link).
# A phone-size screen recording of the real site: a mouse cursor moves to and clicks each link, captions say what
# you're looking at, with music + click sounds. Numbers come from today's gaps.json / expiry.json.
# Usage: python3 make_short.py <site folder> <output.mp4> [state.json]   (writes <output>.txt with title/description/tags)
import asyncio, json, math, os, shutil, subprocess, sys, time, wave
import numpy as np
from playwright.async_api import async_playwright

SITE, OUT = sys.argv[1], sys.argv[2]
FPS, W, H, DPR = 30, 432, 768, 2.5          # 432x768 CSS px x 2.5 = 1080x1920
FR = "/tmp/short_frames"
PORT = 8771

# ---------- today's picks (Nov 15 v3: different markets every day) ----------
import re
from datetime import datetime, timedelta, timezone
STATE = sys.argv[3] if len(sys.argv) > 3 else os.path.join(SITE, "short_state.json")
try:
    st = json.load(open(STATE))
except Exception:
    st = {"seen": {}}
now = time.time()
seen = {k for k, t in st["seen"].items() if now - t < 4 * 86400}        # don't repeat a market for 4 days
ET = timezone(timedelta(hours=-5))                                       # Eastern (standard time; fine for a weekday name)
PX = re.compile(r"bitcoin|ethereum|solana|dogecoin|\b(btc|eth|xrp|sol|doge|bnb)\b|\bprices?\b|\b(s&p|nasdaq|dow|nikkei|"
                r"ftse|wti|brent|gold|silver|treasury|yield)\b|\bclose (above|below|at)\b", re.I)
short = lambda x, n: x if len(x) <= n else x[:n - 1].rsplit(" ", 1)[0].rstrip(",:;") + "…"


def label(title, outcome, n=64):
    """'US announces end of Iranian blockade by December 31, 2026' - the outcome is never cut off"""
    t = re.sub(r"\s+", " ", title.replace("...", "").replace("?", "")).strip()
    if outcome in ("Yes", title) or not outcome:
        return short(t, n)
    if re.search(r"\b(by|before|in|on|after)$", t, re.I):
        return short(t, n - len(outcome) - 1) + " " + outcome
    return short(t, n - len(outcome) - 2) + ": " + outcome

gaps = json.load(open(os.path.join(SITE, "gaps.json")))["gaps"]
gk = lambda x: "gap|" + x["title"] + "|" + x["outcome"]
pool = [x for x in gaps if gk(x) not in seen] or gaps
g = sorted(pool, key=lambda x: (not x["all3"], -x["net"]))[0]           # all three sites first, then the biggest gap
G_TITLE = label(g["title"], g["outcome"])
GAP = ("Priced on all 3 sites · %.1f¢ gap after fees" if g["all3"] else "%.1f¢ gap after fees") % g["net"]

rows = [r for r in json.load(open(os.path.join(SITE, "expiry.json")))["rows"]
        if 0.5 <= r["days"] <= 7 and not PX.search(r["title"] + " " + (r.get("cat") or "")) and r["ask"] >= 80 and r["ret"] >= 5]   # James: 5%+ only
dk = lambda r: "dz|%s|%s|%s" % (r["title"], r["outcome"], r["side"])
pool = [r for r in rows if dk(r) not in seen] or rows
score = lambda r: min(r["ret"], 20) * min(1, math.log10(max(r["volume"], 10)) / 5.3)   # good return AND a busy market
d = max(pool, key=score)
D_DAY = datetime.strptime(d["close"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).astimezone(ET)
D_WHEN = "today" if D_DAY.date() == datetime.now(ET).date() else D_DAY.strftime("%A")
D_TITLE = label(d["title"], d["outcome"])
st["seen"][gk(g)] = st["seen"][dk(d)] = now
st["seen"] = {k: t for k, t in st["seen"].items() if now - t < 14 * 86400}

OVERLAY = """
(() => { if (document.getElementById('aid-cur')) return;
  document.documentElement.style.scrollBehavior = 'auto';
  const st = document.createElement('style'); st.textContent = `
  #aid-cur{position:fixed;left:0;top:0;width:30px;height:30px;z-index:99999;pointer-events:none;transform-origin:3px 3px;filter:drop-shadow(0 2px 4px rgba(0,0,0,.6))}
  #aid-rip{position:fixed;width:16px;height:16px;margin:-8px 0 0 -8px;border:3px solid #3fdbe6;border-radius:50%;z-index:99998;pointer-events:none;opacity:0}
  #aid-cap{position:fixed;left:6%;right:6%;top:67%;z-index:99997;text-align:center;pointer-events:none;transition:none}
  #aid-cap div{display:inline-block;background:rgba(6,11,18,.88);border:1px solid #1f3044;border-radius:14px;padding:12px 16px;
     font:700 23px/1.25 "Space Grotesk",sans-serif;color:#fff;box-shadow:0 8px 30px rgba(0,0,0,.5)}
  #aid-cap b{color:#ffb347} #aid-cap small{display:block;margin-top:6px;font:700 15px "JetBrains Mono",monospace;color:#3fdbe6}
  .aid-hi{outline:3px solid #3fdbe6 !important;outline-offset:3px;border-radius:8px}`;
  document.head.appendChild(st);
  const c = document.createElement('div'); c.id = 'aid-cur';
  c.innerHTML = '<svg viewBox="0 0 24 24" width="30" height="30"><path d="M3 2l15 11-6.5 1.2L15 21l-3 1.4-3.3-6.8L3 20z" fill="#fff" stroke="#000" stroke-width="1.4" stroke-linejoin="round"/></svg>';
  const r = document.createElement('div'); r.id = 'aid-rip';
  const cap = document.createElement('div'); cap.id = 'aid-cap';
  document.body.append(c, r, cap);
})()"""

SET = """([x, y, press, rip, rx, ry, cap, capA, sy, hi]) => {
  window.scrollTo(0, sy);
  const c = document.getElementById('aid-cur');
  c.style.transform = `translate(${x}px,${y}px) scale(${press})`; c.style.display = x < 0 ? 'none' : 'block';
  const r = document.getElementById('aid-rip');
  r.style.left = rx + 'px'; r.style.top = ry + 'px'; r.style.opacity = rip > 0 ? 1 - rip : 0; r.style.transform = `scale(${1 + rip * 4})`;
  const k = document.getElementById('aid-cap'); k.innerHTML = cap ? '<div>' + cap + '</div>' : ''; k.style.opacity = capA;
  k.style.transform = `translateY(${(1 - capA) * 14}px)`;
  document.querySelectorAll('.aid-hi').forEach(e => e.classList.remove('aid-hi'));
  if (hi) { const e = document.querySelector(hi); if (e) e.classList.add('aid-hi'); }
}"""

ease = lambda t: 0.5 - 0.5 * math.cos(math.pi * max(0, min(1, t)))


def lerp(a, b, t):
    return a + (b - a) * ease(t)


async def rect(pg, sel):
    return await pg.evaluate("s=>{const e=document.querySelector(s);if(!e)return null;const b=e.getBoundingClientRect();"
                             "return [b.x+b.width/2,b.y+b.height/2,b.y+window.scrollY,b.height]}", sel)


async def main():
    shutil.rmtree(FR, ignore_errors=True); os.makedirs(FR)
    srv = subprocess.Popen(["python3", "-m", "http.server", str(PORT)], cwd=SITE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)
    n = [0]
    clicks, swooshes = [], []
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=shutil.which("google-chrome") or "/usr/bin/google-chrome")
        ctx = await b.new_context(viewport={"width": W, "height": H}, device_scale_factor=DPR)
        pg = await ctx.new_page()

        async def go(path):
            await pg.goto("http://localhost:%d/%s" % (PORT, path), wait_until="domcontentloaded")
            await pg.wait_for_timeout(2200)
            await pg.evaluate(OVERLAY)

        async def shoot(secs, fn):
            """fn(t 0..1, s seconds) -> args for SET"""
            k = int(round(secs * FPS))
            for i in range(k):
                await pg.evaluate(SET, fn(i / max(1, k - 1), i / FPS))
                await pg.screenshot(path="%s/%04d.jpg" % (FR, n[0]), type="jpeg", quality=90)
                n[0] += 1

        # ---- 1. homepage: hook, then click Gap Scanner (0 - 3.2 s)
        await go("index.html")
        gs = await rect(pg, 'nav a[href="/gap-scanner.html"]')
        cap1 = "Same question.<br><b>%.1f¢ apart</b> after fees." % g["net"]
        def s1(t, s):
            x, y = lerp(300, gs[0], (s - 0.8) / 1.5), lerp(560, gs[1], (s - 0.8) / 1.5)
            pr = 0.85 if 2.55 <= s < 2.75 else 1
            rp = (s - 2.6) / 0.5 if 2.6 <= s < 3.1 else 0
            return [x, y, pr, rp, gs[0], gs[1], cap1, min(1, s / 0.3), 0, None]
        clicks.append(n[0] / FPS + 2.6)
        await shoot(3.2, s1)

        # ---- 2. Gap Scanner: scroll to the board, hover the top gap, click Danger Zone (3.2 - 8.6 s)
        swooshes.append(n[0] / FPS)
        await go("gap-scanner.html")
        await pg.evaluate("t=>{const c=[...document.querySelectorAll('#board .gp')].find(e=>e.innerText.includes(t));"
                          "document.querySelectorAll('#board .gp').forEach(e=>e.id='');if(c)c.id='aid-pick';else document.querySelector('#board .gp').id='aid-pick'}",
                          g["title"][:40])
        bd = await rect(pg, "#aid-pick")
        dz = await rect(pg, 'nav a[href="/expiry-returns.html"]')
        sy = max(0, bd[2] - 100)
        bd[1] = bd[2] + 40              # point at the card's title line
        cap2 = "<b>Gap Scanner</b><small>%s<br>%s</small>" % (G_TITLE, GAP)
        def s2(t, s):
            scr = lerp(0, sy, (s - 0.3) / 1.4)
            if s < 2.2:
                x, y = lerp(gs[0], W * 0.55, s / 2.0), lerp(gs[1], bd[1] - sy, s / 2.0)
            else:
                x, y = lerp(W * 0.55, dz[0], (s - 3.6) / 1.0), lerp(bd[1] - sy, dz[1], (s - 3.6) / 1.0)
            pr = 0.85 if 4.75 <= s < 4.95 else 1
            rp = (s - 4.8) / 0.5 if 4.8 <= s < 5.3 else 0
            hi = "#aid-pick" if 2.0 <= s < 3.7 else None
            return [x, y, pr, rp, dz[0], dz[1], cap2 if s > 1.6 else "", min(1, max(0, (s - 1.6) / 0.3)), scr, hi]
        clicks.append(n[0] / FPS + 4.8)
        await shoot(5.4, s2)

        # ---- 3. Danger Zone: scroll to the table, point at the return column (8.6 - 12.8 s)
        swooshes.append(n[0] / FPS)
        await go("expiry-returns.html")
        await pg.evaluate("()=>{for(const [id,re] of [['#f-days',/7 DAYS/i],['#f-sort',/highest/i]]){"
                          "const b=[...document.querySelectorAll(id+' .chip')].find(c=>re.test(c.textContent));b&&b.click()}}")
        await pg.wait_for_timeout(400)
        await pg.evaluate("([t,o])=>{const rs=[...document.querySelectorAll('#x-rows tr')];"
                          "const r=rs.find(e=>e.innerText.includes(t)&&e.innerText.includes(o))||rs.find(e=>e.innerText.includes(t))||rs[0];r.id='aid-row'}",
                          [d["title"][:40], d["outcome"][:20]])
        tw = await rect(pg, "#aid-row td:nth-child(4)")
        sy3 = max(0, tw[2] - 200)
        dz2 = await rect(pg, 'nav a[href="/expiry-returns.html"]')
        cap3 = "<b>Danger Zone</b> · closes %s<small>%s<br>%s at %.0f¢ · %+.1f%% if right</small>" % (
            D_WHEN, D_TITLE, d["side"].upper(), d["ask"], d["ret"])
        def s3(t, s):
            scr = lerp(0, sy3, (s - 0.2) / 1.5)
            x, y = lerp(dz2[0], tw[0] - 34, (s - 1.6) / 1.0), lerp(dz2[1], tw[2] + 20 - sy3, (s - 1.6) / 1.0)
            hi = "#aid-row" if s > 2.6 else None
            return [x, y, 1, 0, 0, 0, cap3 if s > 0.9 else "", min(1, max(0, (s - 0.9) / 0.3)), scr, hi]
        await shoot(4.2, s3)

        # ---- 4. end card (12.8 - 15 s)
        swooshes.append(n[0] / FPS)
        end = os.path.join(SITE, "_short_end.html")
        open(end, "w").write("""<!doctype html><meta charset=utf-8><style>
          body{margin:0;height:100vh;background:radial-gradient(circle at 50% 38%,#12324a 0,#0b1420 60%);color:#e8eef5;
               display:flex;flex-direction:column;align-items:center;justify-content:center;font-family:"Space Grotesk",sans-serif;text-align:center}
          img{width:110px} h1{font-size:40px;margin:18px 0 4px} .u{font:800 22px "JetBrains Mono",monospace;color:#3fdbe6;margin:6px 0 22px}
          .t{font-size:19px;color:#ffb347;font-weight:700;letter-spacing:.06em} .d{position:absolute;bottom:150px;left:30px;right:30px;font-size:13px;color:#8fa3b8}
          </style><img src="logo.svg"><h1>Alpha Intel Desk</h1><div class=u>alphainteldesk.com</div>
          <div class=t>FREE · NO SIGN-UP · LIVE</div>
          <div class=d>Not financial advice. Always check each site's rules before you trade.</div>""")
        await go("_short_end.html")
        await shoot(2.2, lambda t, s: [-99, -99, 1, 0, 0, 0, "", 0, 0, None])
        os.remove(end)
        await b.close()
    srv.terminate()
    total = n[0] / FPS
    make_audio("/tmp/short_audio.wav", total, clicks, swooshes)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", FR + "/%04d.jpg", "-i", "/tmp/short_audio.wav",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
                    "-shortest", "-movflags", "+faststart", OUT], check=True)
    json.dump(st, open(STATE, "w"), separators=(",", ":"))
    title = "Your Daily Gap: %.1f¢ + a Potential +%d%% Expiring Market Alert 🚨" % (g["net"], int(d["ret"]))   # James, Nov 15
    desc = ("Today's biggest prediction market price gap after fees: %s. Plus a Danger Zone contract that closes %s: %s, %s at %.0f¢.\n"
            "Not financial advice. https://alphainteldesk.com" % (G_TITLE, D_WHEN, D_TITLE, d["side"].upper(), d["ask"]))
    tags = "#predictionmarkets #polymarket #kalshi #alphaarcade #algorand #trading #markets #shorts"
    open(OUT.rsplit(".", 1)[0] + ".txt", "w").write("TITLE\n%s\n\nDESCRIPTION\n%s\n\nHASHTAGS\n%s\n" % (title, desc, tags))
    print("Short: %s (%.1f s) | gap: %s | danger zone: %s (%s)" % (OUT, total, G_TITLE, D_TITLE, D_WHEN))


def make_audio(path, secs, clicks, swooshes, sr=44100):
    """Calm bed with no noise anywhere (Nov 15 v2: v1 sounded like scratching: hard chord cut-offs + noise hats).
    Pads cross-fade bar to bar, soft sine bass + gentle low pulse, soft 'tock' clicks, airy sine sweeps on page changes."""
    t = np.arange(int(secs * sr)) / sr
    out = np.zeros_like(t)
    beat = 60 / 96
    bar = 4 * beat
    hz = lambda m: 440 * 2 ** ((m - 69) / 12)
    chords = [[57, 60, 64, 67], [53, 57, 60, 64], [48, 55, 60, 64], [55, 59, 62, 67]]   # Am7 Fmaj7 C G
    def seg(s0, length, att, rel):
        """smooth envelope: raised-cosine attack and release, so nothing ever starts or stops abruptly"""
        tt = t - s0
        e = np.zeros_like(t)
        m = (tt >= 0) & (tt < length)
        x = tt[m]
        a = np.where(x < att, 0.5 - 0.5 * np.cos(np.pi * x / att), 1.0)
        r = np.where(x > length - rel, 0.5 + 0.5 * np.cos(np.pi * (x - (length - rel)) / rel), 1.0)
        e[m] = a * r
        return e, tt
    k = 0
    while k * bar < secs:
        ch = chords[k % 4]
        e, tt = seg(k * bar - 0.4, bar + 0.8, 0.6, 0.6)                    # overlaps the next bar: a cross-fade
        for note in ch:
            f = hz(note)
            out += 0.045 * e * (np.sin(2 * np.pi * f * tt) + 0.5 * np.sin(2 * np.pi * f * 1.004 * tt + 1.0)
                                + 0.15 * np.sin(2 * np.pi * 2 * f * tt))
        eb, tb = seg(k * bar, bar, 0.05, 0.3)
        out += 0.11 * eb * np.sin(2 * np.pi * hz(ch[0] - 24) * tb)       # sine bass
        k += 1
    for b in range(int((secs - 2.2) / beat)):                            # soft low pulse, stops before the end card
        e, tt = seg(b * beat, 0.22, 0.004, 0.18)
        out += 0.22 * e * np.sin(2 * np.pi * (48 + 40 * np.exp(-np.maximum(tt, 0) * 25)) * tt)
    for c in clicks:                                                      # soft "tock"
        e, tt = seg(c, 0.06, 0.002, 0.055)
        out += 0.30 * e * np.sin(2 * np.pi * 1150 * tt) * np.exp(-np.maximum(tt, 0) * 60)
    for sw in swooshes:                                                   # airy rising sweep, pure tones
        e, tt = seg(sw - 0.3, 0.6, 0.25, 0.3)
        f = 300 + 900 * np.clip(tt / 0.6, 0, 1) ** 2
        out += 0.06 * e * np.sin(2 * np.pi * np.cumsum(f) / sr)
    a = 0.12                                                              # gentle one-pole low-pass: rounds off any edge
    try:
        from scipy.signal import lfilter
        y = lfilter([a], [1, a - 1], out)
    except ImportError:
        from itertools import accumulate
        y = np.array(list(accumulate(out * a, lambda p, x: p * (1 - a) + x)))
    fade = np.clip(t / 0.4, 0, 1) * np.clip((secs - t) / 1.5, 0, 1)
    y = y * fade
    y = y / max(1e-9, np.abs(y).max()) * 0.8
    with wave.open(path, "w") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((y * 32767).astype(np.int16).tobytes())


asyncio.run(main())
