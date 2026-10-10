"""Arima Kana avatar decoration + profile banner ("White Penlight").

Builds each frame as SVG, renders it with headless Chromium (render.mjs),
then packs frames into APNG / GIF with Pillow.

    python3 build.py            # writes into ../ (assets/arima-kana)

Decoration: her white penlight (her B-Komachi colour) resting on the
bottom-left rim, with the glowing trail of its swing sweeping up the left side,
and a small idol-star cluster on the top-right. Two pieces on the diagonal,
outer ring only.
Banner: a long-exposure shot of a night concert, penlight light trails
streaking across a crimson-to-midnight sky.
"""

import json
import math
import os
import subprocess
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.dirname(HERE)
FRAMES_DIR = os.path.join(HERE, "_frames")

N_FRAMES = 30
FRAME_MS = 1000 // 15  # 2 second loop

CRIMSON = "#d0234f"
CRIMSON_DEEP = "#8c0f33"
PINK_GLOW = "#ff9ebb"
BLUSH = "#ffd3e0"
GOLD = "#ffd98a"
COOL = "#dff0ff"


def f(v):
    return f"{v:.2f}"


def wave(t, phase=0.0):
    return math.sin(2 * math.pi * (t + phase))


def pulse(t, phase=0.0):
    return 0.5 + 0.5 * wave(t, phase)


def defs():
    return f"""
<defs>
  <filter id="g2" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="2"/></filter>
  <filter id="g4" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="4"/></filter>
  <filter id="g8" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="8"/></filter>
  <linearGradient id="tube" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="#e9f3ff"/><stop offset="0.45" stop-color="#ffffff"/><stop offset="1" stop-color="#d7e6f7"/>
  </linearGradient>
  <linearGradient id="handle" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="{CRIMSON_DEEP}"/><stop offset="0.45" stop-color="{CRIMSON}"/><stop offset="1" stop-color="#6e0a27"/>
  </linearGradient>
  <linearGradient id="ring" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="#c9a24f"/><stop offset="0.5" stop-color="#fff1c4"/><stop offset="1" stop-color="#b08636"/>
  </linearGradient>
  <radialGradient id="starFill" cx="0.45" cy="0.4" r="0.7">
    <stop offset="0" stop-color="#ffffff"/><stop offset="0.6" stop-color="#fff4f7"/><stop offset="1" stop-color="{BLUSH}"/>
  </radialGradient>
</defs>"""


def star5(x, y, r, rot=0, inner=0.48, round_=0.18):
    """Soft 5-point idol star (slightly rounded tips) as a path."""
    pts = []
    for i in range(10):
        a = math.radians(-90 + i * 36 + rot)
        rr = r if i % 2 == 0 else r * inner
        pts.append((x + rr * math.cos(a), y + rr * math.sin(a)))
    d = []
    n = len(pts)
    for i in range(n):
        p0, p1, p2 = pts[i - 1], pts[i], pts[(i + 1) % n]
        a = (p1[0] + (p0[0] - p1[0]) * round_, p1[1] + (p0[1] - p1[1]) * round_)
        b = (p1[0] + (p2[0] - p1[0]) * round_, p1[1] + (p2[1] - p1[1]) * round_)
        d.append(("M" if i == 0 else "L") + f"{f(a[0])},{f(a[1])} Q{f(p1[0])},{f(p1[1])} {f(b[0])},{f(b[1])}")
    return " ".join(d) + " Z"


def twinkle(x, y, s, color="#fff", opacity=1.0):
    """Thin 4-point glint."""
    d = (f"M{f(x)},{f(y - s)} Q{f(x + s * 0.1)},{f(y - s * 0.1)} {f(x + s)},{f(y)} "
         f"Q{f(x + s * 0.1)},{f(y + s * 0.1)} {f(x)},{f(y + s)} Q{f(x - s * 0.1)},{f(y + s * 0.1)} {f(x - s)},{f(y)} "
         f"Q{f(x - s * 0.1)},{f(y - s * 0.1)} {f(x)},{f(y - s)} Z")
    return f'<path d="{d}" fill="{color}" opacity="{f(opacity)}"/>'


def mini_heart(x, y, s, color, rot=0):
    d = ("M0,0.36 C-0.12,0.26 -0.52,0.02 -0.52,-0.24 C-0.52,-0.5 -0.16,-0.6 0,-0.34 "
         "C0.16,-0.6 0.52,-0.5 0.52,-0.24 C0.52,0.02 0.12,0.26 0,0.36 Z")
    return f'<path d="{d}" transform="translate({f(x)},{f(y)}) rotate({f(rot)}) scale({f(s)})" fill="{color}"/>'


# ---------------------------------------------------------------- decoration

CX = CY = 144


def polar(r, a_deg):
    a = math.radians(a_deg)
    return CX + r * math.cos(a), CY + r * math.sin(a)


def trail_points():
    """The path, listed from the bright end (penlight tip) to the faint end.
    Faint end at the top of the avatar, down the left rim, then a short
    straight drop into the tip of the upright penlight at the bottom-left."""
    pts = []
    tip = (16.5, 196)
    join = polar(132, 165)
    for i in range(10):                       # straight drop, tip -> join
        u = i / 10
        pts.append((tip[0] + (join[0] - tip[0]) * u, tip[1] + (join[1] - tip[1]) * u))
    for i in range(61):                       # arc up the left rim to the top
        a = 165 + (268 - 165) * i / 60
        pts.append(polar(132, a))
    return pts


def path_d(pts):
    return "M" + " L".join(f"{f(x)},{f(y)}" for x, y in pts)


def light_trail(pts, w_max, t):
    """Glowing trail: thick and bright at pts[0], thin and fading at pts[-1]."""
    n = len(pts) - 1
    glow, edge, core = [], [], []
    for i in range(n):
        k = (1 - i / n) ** 1.3
        seg = f'M{f(pts[i][0])},{f(pts[i][1])} L{f(pts[i + 1][0])},{f(pts[i + 1][1])}'
        glow.append(f'<path d="{seg}" stroke="{PINK_GLOW}" stroke-width="{f(2 + w_max * 1.6 * k)}" opacity="{f(0.55 * k)}" stroke-linecap="round"/>')
        edge.append(f'<path d="{seg}" stroke="{CRIMSON}" stroke-width="{f(1 + w_max * 0.9 * k)}" opacity="{f(0.85 * k ** 0.7)}" stroke-linecap="round"/>')
        core.append(f'<path d="{seg}" stroke="#ffffff" stroke-width="{f(0.6 + w_max * 0.5 * k)}" opacity="{f(min(1, 0.25 + k))}" stroke-linecap="round"/>')
    out = [f'<g filter="url(#g4)">{"".join(glow)}</g>', "".join(edge), "".join(core)]
    # sparks drifting off the trail
    for j in range(6):
        u = (t + j / 6) % 1
        i = int(n * (0.1 + 0.8 * ((j * 0.37) % 1)))
        x, y = pts[i]
        dx, dy = x - CX, y - CY
        ln = math.hypot(dx, dy) or 1
        d = (4 + 10 * u) * (1 if j % 2 else -0.4)
        op = math.sin(math.pi * u)
        out.append(twinkle(x + dx / ln * d, y + dy / ln * d, 1.6 + 1.6 * op, "#fff", op))
    return "\n".join(out)


def penlight_piece(x, y, rot, t, scale=1.0, flash=0.0):
    """Penlight lying along the rim; origin = centre of the stick, tip at -y."""
    glow = min(1.6, 0.35 * pulse(t, 0.0) + flash)
    return (f'<g transform="translate({f(x)},{f(y)}) rotate({f(rot)}) scale({f(scale)})">'
            # glow
            f'<ellipse cx="0" cy="-8" rx="{f(11 + 3 * glow)}" ry="{f(24 + 3 * glow)}" fill="{PINK_GLOW}" opacity="{f(0.35 + 0.2 * glow)}" filter="url(#g8)"/>'
            f'<ellipse cx="0" cy="-8" rx="{f(6 + 2 * glow)}" ry="{f(19 + 2 * glow)}" fill="#ffffff" opacity="{f(0.55 + 0.3 * glow)}" filter="url(#g4)"/>'
            # tube
            f'<rect x="-5" y="-27" width="10" height="34" rx="5" fill="url(#tube)" stroke="{CRIMSON}" stroke-width="1.3"/>'
            f'<rect x="-2.6" y="-24" width="1.8" height="27" rx="0.9" fill="#fff"/>'
            # little heart on the tube
            + mini_heart(1.2, -6, 6.5, CRIMSON) +
            # gold ring + crimson handle
            f'<rect x="-6" y="6" width="12" height="4" rx="1.4" fill="url(#ring)" stroke="{CRIMSON_DEEP}" stroke-width="0.9"/>'
            f'<rect x="-5" y="10" width="10" height="15" rx="3" fill="url(#handle)" stroke="{CRIMSON_DEEP}" stroke-width="1.1"/>'
            f'<rect x="-3.2" y="12" width="1.6" height="10" rx="0.8" fill="#ff7a9a" opacity="0.8"/>'
            f'<circle cx="0" cy="27" r="1.8" fill="none" stroke="url(#ring)" stroke-width="1.2"/>'
            f'</g>')


def star_cluster(t):
    """Idol stars on the top-right: one main star, two small, one tiny heart."""
    out = []
    x, y = polar(130, -46)
    s = 1 + 0.06 * wave(t, 0.0)
    rot = 6 * wave(t, 0.25)
    out.append(f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(20 * s)}" fill="{PINK_GLOW}" opacity="0.4" filter="url(#g8)"/>')
    out.append(f'<path d="{star5(x, y, 17 * s, rot)}" fill="url(#starFill)" stroke="{CRIMSON}" stroke-width="1.6" stroke-linejoin="round"/>')
    out.append(f'<path d="{star5(x - 2, y - 2.5, 7 * s, rot, 0.5)}" fill="#fff"/>')
    # small stars
    for (r, a, size, ph) in [(132, -70, 7.5, 0.3), (136, -24, 6, 0.6)]:
        sx, sy = polar(r, a)
        k = 0.75 + 0.3 * pulse(t, ph)
        out.append(f'<path d="{star5(sx, sy, size * k, 10 * wave(t, ph))}" fill="#fff" stroke="{CRIMSON}" stroke-width="1.2" stroke-linejoin="round"/>')
    hx, hy = polar(118, -58)
    out.append(mini_heart(hx + 1.5 * wave(t, 0.5), hy, 9, CRIMSON, -14))
    # glints
    for (r, a, size, ph) in [(142, -58, 4, 0.1), (120, -36, 3.2, 0.55), (146, -38, 2.6, 0.8)]:
        gx, gy = polar(r, a)
        k = pulse(t, ph)
        out.append(twinkle(gx, gy, size * (0.4 + 0.7 * k), "#fff", 0.4 + 0.6 * k))
        out.append(twinkle(gx, gy, size * (0.4 + 0.7 * k) * 1.25, PINK_GLOW, 0.25 * k))
    return "\n".join(out)


def decoration(t):
    """A light starts at the top, runs down the left rim and drops into the
    upright penlight at the bottom-left, which flashes when it arrives."""
    pts = trail_points()
    p = [light_trail(pts, 10, t)]

    travel = 0.55                   # share of the loop the light spends travelling
    flash = 0.0
    if t < travel:
        u = (t / travel) ** 1.5     # speeds up as it falls
        n = len(pts) - 1
        head = int(n * (1 - u))
        tail = min(n, head + 14)
        seg = pts[head:tail + 1]
        hx, hy = pts[head]
        p.append(f'<path d="{path_d(seg)}" stroke="{PINK_GLOW}" stroke-width="12" opacity="0.55" fill="none" stroke-linecap="round" filter="url(#g4)"/>')
        p.append(f'<path d="{path_d(seg)}" stroke="#fff" stroke-width="4" opacity="0.9" fill="none" stroke-linecap="round" stroke-linejoin="round"/>')
        p.append(f'<circle cx="{f(hx)}" cy="{f(hy)}" r="13" fill="{PINK_GLOW}" opacity="0.7" filter="url(#g4)"/>')
        p.append(f'<circle cx="{f(hx)}" cy="{f(hy)}" r="5" fill="#fff"/>')
        p.append(twinkle(hx, hy, 12, "#fff", 1.0))
    else:
        k = (t - travel) / (1 - travel)
        flash = 1.2 * math.exp(-5 * k)

    # upright penlight, tip at the bottom of the trail
    tip_x, tip_y = pts[0]
    scale = 1.3
    p.append(penlight_piece(tip_x, tip_y + 27 * scale, 0, t, scale, flash))
    if flash > 0.05:
        p.append(twinkle(tip_x, tip_y, 6 + 14 * flash, "#fff", min(1, flash)))

    p.append(star_cluster(t))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="288" height="288" viewBox="0 0 288 288">'
            f'{defs()}{"".join(p)}</svg>')


# ---------------------------------------------------------------- banner

def banner(t):
    W, H = 448, 84
    p = [f"""
<linearGradient id="sky" x1="0" y1="0" x2="1" y2="0.4">
  <stop offset="0" stop-color="#0b0716"/><stop offset="0.5" stop-color="#1c0a24"/><stop offset="1" stop-color="#4a0f2c"/>
</linearGradient>
<radialGradient id="haze" cx="0.78" cy="0.55" r="0.5">
  <stop offset="0" stop-color="{CRIMSON}" stop-opacity="0.5"/><stop offset="1" stop-color="{CRIMSON}" stop-opacity="0"/>
</radialGradient>
<rect width="{W}" height="{H}" fill="url(#sky)"/>
<rect width="{W}" height="{H}" fill="url(#haze)"/>"""]

    # bokeh
    for (x, y, r, c, op, ph) in [(300, 20, 10, BLUSH, 0.18, 0.0), (380, 64, 14, PINK_GLOW, 0.2, 0.3),
                                 (420, 18, 8, "#fff", 0.16, 0.6), (240, 66, 9, CRIMSON, 0.3, 0.2),
                                 (190, 14, 6, BLUSH, 0.16, 0.8), (130, 60, 7, "#6b2a6e", 0.3, 0.45),
                                 (350, 36, 5, "#fff", 0.22, 0.15)]:
        p.append(f'<circle cx="{f(x + 2.5 * wave(t, ph))}" cy="{y}" r="{r}" fill="{c}" opacity="{f(op * (0.7 + 0.3 * pulse(t, ph)))}" filter="url(#g2)"/>')

    # long-exposure penlight trails: (start, ctrl1, ctrl2, end, colour, width)
    trails = [
        ((150, 92), (230, 10), (330, 4), (452, 46), "#ffffff", 2.4),
        ((200, 96), (280, 40), (360, 30), (452, 70), PINK_GLOW, 1.8),
        ((240, -6), (300, 60), (380, 70), (452, 22), CRIMSON, 2.0),
        ((110, 40), (210, 70), (300, 80), (420, -6), BLUSH, 1.2),
        ((270, 92), (330, 50), (400, 50), (452, 88), "#ffffff", 1.2),
    ]
    for i, (a, b, c, d, col, w) in enumerate(trails):
        path = f"M{a[0]},{a[1]} C{b[0]},{b[1]} {c[0]},{c[1]} {d[0]},{d[1]}"
        p.append(f'<path d="{path}" stroke="{col}" stroke-width="{f(w * 4)}" opacity="0.28" fill="none" filter="url(#g4)" stroke-linecap="round"/>')
        p.append(f'<path d="{path}" stroke="{col}" stroke-width="{f(w)}" opacity="0.85" fill="none" stroke-linecap="round"/>')
        # a bright pulse travelling along each trail
        off = -400 * ((t + i * 0.21) % 1)
        p.append(f'<path d="{path}" stroke="#ffffff" stroke-width="{f(w * 3)}" fill="none" stroke-linecap="round" '
                 f'stroke-dasharray="40 366" stroke-dashoffset="{f(off)}" pathLength="406" opacity="0.6" filter="url(#g2)"/>')

    # stars
    for (x, y, s, ph) in [(60, 18, 2.4, 0.0), (96, 50, 1.6, 0.4), (176, 30, 2, 0.7), (262, 14, 2.6, 0.2),
                          (318, 58, 2, 0.55), (404, 40, 3, 0.85), (436, 62, 1.8, 0.3), (24, 62, 1.6, 0.6)]:
        k = pulse(t, ph)
        p.append(twinkle(x, y, s * (0.6 + 0.8 * k), "#fff", 0.45 + 0.55 * k))
    # main idol star on the right, echoing the decoration
    sx, sy = 392, 30
    s = 1 + 0.07 * wave(t, 0.0)
    p.append(f'<circle cx="{sx}" cy="{sy}" r="{f(18 * s)}" fill="{PINK_GLOW}" opacity="0.45" filter="url(#g8)"/>')
    p.append(f'<path d="{star5(sx, sy, 12 * s, 6 * wave(t, 0.25))}" fill="url(#starFill)" stroke="{CRIMSON}" stroke-width="1.3" stroke-linejoin="round"/>')
    p.append(f'<path d="{star5(sx - 1.5, sy - 2, 5 * s, 6 * wave(t, 0.25), 0.5)}" fill="#fff"/>')
    p.append(mini_heart(414, 46 + 1.5 * wave(t, 0.4), 7, CRIMSON, 12))

    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
            f'{defs()}{"".join(p)}</svg>')


# ---------------------------------------------------------------- render

def render(jobs, scale):
    os.makedirs(FRAMES_DIR, exist_ok=True)
    manifest = []
    for name, svg in jobs:
        sp = os.path.join(FRAMES_DIR, name + ".svg")
        with open(sp, "w") as fh:
            fh.write(svg)
        manifest.append({"svg": sp, "png": os.path.join(FRAMES_DIR, f"{name}@{scale}x.png")})
    mp = os.path.join(FRAMES_DIR, "manifest.json")
    with open(mp, "w") as fh:
        json.dump({"scale": scale, "items": manifest}, fh)
    subprocess.run(["node", os.path.join(HERE, "render.mjs"), mp], check=True)
    return [Image.open(m["png"]).convert("RGBA") for m in manifest]


def save_apng(frames, path):
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=FRAME_MS,
                   loop=0, disposal=1, blend=0, optimize=True)


def save_gif(frames, path):
    pal = [fr.convert("RGB").quantize(colors=255, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.FLOYDSTEINBERG)
           for fr in frames]
    pal[0].save(path, save_all=True, append_images=pal[1:], duration=FRAME_MS, loop=0, optimize=False)


def main():
    ts = [i / N_FRAMES for i in range(N_FRAMES)]
    still = 0.62  # penlight flashing, used for the static images

    deco = render([(f"deco_{i:02d}", decoration(t)) for i, t in enumerate(ts)], 1)
    save_apng(deco, os.path.join(OUT, "kana-decoration.apng"))
    render([("deco_still", decoration(still))], 1)[0].save(os.path.join(OUT, "kana-decoration.png"))
    with open(os.path.join(OUT, "kana-decoration.svg"), "w") as fh:
        fh.write(decoration(still))

    ban = render([(f"ban_{i:02d}", banner(t)) for i, t in enumerate(ts)], 2)
    save_gif(ban, os.path.join(OUT, "kana-banner.gif"))
    render([("ban_still2", banner(still))], 2)[0].convert("RGB").save(os.path.join(OUT, "kana-banner@2x.png"))
    render([("ban_still1", banner(still))], 1)[0].convert("RGB").save(os.path.join(OUT, "kana-banner.png"))
    with open(os.path.join(OUT, "kana-banner.svg"), "w") as fh:
        fh.write(banner(still))

    print("done ->", OUT)


if __name__ == "__main__":
    sys.exit(main())
