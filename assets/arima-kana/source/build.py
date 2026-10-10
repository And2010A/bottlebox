"""Arima Kana avatar decoration + profile banner generator.

Builds every frame as SVG, renders it with headless Chromium (render.mjs),
then packs the frames into APNG / GIF with Pillow.

    python3 build.py            # writes into ../ (assets/arima-kana)

Design notes (what each motif refers to):
  * crimson satin ribbon + bow  -> Kana's red hair / the pink ribbon in the icon
  * pink scalloped lace         -> the frilly collar of her pink outfit in the icon
  * white hearts w/ blue rim    -> the doodled hearts drawn around her in the icon
  * white phone with red bow    -> the phone case she is holding in the icon
  * blue->pink starry sparkle   -> her sparkling ruby eyes
  * green pepper + music notes  -> "Piman Taiso", her hit song as a child star
  * light-blue teardrop         -> "the genius child actress who cries in 10 seconds"
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

N_FRAMES = 24
FRAME_MS = 1000 // 12  # 2 second loop

INK = "#2b0a16"          # outline colour, same dark plum as the Ruby set
CRIMSON = "#c8163f"
CRIMSON_DARK = "#7e0a27"
CRIMSON_LIGHT = "#ff6a8a"
PINK_LACE = "#fbd3de"
PINK_LACE_SHADE = "#ea94ad"
PINK = "#ff6f96"
HEART_RIM = "#9fd8ff"
PEPPER = "#3fae4a"
PEPPER_DARK = "#1d6b2a"


def f(v):
    return f"{v:.2f}"


def wave(t, phase=0.0):
    return math.sin(2 * math.pi * (t + phase))


# ---------------------------------------------------------------- primitives

def defs():
    return f"""
<defs>
  <linearGradient id="eyeStar" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#2f4fd8"/>
    <stop offset="0.45" stop-color="#9b4dff"/>
    <stop offset="1" stop-color="#ff6fa8"/>
  </linearGradient>
  <radialGradient id="glow">
    <stop offset="0" stop-color="#ffffff" stop-opacity="0.9"/>
    <stop offset="0.35" stop-color="#ff8fb4" stop-opacity="0.45"/>
    <stop offset="1" stop-color="#ff8fb4" stop-opacity="0"/>
  </radialGradient>
  <linearGradient id="beam" x1="1" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#ffe6f0" stop-opacity="0.55"/>
    <stop offset="1" stop-color="#ffe6f0" stop-opacity="0"/>
  </linearGradient>
  <linearGradient id="pepperShine" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="#7fdc79"/>
    <stop offset="1" stop-color="{PEPPER}"/>
  </linearGradient>
  <filter id="blur4" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="4"/></filter>
  <filter id="blur2" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="2"/></filter>
</defs>"""


HEART = ("M0,0.36 C-0.12,0.26 -0.52,0.02 -0.52,-0.24 C-0.52,-0.5 -0.16,-0.6 0,-0.34 "
         "C0.16,-0.6 0.52,-0.5 0.52,-0.24 C0.52,0.02 0.12,0.26 0,0.36 Z")
SPARK = "M0,-1 Q0.14,-0.14 1,0 Q0.14,0.14 0,1 Q-0.14,0.14 -1,0 Q-0.14,-0.14 0,-1 Z"


def heart(x, y, s, kind="white", rot=0):
    """kind: white (blue rim, like the icon's doodles) | pink | crimson"""
    sw = 1.5 / s
    tr = f'translate({f(x)},{f(y)}) rotate({rot}) scale({f(s)})'
    if kind == "white":
        return (f'<g transform="{tr}">'
                f'<path d="{HEART}" fill="#fff" stroke="{INK}" stroke-width="{f(sw)}" stroke-linejoin="round"/>'
                f'<path d="{HEART}" transform="scale(0.72) translate(0,-0.02)" fill="none" '
                f'stroke="{HEART_RIM}" stroke-width="{f(sw * 1.25)}"/>'
                f'<ellipse cx="-0.24" cy="-0.27" rx="0.07" ry="0.11" transform="rotate(-30 -0.24 -0.27)" fill="{HEART_RIM}" opacity="0.8"/>'
                f'</g>')
    fill = PINK if kind == "pink" else CRIMSON
    return (f'<g transform="{tr}">'
            f'<path d="{HEART}" fill="{fill}" stroke="{INK}" stroke-width="{f(sw)}" stroke-linejoin="round"/>'
            f'<ellipse cx="-0.24" cy="-0.25" rx="0.08" ry="0.12" transform="rotate(-30 -0.24 -0.25)" fill="#fff" opacity="0.85"/>'
            f'</g>')


def sparkle(x, y, s, fill="#fff", rot=0, outline=True):
    sw = 1.4 / s
    stroke = f'stroke="{INK}" stroke-width="{f(sw)}" stroke-linejoin="round"' if outline else ""
    return (f'<path d="{SPARK}" transform="translate({f(x)},{f(y)}) rotate({f(rot)}) scale({f(s)})" '
            f'fill="{fill}" {stroke}/>')


def eye_star(x, y, s, rot=0):
    """Starry sparkle with the blue->pink gradient of her eyes."""
    sw = 1.6 / s
    return (f'<g transform="translate({f(x)},{f(y)}) rotate({f(rot)}) scale({f(s)})">'
            f'<circle r="1.3" fill="url(#glow)"/>'
            f'<path d="{SPARK}" fill="url(#eyeStar)" stroke="{INK}" stroke-width="{f(sw)}" stroke-linejoin="round"/>'
            f'<path d="{SPARK}" transform="scale(0.32)" fill="#fff"/>'
            f'</g>')


def note(x, y, s, fill=CRIMSON, double=False, rot=0):
    sw = 1.3 / s
    common = f'fill="{fill}" stroke="{INK}" stroke-width="{f(sw)}" stroke-linejoin="round"'
    if double:
        body = (f'<path d="M-0.55,0.55 L-0.55,-0.75 L0.65,-1 L0.65,0.3 L0.48,0.3 L0.48,-0.6 L-0.38,-0.42 L-0.38,0.55 Z" {common}/>'
                f'<ellipse cx="-0.72" cy="0.55" rx="0.3" ry="0.22" transform="rotate(-20 -0.72 0.55)" {common}/>'
                f'<ellipse cx="0.48" cy="0.3" rx="0.3" ry="0.22" transform="rotate(-20 0.48 0.3)" {common}/>')
    else:
        body = (f'<path d="M0.12,0.55 L0.12,-0.9 C0.35,-0.6 0.75,-0.55 0.6,-0.1 C0.55,-0.4 0.4,-0.45 0.3,-0.5 L0.3,0.55 Z" {common}/>'
                f'<ellipse cx="-0.05" cy="0.6" rx="0.34" ry="0.25" transform="rotate(-20 -0.05 0.6)" {common}/>')
    return f'<g transform="translate({f(x)},{f(y)}) rotate({f(rot)}) scale({f(s)})">{body}</g>'


def pepper(x, y, s, rot=0):
    """Little green bell pepper charm (Piman Taiso). Origin = top of the stem."""
    sw = 1.4 / s
    st = f'stroke="{INK}" stroke-width="{f(sw)}" stroke-linejoin="round"'
    return (f'<g transform="translate({f(x)},{f(y)}) rotate({f(rot)}) scale({f(s)})">'
            # body: three lobes
            f'<path d="M0,0.28 C-0.45,0.1 -0.8,0.35 -0.72,0.95 C-0.66,1.45 -0.3,1.55 -0.12,1.38 '
            f'C0,1.55 0.12,1.55 0.22,1.4 C0.4,1.6 0.8,1.4 0.8,0.9 C0.82,0.35 0.42,0.1 0,0.28 Z" '
            f'fill="url(#pepperShine)" {st}/>'
            f'<path d="M-0.12,0.5 C-0.2,0.85 -0.18,1.15 -0.1,1.32 M0.22,0.5 C0.32,0.85 0.3,1.15 0.22,1.36" '
            f'fill="none" stroke="{PEPPER_DARK}" stroke-width="{f(sw * 0.9)}" stroke-linecap="round"/>'
            f'<ellipse cx="-0.42" cy="0.72" rx="0.09" ry="0.2" transform="rotate(20 -0.42 0.72)" fill="#fff" opacity="0.85"/>'
            # calyx + stem
            f'<path d="M-0.36,0.3 C-0.15,0.12 0.15,0.12 0.38,0.3 C0.18,0.4 -0.15,0.42 -0.36,0.3 Z" fill="{PEPPER_DARK}" {st}/>'
            f'<path d="M-0.05,0.24 C-0.05,0.1 0,-0.02 0.12,-0.1 L0.2,-0.02 C0.1,0.05 0.07,0.14 0.08,0.24 Z" fill="#6b8e23" {st}/>'
            # tiny blush face, it's a mascot after all
            f'<circle cx="-0.18" cy="0.85" r="0.05" fill="{INK}"/><circle cx="0.26" cy="0.85" r="0.05" fill="{INK}"/>'
            f'<path d="M-0.02,0.98 Q0.04,1.04 0.1,0.98" fill="none" stroke="{INK}" stroke-width="{f(sw * 0.7)}" stroke-linecap="round"/>'
            f'<ellipse cx="-0.35" cy="0.98" rx="0.1" ry="0.06" fill="{PINK}" opacity="0.8"/>'
            f'<ellipse cx="0.45" cy="0.98" rx="0.1" ry="0.06" fill="{PINK}" opacity="0.8"/>'
            f'</g>')


def teardrop(x, y, s):
    sw = 1.3 / s
    return (f'<g transform="translate({f(x)},{f(y)}) scale({f(s)})">'
            f'<path d="M0,-1 C0.25,-0.5 0.55,-0.1 0.55,0.25 C0.55,0.6 0.28,0.8 0,0.8 C-0.28,0.8 -0.55,0.6 -0.55,0.25 C-0.55,-0.1 -0.25,-0.5 0,-1 Z" '
            f'fill="#cdeeff" stroke="{INK}" stroke-width="{f(sw)}" stroke-linejoin="round"/>'
            f'<ellipse cx="-0.2" cy="0.2" rx="0.1" ry="0.2" fill="#fff"/>'
            f'</g>')


def bow(x, y, s, rot=0):
    """Crimson satin bow. Origin = knot."""
    sw = 1.6 / s
    st = f'stroke="{INK}" stroke-width="{f(sw)}" stroke-linejoin="round"'
    loop_l = "M-0.08,-0.05 C-0.35,-0.55 -0.98,-0.6 -1.02,-0.12 C-1.06,0.32 -0.5,0.42 -0.08,0.1 Z"
    fold_l = "M-0.18,0 C-0.42,-0.22 -0.7,-0.3 -0.86,-0.18 C-0.7,-0.1 -0.45,-0.04 -0.18,0.04 Z"
    tail_l = "M-0.1,0.1 C-0.25,0.45 -0.42,0.8 -0.62,1.05 L-0.42,1.0 L-0.36,1.2 C-0.18,0.9 -0.02,0.5 0.04,0.14 Z"
    mirror = 'transform="scale(-1,1)"'
    return (f'<g transform="translate({f(x)},{f(y)}) rotate({f(rot)}) scale({f(s)})">'
            f'<path d="{tail_l}" fill="{CRIMSON_DARK}" {st}/>'
            f'<path d="{tail_l}" fill="{CRIMSON}" {st} transform="scale(-1,1) rotate(-6)"/>'
            f'<path d="{loop_l}" fill="{CRIMSON}" {st}/>'
            f'<path d="{loop_l}" fill="{CRIMSON}" {st} {mirror}/>'
            f'<path d="{fold_l}" fill="{CRIMSON_DARK}" opacity="0.85"/>'
            f'<path d="{fold_l}" fill="{CRIMSON_DARK}" opacity="0.85" {mirror}/>'
            f'<path d="M-0.55,-0.36 C-0.7,-0.36 -0.82,-0.3 -0.88,-0.2" fill="none" stroke="{CRIMSON_LIGHT}" stroke-width="{f(sw * 1.3)}" stroke-linecap="round"/>'
            f'<path d="M0.55,-0.36 C0.7,-0.36 0.82,-0.3 0.88,-0.2" fill="none" stroke="{CRIMSON_LIGHT}" stroke-width="{f(sw * 1.3)}" stroke-linecap="round"/>'
            f'<ellipse cx="0" cy="0.02" rx="0.17" ry="0.2" fill="{CRIMSON}" {st}/>'
            f'<ellipse cx="-0.04" cy="-0.04" rx="0.05" ry="0.07" fill="{CRIMSON_LIGHT}"/>'
            f'</g>')


def ribbon(center_fn, t0, t1, width, twists, notch=True, steps=90):
    """Satin ribbon band following center_fn(u) -> (x, y), u in [t0, t1].

    Width is width*cos(phase) so the band visibly twists; where the sign flips
    we're looking at the back side, which is painted darker."""
    pts, ws = [], []
    for i in range(steps + 1):
        u = t0 + (t1 - t0) * i / steps
        pts.append(center_fn(u))
        ph = math.pi * twists * i / steps + 0.35
        w = width * (0.8 * math.cos(ph) + 0.3)  # biased so the front side shows more
        if abs(w) < 0.9:
            w = 0.9 if w >= 0 else -0.9
        ws.append(w)
    left, right = [], []
    for i, (x, y) in enumerate(pts):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, steps)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        ln = math.hypot(dx, dy) or 1
        nx, ny = -dy / ln, dx / ln
        w = ws[i] / 2
        left.append((x + nx * w, y + ny * w))
        right.append((x - nx * w, y - ny * w))
    outline = left[:]
    if notch:
        ex, ey = pts[-1]
        px, py = pts[-4]
        outline.append((px + (ex - px) * 0.2, py + (ey - py) * 0.2))
    outline += right[::-1]
    d = "M" + " L".join(f"{f(x)},{f(y)}" for x, y in outline) + " Z"
    out = [f'<path d="{d}" fill="{CRIMSON}" stroke="{INK}" stroke-width="1.8" stroke-linejoin="round"/>']
    # back side segments + centre highlight on the front side
    for i in range(steps):
        if ws[i] < 0 and ws[i + 1] < 0:
            q = [left[i], left[i + 1], right[i + 1], right[i]]
            out.append('<path d="M' + " L".join(f"{f(x)},{f(y)}" for x, y in q) + f' Z" fill="{CRIMSON_DARK}"/>')
    hl = []
    for i in range(steps + 1):
        if ws[i] > width * 0.45:
            hl.append(f"{f(pts[i][0] + (left[i][0] - pts[i][0]) * 0.35)},{f(pts[i][1] + (left[i][1] - pts[i][1]) * 0.35)}")
        elif hl:
            if len(hl) > 2:
                out.append(f'<polyline points="{" ".join(hl)}" fill="none" stroke="{CRIMSON_LIGHT}" stroke-width="1.3" stroke-linecap="round" opacity="0.9"/>')
            hl = []
    if len(hl) > 2:
        out.append(f'<polyline points="{" ".join(hl)}" fill="none" stroke="{CRIMSON_LIGHT}" stroke-width="1.3" stroke-linecap="round" opacity="0.9"/>')
    return "\n".join(out)


def lace_arc(cx, cy, r_in, r_out, a0, a1, n):
    """Pink scalloped lace ruffle along an arc (angles in degrees, 0 = +x, clockwise)."""
    def p(r, a):
        a = math.radians(a)
        return cx + r * math.cos(a), cy + r * math.sin(a)

    parts = [f"M{f(p(r_in, a0)[0])},{f(p(r_in, a0)[1])}"]
    step = (a1 - a0) / n
    x, y = p(r_out - 4, a0)
    parts.append(f"L{f(x)},{f(y)}")
    for i in range(n):
        aa, ab = a0 + step * i, a0 + step * (i + 1)
        c1 = p(r_out + 5, aa + step * 0.1)
        c2 = p(r_out + 5, ab - step * 0.1)
        e = p(r_out - 3, ab)
        parts.append(f"C{f(c1[0])},{f(c1[1])} {f(c2[0])},{f(c2[1])} {f(e[0])},{f(e[1])}")
    e = p(r_in, a1)
    parts.append(f"L{f(e[0])},{f(e[1])}")
    parts.append(f"A{r_in},{r_in} 0 0 0 {f(p(r_in, a0)[0])},{f(p(r_in, a0)[1])} Z")
    out = [f'<path d="{" ".join(parts)}" fill="{PINK_LACE}" stroke="{INK}" stroke-width="1.6" stroke-linejoin="round"/>']
    # fold shading toward the scallop valleys
    for i in range(1, n):
        a = a0 + step * i
        s, e = p(r_in + 3, a), p(r_out - 3, a)
        out.append(f'<line x1="{f(s[0])}" y1="{f(s[1])}" x2="{f(e[0])}" y2="{f(e[1])}" stroke="{PINK_LACE_SHADE}" stroke-width="1.2" stroke-linecap="round"/>')
    # eyelets
    for i in range(n):
        a = a0 + step * (i + 0.5)
        x, y = p((r_in + r_out) / 2 + 2, a)
        out.append(f'<circle cx="{f(x)}" cy="{f(y)}" r="1.5" fill="#fff" stroke="{PINK_LACE_SHADE}" stroke-width="0.8"/>')
    # stitched band on the inner edge
    s, e = p(r_in + 2.5, a0 + 1), p(r_in + 2.5, a1 - 1)
    out.append(f'<path d="M{f(s[0])},{f(s[1])} A{r_in + 2.5},{r_in + 2.5} 0 0 1 {f(e[0])},{f(e[1])}" fill="none" '
               f'stroke="{PINK}" stroke-width="1" stroke-dasharray="2.5 2" />')
    return "\n".join(out)


def phone(x, y, s, rot):
    """White phone case with the red bow, like the one in the icon."""
    sw = 1.6 / s
    st = f'stroke="{INK}" stroke-width="{f(sw)}" stroke-linejoin="round"'
    lens = "".join(
        f'<circle cx="{cx}" cy="{cy}" r="0.13" fill="#d8b77a" {st}/><circle cx="{cx}" cy="{cy}" r="0.07" fill="#3a2a1a"/>'
        for cx, cy in [(-0.28, -0.72), (-0.28, -0.42), (0.0, -0.57)])
    return (f'<g transform="translate({f(x)},{f(y)}) rotate({f(rot)}) scale({f(s)})">'
            f'<rect x="-0.52" y="-1" width="1.04" height="2" rx="0.2" fill="#fbf6f2" {st}/>'
            f'<rect x="-0.44" y="-0.92" width="0.88" height="1.84" rx="0.15" fill="none" stroke="#efd9dc" stroke-width="{f(sw * 0.8)}"/>'
            f'<rect x="-0.44" y="-0.88" width="0.62" height="0.62" rx="0.15" fill="#f1e7ea" {st}/>'
            f'{lens}<circle cx="0.02" cy="-0.36" r="0.04" fill="#f6d36b"/>'
            f'</g>' + bow_on_phone(x, y, s, rot))


def bow_on_phone(x, y, s, rot):
    # bow sits a bit below the middle of the case, rotated with it
    r = math.radians(rot)
    ox, oy = 0.05, 0.28
    bx = x + (ox * math.cos(r) - oy * math.sin(r)) * s
    by = y + (ox * math.sin(r) + oy * math.cos(r)) * s
    return bow(bx, by, s * 0.32, rot)


def halftone(x0, y0, cols, rows, gap, rmax, color, flip=False):
    out = []
    for j in range(rows):
        for i in range(cols):
            k = (i / max(cols - 1, 1))
            if flip:
                k = 1 - k
            r = rmax * (0.25 + 0.75 * k) * (1 - 0.15 * j)
            if (i + j) % 2:
                continue
            out.append(f'<circle cx="{f(x0 + i * gap)}" cy="{f(y0 + j * gap)}" r="{f(r)}" fill="{color}"/>')
    return "".join(out)


# ---------------------------------------------------------------- decoration

def decoration(t):
    cx = cy = 144
    p = []

    def polar(r, a):
        a = math.radians(a)
        return cx + r * math.cos(a), cy + r * math.sin(a)

    # halftone + dot sparkle clusters (same language as the Ruby set)
    p.append(halftone(96, 10, 9, 3, 4.2, 1.7, "#ff8fb0"))
    p.append(halftone(188, 266, 8, 3, 4.2, 1.6, "#ff8fb0", flip=True))

    # lace ruffle across the bottom
    p.append(lace_arc(cx, cy, 117, 136, 52, 128, 11))

    # long ribbon wrapping down the left side from the bow, ending over the lace
    def left_path(u):
        r = 131 + 3.5 * math.sin(math.radians(u) * 4 + 1)
        return polar(r, u)
    p.append(ribbon(left_path, -126, -222, 13, 3.3))

    # short tail along the top toward the right
    def top_path(u):
        r = 132 + 3 * math.sin(math.radians(u) * 5)
        return polar(r, u)
    p.append(ribbon(top_path, -122, -86, 12, 1.4))

    # phone with red bow, bottom-right, peeking over the rim like in the icon
    bob = 1.2 * wave(t, 0.1)
    p.append(phone(236, 228 + bob, 25, -22))

    # big crimson bow at top-left
    p.append(bow(58, 46, 34, -28 + 2.5 * wave(t, 0.0)))

    # right side heart cluster (white doodle hearts from the icon)
    hearts = [
        (264, 112, 21, "white", 12, 0.0),
        (279, 143, 13, "white", -8, 0.25),
        (259, 165, 15, "pink", 10, 0.5),
        (277, 82, 11, "white", 18, 0.7),
        (242, 86, 8, "crimson", -12, 0.4),
    ]
    for x, y, s, k, rot, ph in hearts:
        p.append(heart(x, y + 2.2 * wave(t, ph), s, k, rot))

    # two small hearts on the left ribbon side
    p.append(heart(24, 214 + 2 * wave(t, 0.6), 12, "white", -14))
    p.append(heart(44, 246 + 2 * wave(t, 0.15), 9, "pink", 8))

    # teardrop: "cries in 10 seconds"
    p.append(teardrop(271, 194 + 1.5 * wave(t, 0.3), 6))

    # pepper charm + music notes at the top-right (Piman Taiso)
    p.append(note(185, 18 + 1.5 * wave(t, 0.2), 6.5, CRIMSON, False, -10))
    p.append(note(236, 20 + 1.5 * wave(t, 0.55), 6.5, PINK, True, 8))
    p.append(pepper(211, 9, 16, 9 * wave(t, 0.0)))

    # starry eye sparkle, top-right
    p.append(eye_star(254, 48, 12 * (0.9 + 0.12 * wave(t, 0.0)), 10 * wave(t, 0.25)))

    # white sparkles
    for x, y, s, ph in [(150, 8, 6, 0.0), (24, 116, 5, 0.33), (279, 222, 5.5, 0.66),
                        (88, 276, 6, 0.5), (14, 172, 4, 0.15), (126, 22, 3.5, 0.8)]:
        k = 0.55 + 0.45 * (0.5 + 0.5 * wave(t, ph))
        p.append(sparkle(x, y, s * k))
    # tiny dots
    for x, y, r in [(166, 14, 1.2), (36, 98, 1.4), (284, 196, 1.2), (70, 282, 1.3), (8, 150, 1.1)]:
        p.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{INK}"/>')

    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="288" height="288" viewBox="0 0 288 288">'
            f'{defs()}{"".join(p)}</svg>')


# ---------------------------------------------------------------- banner

def banner(t):
    W, H = 448, 84
    p = [f"""
<linearGradient id="bg" x1="0" y1="0" x2="1" y2="0">
  <stop offset="0" stop-color="#14040b"/>
  <stop offset="0.38" stop-color="#3a0a1e"/>
  <stop offset="0.75" stop-color="#7d1a3d"/>
  <stop offset="1" stop-color="#b8406a"/>
</linearGradient>
<linearGradient id="vig" x1="0" y1="0" x2="0" y2="1">
  <stop offset="0" stop-color="#000" stop-opacity="0.25"/>
  <stop offset="0.5" stop-color="#000" stop-opacity="0"/>
  <stop offset="1" stop-color="#000" stop-opacity="0.35"/>
</linearGradient>
<rect width="{W}" height="{H}" fill="url(#bg)"/>"""]

    # stage spotlight beams from the top-right
    for x0, spread, op in [(430, 70, 0.5), (360, 55, 0.35), (300, 45, 0.22)]:
        sway = 4 * wave(t, x0 / 100)
        p.append(f'<path d="M{x0},-4 L{x0 - spread - 60 + sway},{H} L{x0 - 25 + sway},{H} Z" fill="url(#beam)" opacity="{op}"/>')

    # bokeh
    bokeh = [(250, 30, 14, "#ff7aa3", 0.25, 0.0), (300, 66, 10, "#ffb3cb", 0.22, 0.3),
             (340, 18, 8, "#ffd1e0", 0.3, 0.6), (395, 70, 16, "#ff6f96", 0.22, 0.1),
             (180, 60, 12, "#c2456e", 0.18, 0.8), (120, 22, 9, "#8e1f45", 0.25, 0.45),
             (430, 40, 9, "#fff", 0.18, 0.7), (60, 64, 10, "#5a0f2a", 0.35, 0.2)]
    for x, y, r, c, op, ph in bokeh:
        p.append(f'<circle cx="{f(x + 3 * wave(t, ph))}" cy="{y}" r="{r}" fill="{c}" opacity="{op}" filter="url(#blur4)"/>')
    p.append(f'<rect width="{W}" height="{H}" fill="url(#vig)"/>')

    # lace trim along the bottom right
    sc = []
    x = 214
    sc.append(f"M{x},{H + 2} L{x},{H - 6}")
    while x < W + 10:
        sc.append(f"C{x + 1},{H - 13} {x + 9},{H - 13} {x + 10},{H - 6}")
        x += 10
    sc.append(f"L{x},{H + 2} Z")
    p.append(f'<path d="{" ".join(sc)}" fill="{PINK_LACE}" opacity="0.92" stroke="{INK}" stroke-width="1.2"/>')
    for i in range(23):
        xx = 219 + i * 10
        if xx < W:
            p.append(f'<circle cx="{xx}" cy="{H - 4}" r="1.3" fill="#fff" stroke="{PINK_LACE_SHADE}" stroke-width="0.7"/>')

    # ribbon garland swag across the top right
    def swag(u):
        return 228 + u * 150, 2 + 22 * math.sin(math.pi * u) ** 1.3
    p.append(ribbon(swag, 0, 1, 8, 2.2, notch=False, steps=70))

    def swag2(u):
        return 378 + u * 80, 4 + 14 * math.sin(math.pi * u * 0.9)
    p.append(ribbon(swag2, 0, 1, 8, 1.4, notch=False, steps=50))

    # chain + pepper charm hanging from the bow
    sway = 7 * wave(t, 0.0)
    ax, ay = 378, 10
    beads = []
    for i in range(1, 6):
        k = i / 6 * 0.75
        bx = ax + math.sin(math.radians(sway)) * 34 * k
        by = ay + math.cos(math.radians(sway)) * 34 * k
        beads.append(f'<circle cx="{f(bx)}" cy="{f(by)}" r="1.7" fill="none" stroke="{INK}" stroke-width="0.9"/>'
                     f'<circle cx="{f(bx)}" cy="{f(by)}" r="1.2" fill="none" stroke="#f3d7e0" stroke-width="0.6"/>')
    p.append("".join(beads))
    ex = ax + math.sin(math.radians(sway)) * 28
    ey = ay + math.cos(math.radians(sway)) * 28
    p.append(pepper(ex, ey, 12, -sway))
    p.append(bow(ax, ay, 22, -6 + 2 * wave(t, 0.5)))

    # floating hearts
    hearts = [(262, 52, 15, "white", -10, 0.0), (296, 34, 9, "pink", 12, 0.3),
              (330, 58, 12, "white", 6, 0.55), (420, 28, 12, "white", 14, 0.8),
              (440, 62, 9, "pink", -8, 0.15), (230, 30, 7, "crimson", 10, 0.65),
              (175, 40, 6, "white", -6, 0.4)]
    for x, y, s, k, rot, ph in hearts:
        p.append(heart(x, y + 2.5 * wave(t, ph), s, k, rot))

    p.append(teardrop(312, 70 + 1.5 * wave(t, 0.2), 5))
    p.append(note(352, 38 + 2 * wave(t, 0.35), 6, PINK, True, -8))
    p.append(note(404, 50 + 2 * wave(t, 0.75), 5.5, "#fff", False, 10))

    # the big starry eye sparkle
    p.append(eye_star(355, 16, 10 * (0.9 + 0.12 * wave(t, 0.0)), 8 * wave(t, 0.3)))

    for x, y, s, ph in [(280, 14, 4.5, 0.0), (244, 70, 3.5, 0.4), (318, 22, 3, 0.7),
                        (436, 12, 4, 0.25), (150, 18, 3, 0.55), (96, 58, 2.5, 0.85),
                        (205, 12, 3, 0.1)]:
        k = 0.5 + 0.5 * (0.5 + 0.5 * wave(t, ph))
        p.append(sparkle(x, y, s * k, "#fff", 0, outline=False))

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

    deco = render([(f"deco_{i:02d}", decoration(t)) for i, t in enumerate(ts)], 1)
    deco[0].save(os.path.join(OUT, "kana-decoration.png"))
    save_apng(deco, os.path.join(OUT, "kana-decoration.apng"))
    with open(os.path.join(OUT, "kana-decoration.svg"), "w") as fh:
        fh.write(decoration(0))

    ban1 = render([(f"ban_{i:02d}", banner(t)) for i, t in enumerate(ts)], 1)
    ban1[0].convert("RGB").save(os.path.join(OUT, "kana-banner.png"))
    save_gif(ban1, os.path.join(OUT, "kana-banner.gif"))
    ban2 = render([("ban_hd", banner(0))], 2)
    ban2[0].convert("RGB").save(os.path.join(OUT, "kana-banner@2x.png"))
    with open(os.path.join(OUT, "kana-banner.svg"), "w") as fh:
        fh.write(banner(0))

    print("done ->", OUT)


if __name__ == "__main__":
    sys.exit(main())
