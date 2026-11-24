"""Dossier No. 2 YouTube Short: "Somebody Knew: The Jensen Huang Comeback Bets". 1080x1920, 30 fps, ~29 s.
Animated cards + the real Polymarket price line. No photos of real people."""
import json, math, os, subprocess, sys
from PIL import Image, ImageDraw, ImageFont
import numpy as np
from scipy.io import wavfile

REPO = "/home/claude/alphainteldesk-droid.github.io"
OUT = sys.argv[1] if len(sys.argv) > 1 else "/home/claude/short2/huang-dossier-short.mp4"
W, H, FPS, DUR = 1080, 1920, 30, 32.5
F = lambda n, b=True: ImageFont.truetype(REPO + "/fonts/SpaceGrotesk-%s.ttf" % ("Bold" if b else "Medium"), n)
MONO = lambda n: ImageFont.truetype(REPO + "/fonts/JetBrainsMono-ExtraBold.ttf", n)
BG, PANEL, LINE = (11, 17, 28), (17, 29, 45), (36, 58, 82)
CYAN, AMBER, TEXT, MUTED, GREEN, RED, BLUE = (63, 219, 230), (255, 179, 71), (232, 240, 248), (149, 168, 188), (62, 232, 138), (255, 107, 107), (111, 140, 255)
D = json.load(open(os.environ.get("HUANG_DATA", "/home/claude/dossier2/data.json")))
LOGO = Image.open("/tmp/logo.png").convert("RGBA").resize((96, 96)) if os.path.exists("/tmp/logo.png") else None

ease = lambda x: 1 - (1 - max(0, min(1, x))) ** 3
def fade(t, a, b=None, d=0.35):
    """0..1 in at a, out at b."""
    v = ease((t - a) / d)
    if b is not None:
        v = min(v, ease((b - t) / d))
    return max(0, v)

def text(im, xy, s, font, fill, alpha=1.0, anchor="la", dy=0):
    if alpha <= 0:
        return
    lay = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(lay).text((xy[0], xy[1] + dy), s, font=font, fill=fill + (int(255 * alpha),), anchor=anchor)
    im.alpha_composite(lay)

def box(im, xy, alpha=1.0, outline=LINE, fill=PANEL, r=28, width=3):
    if alpha <= 0:
        return
    lay = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(lay).rounded_rectangle(xy, r, fill=fill + (int(235 * alpha),), outline=outline + (int(255 * alpha),), width=width)
    im.alpha_composite(lay)

def wrap(s, font, maxw):
    out, cur = [], ""
    for w in s.split():
        t = (cur + " " + w).strip()
        if font.getlength(t) <= maxw:
            cur = t
        else:
            out.append(cur); cur = w
    return out + [cur]

def para(im, x, y, s, font, fill, alpha, maxw=900, lh=1.25, anchor="la", dy=0):
    for i, ln in enumerate(wrap(s, font, maxw)):
        text(im, (x, y + i * font.size * lh), ln, font, fill, alpha, anchor, dy)

def cta(sc, t, t0):
    """YouTube end card (James, Nov 24, 2026: on every YouTube video)."""
    a = fade(t, t0)
    if a <= 0:
        return
    text(sc, (W // 2, 430), "Like what you see?", F(88), TEXT, a, "mm")
    para(sc, W // 2, 520, "Want more intel like this?", F(50, False), MUTED, fade(t, t0 + 0.3), 900, anchor="ma")
    text(sc, (W // 2, 690), "alphainteldesk.com", F(84), CYAN, fade(t, t0 + 0.5), "mm")
    a1 = fade(t, t0 + 0.9)
    box(sc, (150, 850, W - 150, 1010), a1, outline=TEXT, fill=(30, 44, 62), r=80, width=4)
    text(sc, (W // 2, 930), "Hit LIKE", F(70), TEXT, a1, "mm")
    a2 = fade(t, t0 + 1.4)
    box(sc, (150, 1060, W - 150, 1220), a2, outline=(255, 0, 0), fill=(204, 0, 0), r=80, width=4)
    text(sc, (W // 2, 1140), "SUBSCRIBE", F(76), (255, 255, 255), a2, "mm")
    text(sc, (W // 2, 1310), "@alphainteldesk", F(52), MUTED, fade(t, t0 + 1.8), "mm")


def frame(t):
    im = Image.new("RGBA", (W, H), BG + (255,))
    dr = ImageDraw.Draw(im)
    for gx in range(0, W, 90):                       # faint grid
        dr.line([(gx, 0), (gx, H)], fill=(18, 28, 42))
    for gy in range(0, H, 90):
        dr.line([(0, gy), (W, gy)], fill=(18, 28, 42))
    # header (always)
    if LOGO:
        im.alpha_composite(LOGO, (60, 70))
    text(im, (176, 86), "Alpha Intel Desk", F(46), TEXT)
    text(im, (176, 140), "THE DOSSIER · NO. 2 · OPINION", F(30), AMBER)
    sc = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    # 1 hook 0-4
    a = fade(t, 0.1, 3.8)
    text(sc, (W // 2, 620), "SOMEBODY", F(150), TEXT, a, "mm", dy=(1 - a) * 40)
    text(sc, (W // 2, 790), "KNEW.", F(190), CYAN, fade(t, 0.6, 3.8), "mm")
    text(sc, (W // 2, 960), "The Jensen Huang comeback bets", F(54, False), MUTED, fade(t, 1.2, 3.8), "mm")
    # 2 timeline 4-8.5
    a1, a2 = fade(t, 4.1, 8.4), fade(t, 5.6, 8.4)
    box(sc, (80, 500, W - 80, 820), a1)
    text(sc, (130, 540), "NOV 17", F(44), AMBER, a1)
    para(sc, 130, 610, "Nvidia's board: \"does not intend to reinstate\" Huang", F(56), TEXT, a1, 820)
    box(sc, (80, 880, W - 80, 1160), a2, outline=CYAN)
    text(sc, (130, 920), "NOV 23", F(44), CYAN, a2)
    para(sc, 130, 990, "It brings him back. Stock +31%.", F(64), TEXT, a2, 820)
    text(sc, (W // 2, 1290), "So who saw it coming?", F(58), AMBER, fade(t, 6.8, 8.4), "mm")
    # 3 chart 8.5-14
    a = fade(t, 8.6, 13.9)
    if a > 0:
        box(sc, (60, 430, W - 60, 1370), a)
        text(sc, (110, 470), "POLYMARKET: \"HUANG BACK BY DEC 31\"", F(36), MUTED, a)
        x0, x1, y0, y1 = 130, W - 130, 1240, 620
        pts = [(tt, v) for tt, v in D["dec26"] if tt < 1795442400]
        t0, t1 = pts[0][0], pts[-1][0] + 3600
        X = lambda tt: x0 + (tt - t0) / (t1 - t0) * (x1 - x0)
        Y = lambda v: y0 - min(v, .16) / .16 * (y0 - y1)
        lay = Image.new("RGBA", im.size, (0, 0, 0, 0)); ld = ImageDraw.Draw(lay)
        for v in (0, .04, .08, .12, .16):
            ld.line([(x0, Y(v)), (x1, Y(v))], fill=LINE + (int(255 * a),), width=2)
            ld.text((x0 - 14, Y(v)), "%d¢" % round(v * 100), font=F(30, False), fill=MUTED + (int(255 * a),), anchor="rm")
        prog = ease((t - 9.0) / 3.0)
        n = max(2, int(len(pts) * prog))
        xy = [(X(tt), Y(v)) for tt, v in pts[:n]]
        ld.line(xy, fill=BLUE + (int(255 * a),), width=8, joint="curve")
        if prog >= 1:
            jx = X(t1)
            ld.line([(xy[-1][0], xy[-1][1]), (jx, y1 - 40)], fill=GREEN + (int(255 * a),), width=8)
            ld.text((jx - 10, y1 - 60), "99.5¢", font=F(54), fill=GREEN + (int(255 * a),), anchor="rb")
        sc.alpha_composite(lay)
        text(sc, (W // 2, 1300), "Priced at 2–6¢ until the news hit", F(48), TEXT, fade(t, 10.5, 13.9), "mm")
    # 4 stats 14-19.5
    for i, (big, small, col) in enumerate((("10", "new wallets among the top 50 buyers", CYAN),
                                           ("$11,700", "bet before the announcement", AMBER),
                                           ("$225,000", "paid out when he came back", GREEN))):
        a = fade(t, 14.2 + i * 1.0, 19.4)
        y = 470 + i * 330
        box(sc, (80, y, W - 80, y + 290), a, outline=col)
        text(sc, (130, y + 40), big, F(120), col, a)
        para(sc, 130, y + 185, small, F(44, False), TEXT, a, 820)
    # 5 wallet 19.5-24
    a = fade(t, 19.6, 23.9)
    box(sc, (80, 470, W - 80, 1330), a, outline=AMBER)
    text(sc, (130, 510), "ONE WALLET", F(44), AMBER, a)
    for i, ln in enumerate(("First trade: Nov 16", "Trades only Nvidia markets", "Friday: 77,311 YES at ~2¢")):
        text(sc, (130, 610 + i * 110), "•  " + ln, F(58), TEXT, fade(t, 20.0 + i * 0.6, 23.9))
    text(sc, (130, 1000), "Payout: ~$77,000", F(84), GREEN, fade(t, 22.0, 23.9))
    text(sc, (130, 1150), "Before any public sign of a deal.", F(46, False), MUTED, fade(t, 22.4, 23.9))
    # 6 end card 24-28
    a = fade(t, 24.1, 28.0)
    para(sc, W // 2, 520, "On the face of the data, someone knew something.", F(84), TEXT, a, 900, anchor="ma")
    text(sc, (W // 2, 960), "Full Dossier + all the data", F(52, False), MUTED, fade(t, 24.8, 28.0), "mm")
    text(sc, (W // 2, 1060), "alphainteldesk.com", F(84), CYAN, fade(t, 25.2, 28.0), "mm")
    para(sc, W // 2, 1500, "Opinion, not financial advice. Wallets are public and pseudonymous; no person is named or accused.", F(34, False), MUTED, fade(t, 25.6, 28.0), 900, anchor="ma")
    cta(sc, t, 28.1)
    im.alpha_composite(sc, (0, 150))
    # progress bar
    dr = ImageDraw.Draw(im)
    dr.rectangle([0, H - 14, int(W * t / DUR), H], fill=CYAN)
    return im.convert("RGB")


def audio(path):
    sr = 44100
    n = int(DUR * sr)
    tt = np.arange(n) / sr
    drone = 0.22 * np.sin(2 * np.pi * 55 * tt) + 0.12 * np.sin(2 * np.pi * 82.4 * tt) + 0.06 * np.sin(2 * np.pi * 110 * tt + 0.3 * np.sin(2 * np.pi * 0.2 * tt))
    drone *= 0.6 + 0.4 * np.sin(2 * np.pi * 0.25 * tt) ** 2
    pulse = np.zeros(n)
    for beat in np.arange(4.0, 24.0, 0.5):                 # heartbeat ticks from the timeline on
        i = int(beat * sr); k = np.arange(int(0.12 * sr))
        pulse[i:i + len(k)] += 0.35 * np.sin(2 * np.pi * 60 * k / sr) * np.exp(-k / (0.03 * sr))
    hits = np.zeros(n)
    for h in (0.1, 4.1, 8.6, 14.2, 19.6, 24.1):            # impacts on scene changes
        i = int(h * sr); k = np.arange(int(1.4 * sr))
        seg = (0.9 * np.sin(2 * np.pi * 40 * k / sr) + 0.4 * np.random.default_rng(int(h * 10)).standard_normal(len(k)) * np.exp(-k / (0.02 * sr))) * np.exp(-k / (0.35 * sr))
        hits[i:i + len(k)] += seg[:max(0, min(len(k), n - i))]
    riser = np.where((tt > 11.0) & (tt < 12.2), (tt - 11.0) / 1.2, 0) * 0.25 * np.sin(2 * np.pi * (200 + 600 * np.clip(tt - 11.0, 0, 1.2)) * tt)
    mix = drone + pulse + hits + riser
    fade_out = np.clip((DUR - tt) / 2.5, 0, 1); fade_in = np.clip(tt / 0.3, 0, 1)
    mix = mix * fade_in * fade_out
    mix = mix / np.max(np.abs(mix)) * 0.85
    wavfile.write(path, sr, (mix * 32767).astype(np.int16))


if __name__ == "__main__":
    fr = "/tmp/h2frames"
    os.makedirs(fr, exist_ok=True)
    for i in range(int(DUR * FPS)):
        frame(i / FPS).save("%s/%04d.jpg" % (fr, i), quality=92)
    audio("/tmp/h2audio.wav")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", fr + "/%04d.jpg", "-i", "/tmp/h2audio.wav",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
                    "-shortest", "-movflags", "+faststart", OUT], check=True)
    print("wrote", OUT)
