"""Arima Kana avatar decoration + profile banner.

Builds each frame as SVG, renders it with headless Chromium (render.mjs),
then packs frames into APNG / GIF with Pillow.

    python3 build.py            # writes into ../ (assets/arima-kana)

Decoration: Kana's ivory beret with a crimson ribbon (her signature look),
worn on the top-left, and one satin ribbon tied in a bow on the bottom-right.
Banner: the stage she grew up on, with her name in lights and a crowd waving
B-Komachi penlights, white (her colour) up front.
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

INK = "#22080f"
CRIMSON = "#c8163f"
CRIMSON_DARK = "#7a0a26"
CRIMSON_LIGHT = "#ff6a8a"
IVORY = "#f7f0e6"
IVORY_SHADE = "#e2d2c0"
GOLD = "#ffcf5a"
GOLD_DARK = "#b9822a"
FILM = "#1b1116"
PEPPER = "#3fae4a"
PEPPER_DARK = "#1d6b2a"
PENLIGHT = "#ffffff"
PENLIGHT_GLOW = "#cfe9ff"

FONT = "'Inter Display', 'Inter', sans-serif"
FONT_JP = "'IPAPGothic', 'IPAGothic', sans-serif"


def f(v):
    return f"{v:.2f}"


def wave(t, phase=0.0):
    return math.sin(2 * math.pi * (t + phase))


def pulse(t, phase=0.0):
    return 0.5 + 0.5 * wave(t, phase)


def defs():
    return f"""
<defs>
  <linearGradient id="beret" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#fffaf2"/><stop offset="1" stop-color="{IVORY_SHADE}"/>
  </linearGradient>
  <linearGradient id="velvet" x1="0" y1="0" x2="14" y2="0" gradientUnits="userSpaceOnUse" spreadMethod="reflect">
    <stop offset="0" stop-color="#4e0414"/><stop offset="1" stop-color="#d0204a"/>
  </linearGradient>
  <linearGradient id="valance" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#8e0c2c"/><stop offset="1" stop-color="#d62650"/>
  </linearGradient>
  <linearGradient id="gold" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#fff0b8"/><stop offset="0.5" stop-color="{GOLD}"/><stop offset="1" stop-color="{GOLD_DARK}"/>
  </linearGradient>
  <linearGradient id="spot" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#fff6e0" stop-opacity="0.65"/><stop offset="1" stop-color="#fff6e0" stop-opacity="0.08"/>
  </linearGradient>
  <radialGradient id="penGlow">
    <stop offset="0" stop-color="#ffffff" stop-opacity="0.95"/>
    <stop offset="0.4" stop-color="{PENLIGHT_GLOW}" stop-opacity="0.5"/>
    <stop offset="1" stop-color="{PENLIGHT_GLOW}" stop-opacity="0"/>
  </radialGradient>
  <linearGradient id="pepperShine" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="#86e07f"/><stop offset="1" stop-color="{PEPPER}"/>
  </linearGradient>
  <filter id="blur1" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="1.2"/></filter>
  <filter id="blur3" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="3"/></filter>
  <filter id="textGlow" x="-20%" y="-50%" width="140%" height="200%">
    <feGaussianBlur in="SourceAlpha" stdDeviation="1.6" result="b"/>
    <feFlood flood-color="#ff6f96"/><feComposite in2="b" operator="in" result="g"/>
    <feMerge><feMergeNode in="g"/><feMergeNode in="SourceGraphic"/></feMerge>
  </filter>
</defs>"""


SPARK = "M0,-1 Q0.12,-0.12 1,0 Q0.12,0.12 0,1 Q-0.12,0.12 -1,0 Q-0.12,-0.12 0,-1 Z"


def sparkle(x, y, s, fill="#fff", outline=False):
    st = f'stroke="{INK}" stroke-width="{f(1.2 / s)}" stroke-linejoin="round"' if outline else ""
    return f'<path d="{SPARK}" transform="translate({f(x)},{f(y)}) scale({f(s)})" fill="{fill}" {st}/>'


def small_bow(x, y, s, rot=0, fill=CRIMSON):
    sw = 1.4 / s
    st = f'stroke="{INK}" stroke-width="{f(sw)}" stroke-linejoin="round"'
    loop = "M0,0 C-0.3,-0.55 -1,-0.55 -1,-0.05 C-1,0.4 -0.35,0.35 0,0.05 Z"
    tail = "M-0.05,0.08 L-0.45,0.9 L-0.25,0.82 L-0.15,1.0 L0.08,0.12 Z"
    return (f'<g transform="translate({f(x)},{f(y)}) rotate({f(rot)}) scale({f(s)})">'
            f'<path d="{tail}" fill="{CRIMSON_DARK}" {st}/><path d="{tail}" fill="{fill}" {st} transform="scale(-1,1)"/>'
            f'<path d="{loop}" fill="{fill}" {st}/><path d="{loop}" fill="{fill}" {st} transform="scale(-1,1)"/>'
            f'<path d="M-0.55,-0.25 Q-0.75,-0.25 -0.82,-0.1" fill="none" stroke="{CRIMSON_LIGHT}" stroke-width="{f(sw * 1.2)}" stroke-linecap="round"/>'
            f'<ellipse rx="0.18" ry="0.2" fill="{fill}" {st}/>'
            f'</g>')


# ---------------------------------------------------------------- motifs

def beret(x, y, s, rot):
    """Kana's ivory beret with a crimson ribbon band and bow. Origin = band centre."""
    sw = 1.8 / s
    st = f'stroke="{INK}" stroke-width="{f(sw)}" stroke-linejoin="round"'
    dome = ("M-0.98,0.02 C-1.12,-0.38 -0.62,-0.72 0.02,-0.74 C0.7,-0.76 1.18,-0.4 1.02,0.02 "
            "C0.7,0.16 -0.68,0.16 -0.98,0.02 Z")
    band = "M-0.7,0.08 C-0.35,0.2 0.35,0.2 0.72,0.08 L0.68,0.3 C0.32,0.42 -0.32,0.42 -0.66,0.3 Z"
    r = math.radians(rot)
    bx = x + s * (0.62 * math.cos(r) - 0.2 * math.sin(r))
    by = y + s * (0.62 * math.sin(r) + 0.2 * math.cos(r))
    return (f'<g transform="translate({f(x)},{f(y)}) rotate({f(rot)}) scale({f(s)})">'
            f'<path d="{dome}" fill="url(#beret)" {st}/>'
            f'<path d="M-0.55,-0.45 C-0.25,-0.62 0.25,-0.64 0.6,-0.48" fill="none" stroke="{IVORY_SHADE}" stroke-width="{f(sw * 1.3)}" stroke-linecap="round"/>'
            f'<path d="M-0.8,-0.08 C-0.4,0.02 0.4,0.02 0.85,-0.1" fill="none" stroke="{IVORY_SHADE}" stroke-width="{f(sw)}" stroke-linecap="round"/>'
            f'<ellipse cx="-0.42" cy="-0.5" rx="0.2" ry="0.07" transform="rotate(-14 -0.42 -0.5)" fill="#fff"/>'
            f'<path d="M-0.04,-0.74 C-0.05,-0.86 0.02,-0.92 0.1,-0.9 L0.1,-0.74 Z" fill="{IVORY}" {st}/>'
            f'<path d="{band}" fill="{CRIMSON}" {st}/>'
            f'<path d="M-0.5,0.2 C-0.2,0.28 0.2,0.28 0.5,0.2" fill="none" stroke="{CRIMSON_LIGHT}" stroke-width="{f(sw * 0.9)}" stroke-linecap="round"/>'
            f'</g>' + small_bow(bx, by, s * 0.3, rot + 8))


def penlight(x, y, s, rot, glow, color=PENLIGHT, handle="#3a3036"):
    """Glowing penlight. Origin = bottom of the handle."""
    sw = 1.3 / s
    return (f'<g transform="translate({f(x)},{f(y)}) rotate({f(rot)}) scale({f(s)})">'
            f'<ellipse cx="0" cy="-1.55" rx="{f(0.55 + 0.25 * glow)}" ry="{f(1.25 + 0.2 * glow)}" fill="url(#penGlow)" opacity="{f(0.55 + 0.45 * glow)}"/>'
            f'<rect x="-0.17" y="-0.62" width="0.34" height="0.62" rx="0.08" fill="{handle}" stroke="{INK}" stroke-width="{f(sw)}"/>'
            f'<rect x="-0.12" y="-0.48" width="0.24" height="0.06" fill="{GOLD}"/>'
            f'<rect x="-0.2" y="-2.5" width="0.4" height="1.9" rx="0.2" fill="{color}" stroke="{INK}" stroke-width="{f(sw)}"/>'
            f'<rect x="-0.09" y="-2.35" width="0.08" height="1.5" rx="0.04" fill="#fff" opacity="0.9"/>'
            f'</g>')


def mic(x, y, s):
    """Stage microphone on a stand."""
    sw = 1.2 / s
    return (f'<g transform="translate({f(x)},{f(y)}) scale({f(s)})">'
            f'<ellipse cx="0" cy="0" rx="0.9" ry="0.16" fill="#000" opacity="0.5"/>'
            f'<path d="M-0.6,0 L0,-0.25 L0.6,0" fill="none" stroke="#2b2228" stroke-width="{f(sw * 2)}" stroke-linecap="round"/>'
            f'<line x1="0" y1="-0.25" x2="0" y2="-2.9" stroke="#2b2228" stroke-width="{f(sw * 2)}"/>'
            f'<line x1="0.08" y1="-0.4" x2="0.08" y2="-2.8" stroke="#8a7a82" stroke-width="{f(sw * 0.6)}"/>'
            f'<g transform="translate(0,-3.05) rotate(-20)">'
            f'<rect x="-0.14" y="0" width="0.28" height="0.6" rx="0.1" fill="#3a3036"/>'
            f'<ellipse cx="0" cy="-0.12" rx="0.26" ry="0.32" fill="#d9d2d6" stroke="{INK}" stroke-width="{f(sw)}"/>'
            f'<ellipse cx="-0.08" cy="-0.2" rx="0.06" ry="0.12" fill="#fff"/></g>'
            f'</g>')


# ---------------------------------------------------------------- decoration
#
# Kept deliberately sparse, the way Discord's own decorations are built:
# one hero piece (the beret, worn on the top-left like a hat decoration) and
# one supporting piece (a satin ribbon hugging the bottom-right rim, tied in a
# bow), balanced on the diagonal. Everything stays in the outer ring so the
# avatar itself is never covered.

BERET_DOME = ("M-0.98,0.02 C-1.12,-0.38 -0.62,-0.72 0.02,-0.74 C0.7,-0.76 1.18,-0.4 1.02,0.02 "
              "C0.7,0.16 -0.68,0.16 -0.98,0.02 Z")


def hero_beret(x, y, s, rot, t):
    """The beret at full size, with a light glint sweeping across it."""
    sw = 1.8 / s
    st = f'stroke="{INK}" stroke-width="{f(sw)}" stroke-linejoin="round"'
    band = "M-0.74,0.06 C-0.36,0.2 0.36,0.2 0.76,0.06 L0.72,0.32 C0.34,0.45 -0.34,0.45 -0.7,0.32 Z"
    # glint runs during the first 40% of the loop, then rests off the hat
    g = t / 0.4
    gx = -1.8 + 3.6 * g if g <= 1 else 3
    glint = (f'<clipPath id="domeClip"><path d="{BERET_DOME}"/></clipPath>'
             f'<g clip-path="url(#domeClip)"><rect x="{f(gx)}" y="-1" width="0.22" height="1.4" fill="#fff" opacity="0.75" transform="rotate(24 {f(gx)} 0)"/>'
             f'<rect x="{f(gx + 0.32)}" y="-1" width="0.07" height="1.4" fill="#fff" opacity="0.6" transform="rotate(24 {f(gx + 0.32)} 0)"/></g>')
    r = math.radians(rot)
    bx = x + s * (0.6 * math.cos(r) - 0.24 * math.sin(r))
    by = y + s * (0.6 * math.sin(r) + 0.24 * math.cos(r))
    return (f'<g transform="translate({f(x)},{f(y)}) rotate({f(rot)}) scale({f(s)})">'
            # soft drop shadow onto the avatar
            f'<ellipse cx="0.05" cy="0.32" rx="0.9" ry="0.16" fill="#000" opacity="0.18"/>'
            f'<path d="{BERET_DOME}" fill="url(#beret)" {st}/>'
            f'<path d="M-0.86,-0.06 C-0.5,0.04 0.5,0.04 0.9,-0.08 C0.8,0.06 -0.7,0.1 -0.86,-0.06 Z" fill="{IVORY_SHADE}"/>'
            f'<path d="M-0.6,-0.46 C-0.3,-0.62 0.24,-0.66 0.62,-0.5" fill="none" stroke="{IVORY_SHADE}" stroke-width="{f(sw * 1.2)}" stroke-linecap="round"/>'
            f'<ellipse cx="-0.46" cy="-0.47" rx="0.22" ry="0.07" transform="rotate(-16 -0.46 -0.47)" fill="#fff"/>'
            f'{glint}'
            f'<path d="M-0.04,-0.74 C-0.06,-0.88 0.02,-0.95 0.12,-0.92 L0.11,-0.74 Z" fill="{IVORY}" {st}/>'
            f'<path d="{band}" fill="{CRIMSON}" {st}/>'
            f'<path d="M-0.56,0.22 C-0.22,0.31 0.22,0.31 0.56,0.22" fill="none" stroke="{CRIMSON_LIGHT}" stroke-width="{f(sw * 0.9)}" stroke-linecap="round" opacity="0.9"/>'
            f'</g>' + small_bow(bx, by, s * 0.27, rot + 6))


def satin_ribbon(cx, cy, r, a_from, a_to, width, fold_at=0.55):
    """Ribbon band hugging the avatar rim from angle a_from to a_to (degrees).
    Narrows into one soft fold and ends in a V-cut."""
    steps = 60
    pts, ws = [], []
    for i in range(steps + 1):
        u = i / steps
        a = math.radians(a_from + (a_to - a_from) * u)
        rr = r + 1.6 * math.sin(u * math.pi * 2)
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
        fold = 1 - 0.62 * math.exp(-((u - fold_at) / 0.07) ** 2)
        taper = 1 - 0.3 * u
        ws.append(width * fold * taper)
    left, right = [], []
    for i, (x, y) in enumerate(pts):
        ax, ay = pts[max(i - 1, 0)]
        bx, by = pts[min(i + 1, steps)]
        dx, dy = bx - ax, by - ay
        ln = math.hypot(dx, dy) or 1
        nx, ny = -dy / ln, dx / ln
        left.append((x + nx * ws[i] / 2, y + ny * ws[i] / 2))
        right.append((x - nx * ws[i] / 2, y - ny * ws[i] / 2))
    ex, ey = pts[-1]
    px, py = pts[-5]
    notch = (px + (ex - px) * 0.35, py + (ey - py) * 0.35)
    poly = left + [notch] + right[::-1]
    d = "M" + " L".join(f"{f(x)},{f(y)}" for x, y in poly) + " Z"
    out = [f'<path d="{d}" fill="{CRIMSON}" stroke="{INK}" stroke-width="1.7" stroke-linejoin="round"/>']
    # darker inside of the fold
    for i in range(steps):
        if ws[i] < width * 0.7 * (1 - 0.3 * i / steps):
            q = [left[i], left[i + 1], right[i + 1], right[i]]
            out.append('<path d="M' + " L".join(f"{f(x)},{f(y)}" for x, y in q) + f' Z" fill="{CRIMSON_DARK}"/>')
    # satin sheen along the outer edge, broken at the fold
    seg = []
    for i in range(steps + 1):
        if ws[i] > width * 0.8 * (1 - 0.3 * i / steps) and i < steps - 3:
            x = pts[i][0] + (left[i][0] - pts[i][0]) * 0.45
            y = pts[i][1] + (left[i][1] - pts[i][1]) * 0.45
            seg.append(f"{f(x)},{f(y)}")
        else:
            if len(seg) > 2:
                out.append(f'<polyline points="{" ".join(seg)}" fill="none" stroke="{CRIMSON_LIGHT}" stroke-width="1.4" stroke-linecap="round"/>')
            seg = []
    if len(seg) > 2:
        out.append(f'<polyline points="{" ".join(seg)}" fill="none" stroke="{CRIMSON_LIGHT}" stroke-width="1.4" stroke-linecap="round"/>')
    return "\n".join(out)


def hero_bow(x, y, s, rot, t):
    """Satin bow with folds; the tails sway a little."""
    sw = 1.7 / s
    st = f'stroke="{INK}" stroke-width="{f(sw)}" stroke-linejoin="round"'
    loop = "M-0.08,-0.04 C-0.36,-0.56 -1.0,-0.62 -1.04,-0.12 C-1.08,0.34 -0.5,0.42 -0.08,0.1 Z"
    fold = "M-0.18,0 C-0.42,-0.22 -0.72,-0.3 -0.88,-0.18 C-0.72,-0.1 -0.46,-0.04 -0.18,0.04 Z"
    tail = "M-0.1,0.1 C-0.24,0.46 -0.4,0.82 -0.6,1.08 L-0.4,1.02 L-0.33,1.24 C-0.16,0.92 -0.02,0.52 0.04,0.14 Z"
    sway = 4 * wave(t, 0.15)
    return (f'<g transform="translate({f(x)},{f(y)}) rotate({f(rot)}) scale({f(s)})">'
            f'<g transform="rotate({f(sway)})"><path d="{tail}" fill="{CRIMSON_DARK}" {st}/></g>'
            f'<g transform="scale(-1,1) rotate({f(-6 + sway)})"><path d="{tail}" fill="{CRIMSON}" {st}/></g>'
            f'<path d="{loop}" fill="{CRIMSON}" {st}/>'
            f'<path d="{loop}" fill="{CRIMSON}" {st} transform="scale(-1,1)"/>'
            f'<path d="{fold}" fill="{CRIMSON_DARK}" opacity="0.85"/>'
            f'<path d="{fold}" fill="{CRIMSON_DARK}" opacity="0.85" transform="scale(-1,1)"/>'
            f'<path d="M-0.56,-0.38 C-0.72,-0.38 -0.84,-0.3 -0.9,-0.2" fill="none" stroke="{CRIMSON_LIGHT}" stroke-width="{f(sw * 1.3)}" stroke-linecap="round"/>'
            f'<path d="M0.56,-0.38 C0.72,-0.38 0.84,-0.3 0.9,-0.2" fill="none" stroke="{CRIMSON_LIGHT}" stroke-width="{f(sw * 1.3)}" stroke-linecap="round"/>'
            f'<ellipse cx="0" cy="0.02" rx="0.18" ry="0.21" fill="{CRIMSON}" {st}/>'
            f'<ellipse cx="-0.05" cy="-0.04" rx="0.05" ry="0.08" fill="{CRIMSON_LIGHT}"/>'
            f'</g>')


def decoration(t):
    cx = cy = 144
    p = []
    # ribbon hugging the bottom-right rim, tied at 45 degrees
    p.append(satin_ribbon(cx, cy, 126, 40, -24, 11, fold_at=0.6))
    p.append(satin_ribbon(cx, cy, 126, 50, 118, 11, fold_at=0.5))
    p.append(hero_bow(235, 235, 27, -42, t))
    # the beret, worn on the top-left of the head
    p.append(hero_beret(74, 47, 58, -34, t))
    # three quiet sparkles, one per piece plus one to bridge the diagonal
    for x, y, s, ph in [(150, 20, 6, 0.0), (270, 196, 5.5, 0.33), (26, 112, 4.5, 0.66)]:
        k = 0.35 + 0.65 * pulse(t, ph)
        p.append(f'<circle cx="{x}" cy="{y}" r="{f(s * 1.3 * k)}" fill="#fff" opacity="0.35" filter="url(#blur1)"/>')
        p.append(sparkle(x, y, s * k, "#fff", outline=True))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="288" height="288" viewBox="0 0 288 288">'
            f'{defs()}{"".join(p)}</svg>')


# ---------------------------------------------------------------- banner

def banner(t):
    W, H = 448, 84
    p = [f"""
<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
  <stop offset="0" stop-color="#0c0307"/><stop offset="0.55" stop-color="#22060f"/><stop offset="1" stop-color="#3d0a1c"/>
</linearGradient>
<rect width="{W}" height="{H}" fill="url(#bg)"/>"""]

    # spotlight on centre stage
    sx = 352
    inten = 0.85 + 0.15 * wave(t, 0.0)
    p.append(f'<path d="M{sx - 10},0 L{sx + 10},0 L{sx + 52},{H - 12} L{sx - 52},{H - 12} Z" fill="url(#spot)" opacity="{f(inten)}"/>')
    p.append(f'<ellipse cx="{sx}" cy="{H - 12}" rx="54" ry="7" fill="#fff6e0" opacity="{f(0.28 * inten)}" filter="url(#blur3)"/>')
    for i in range(9):
        ph = i / 9
        yy = 10 + 60 * ((t + ph) % 1)
        xx = sx - 20 + 40 * ((i * 0.37) % 1) + 3 * wave(t, ph)
        p.append(f'<circle cx="{f(xx)}" cy="{f(yy)}" r="0.8" fill="#fff" opacity="{f(0.3 + 0.5 * pulse(t, ph))}"/>')
    p.append(mic(sx, H - 12, 15))

    # side curtains, tied back with gold rope
    for side in (0, 1):
        if side == 0:
            d = f"M0,0 L46,0 C34,20 22,30 18,44 C22,58 16,72 10,{H} L0,{H} Z"
            tie = (17, 46)
        else:
            d = f"M{W},0 L{W - 42},0 C{W - 32},22 {W - 22},32 {W - 17},46 C{W - 20},60 {W - 14},72 {W - 10},{H} L{W},{H} Z"
            tie = (W - 17, 47)
        p.append(f'<path d="{d}" fill="url(#velvet)" stroke="{INK}" stroke-width="1.2"/>')
        p.append(f'<ellipse cx="{tie[0]}" cy="{tie[1]}" rx="7" ry="3" fill="url(#gold)" stroke="{INK}" stroke-width="0.8"/>')
        p.append(f'<path d="M{tie[0] - 1},{tie[1] + 2} L{tie[0] - 3},{tie[1] + 13} L{tie[0] + 3},{tie[1] + 13} Z" fill="url(#gold)" stroke="{INK}" stroke-width="0.7"/>')

    # top valance swags with gold trim and tassels
    n = 7
    w = W / n
    for i in range(n):
        x0 = i * w
        p.append(f'<path d="M{f(x0)},0 L{f(x0 + w)},0 L{f(x0 + w)},5 Q{f(x0 + w / 2)},22 {f(x0)},5 Z" fill="url(#valance)" stroke="{INK}" stroke-width="1"/>')
        p.append(f'<path d="M{f(x0 + 1)},6 Q{f(x0 + w / 2)},21 {f(x0 + w - 1)},6" fill="none" stroke="url(#gold)" stroke-width="1.6"/>')
    for i in range(n + 1):
        x0 = i * w
        sway = 1.5 * wave(t, i / n)
        p.append(f'<path d="M{f(x0)},4 L{f(x0 - 2.5 + sway)},14 L{f(x0 + 2.5 + sway)},14 Z" fill="url(#gold)" stroke="{INK}" stroke-width="0.6"/>')
        p.append(f'<circle cx="{f(x0)}" cy="5" r="2" fill="url(#gold)" stroke="{INK}" stroke-width="0.6"/>')

    # marquee sign with chasing bulbs
    mx0, my0, mw, mh = 154, 22, 140, 40
    p.append(f'<rect x="{mx0}" y="{my0}" width="{mw}" height="{mh}" rx="7" fill="url(#gold)" stroke="{INK}" stroke-width="1.4"/>')
    p.append(f'<rect x="{mx0 + 5}" y="{my0 + 5}" width="{mw - 10}" height="{mh - 10}" rx="4" fill="#5a0a20" stroke="{INK}" stroke-width="1"/>')
    perim = []
    for i in range(16):
        perim.append((mx0 + 7 + i * (mw - 14) / 15, my0 + 2.6))
    for i in range(4):
        perim.append((mx0 + mw - 2.6, my0 + 8 + i * (mh - 16) / 3))
    for i in range(16):
        perim.append((mx0 + mw - 7 - i * (mw - 14) / 15, my0 + mh - 2.6))
    for i in range(4):
        perim.append((mx0 + 2.6, my0 + mh - 8 - i * (mh - 16) / 3))
    phase = int(t * 15) % 3
    bulbs = []
    for i, (bx, by) in enumerate(perim):
        on = (i % 3) == phase
        bulbs.append(f'<circle cx="{f(bx)}" cy="{f(by)}" r="1.5" fill="{"#fffbe8" if on else "#c58a2e"}"/>')
        if on:
            bulbs.append(f'<circle cx="{f(bx)}" cy="{f(by)}" r="3.4" fill="#fff3c4" opacity="0.45" filter="url(#blur1)"/>')
    p.append("".join(bulbs))
    p.append(f'<text x="{mx0 + mw / 2}" y="{my0 + 24}" text-anchor="middle" font-family="{FONT}" font-weight="900" '
             f'font-size="15" fill="{IVORY}" letter-spacing="1" filter="url(#textGlow)">ARIMA KANA</text>')
    p.append(f'<text x="{mx0 + mw / 2}" y="{my0 + 32.5}" text-anchor="middle" font-family="{FONT_JP}" font-size="6.2" '
             f'fill="{GOLD}" letter-spacing="0.6">★ 10秒で泣ける天才役者 ★</text>')
    p.append(beret(mx0 + 8, my0 - 3, 20, -22))

    # audience: a sea of penlights in B-Komachi colours, one big white one for her
    lights = []
    colors = [("#ff8fbf", "#ff8fbf"), ("#ffe066", "#ffe066"), ("#ffffff", PENLIGHT_GLOW)]
    for i in range(30):
        lx = 30 + i * 13.3
        if abs(lx - sx) < 8:
            continue
        c, gc = colors[(i * 7) % 3]
        ang = 16 * wave(t, (i % 5) / 5)
        lights.append(
            f'<g transform="translate({f(lx)},{H - 1}) rotate({f(ang)})">'
            f'<ellipse cx="0" cy="-11" rx="2.6" ry="6" fill="{gc}" opacity="0.28" filter="url(#blur1)"/>'
            f'<rect x="-1" y="-15" width="2" height="10" rx="1" fill="{c}" opacity="0.9"/>'
            f'<rect x="-0.8" y="-5" width="1.6" height="5" fill="#2a2226"/></g>')
    p.append("".join(lights))
    heads = [f'<ellipse cx="{f(20 + i * 18.4 + (6 if i % 2 else 0))}" cy="{H + 2}" rx="9" ry="8" fill="#0a0205"/>' for i in range(24)]
    p.append("".join(heads))
    p.append(penlight(sx - 2, H + 2, 9.5, 10 * wave(t, 0.0), pulse(t, 0.0)))
    p.append(sparkle(sx + 10, H - 30, 3.5 * (0.6 + 0.6 * pulse(t, 0.2)), "#fff"))

    for x, y, s, c, ph in [(64, 18, 3.5, GOLD, 0.0), (318, 24, 3, "#fff", 0.35), (392, 56, 3.2, GOLD, 0.7),
                           (420, 34, 2.8, "#fff", 0.5), (120, 54, 2.6, "#fff", 0.2), (140, 26, 2.8, GOLD, 0.85)]:
        p.append(sparkle(x, y, s * (0.5 + 0.6 * pulse(t, ph)), c))

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
    still = 0.84  # tear mid-fall, used for the static images

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
