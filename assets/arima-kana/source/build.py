"""Arima Kana — "Genius Actress" avatar decoration + profile banner.

Builds each frame as SVG, renders it with headless Chromium (render.mjs),
then packs frames into APNG / GIF with Pillow.

    python3 build.py            # writes into ../ (assets/arima-kana)

Every motif comes from Kana herself:
  * beret with a ribbon            -> her signature look
  * stopwatch at 10 s + a tear     -> "the genius child actress who can cry in 10 seconds"
  * clapperboard + film strip      -> child-star actress, TV dramas
  * velvet curtain, spotlight      -> stage actress (Tsurugi in the Tokyo Blade play)
  * white penlights                -> her B-Komachi member colour; the season-1 finale
                                      where Aqua raises a white penlight for her
  * grumpy bell pepper             -> she secretly hates peppers, yet her childhood
                                      hit song was "Piman Taiso" (Bell Pepper Exercise)
  * "Hmph!" bubble + anger mark    -> tsundere
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


def film_strip(cx, cy, r_in, r_out, a0, a1, t):
    """Film strip bent around the avatar; frames scroll as it animates."""
    def p(r, a):
        a = math.radians(a)
        return cx + r * math.cos(a), cy + r * math.sin(a)

    out = []
    s0, s1 = p(r_out, a0), p(r_out, a1)
    e0, e1 = p(r_in, a1), p(r_in, a0)
    large = 1 if (a1 - a0) > 180 else 0
    d = (f"M{f(s0[0])},{f(s0[1])} A{r_out},{r_out} 0 {large} 1 {f(s1[0])},{f(s1[1])} "
         f"L{f(e0[0])},{f(e0[1])} A{r_in},{r_in} 0 {large} 0 {f(e1[0])},{f(e1[1])} Z")
    out.append(f'<path d="{d}" fill="{FILM}" stroke="{INK}" stroke-width="1.6" stroke-linejoin="round"/>')

    hole_step = 6.0
    travel = t * 12.0  # degrees the film advances per loop (multiple of both steps)

    a = a0 + 2 + (travel % hole_step)
    while a < a1 - 2:
        for r in (r_in + 2.8, r_out - 2.8):
            x, y = p(r, a)
            out.append(f'<rect x="-1.4" y="-1.1" width="2.8" height="2.2" rx="0.6" fill="#f3e6ea" '
                       f'transform="translate({f(x)},{f(y)}) rotate({f(a + 90)})"/>')
        a += hole_step

    icons = ["heart", "star", "beret", "pepper", "tear", "star"]
    fill = ["#ff7fa3", "#ffe3a3", "#ffd0dc", "#c9f0c3", "#d5efff", "#ffb3c6"]
    frame_step = 12.0
    rm = (r_in + r_out) / 2
    fw, fh = 8.4, (r_out - r_in) - 9
    a = a0 + 4 + (travel % frame_step)
    k = -int(travel // frame_step)
    while a < a1 - 4:
        x, y = p(rm, a)
        i = k % len(icons)
        g = [f'<rect x="{-fh / 2}" y="{-fw / 2}" width="{fh}" height="{fw}" rx="0.8" fill="{fill[i]}"/>']
        ic = icons[i]
        if ic == "heart":
            g.append('<path d="M0,1.6 C-0.6,1.1 -2.2,0.1 -2.2,-0.9 C-2.2,-2 -0.7,-2.3 0,-1.2 C0.7,-2.3 2.2,-2 2.2,-0.9 C2.2,0.1 0.6,1.1 0,1.6Z" fill="#c8163f" transform="rotate(-90)"/>')
        elif ic == "star":
            g.append(f'<path d="{SPARK}" transform="scale(2.4)" fill="#fff"/>')
        elif ic == "beret":
            g.append('<g transform="rotate(-90)"><ellipse cx="0" cy="-0.3" rx="2.6" ry="1.5" fill="#fff"/><rect x="-2" y="0.6" width="4" height="0.9" fill="#c8163f"/></g>')
        elif ic == "pepper":
            g.append('<g transform="rotate(-90)"><ellipse cx="0" cy="0.5" rx="1.9" ry="2" fill="#2f8f3a"/><rect x="-0.3" y="-2.2" width="0.6" height="1.2" fill="#6b8e23"/></g>')
        elif ic == "tear":
            g.append('<path d="M0,-2.2 C0.7,-1 1.4,0 1.4,0.8 C1.4,1.7 0.7,2.1 0,2.1 C-0.7,2.1 -1.4,1.7 -1.4,0.8 C-1.4,0 -0.7,-1 0,-2.2Z" fill="#6fb8ff" transform="rotate(-90)"/>')
        out.append(f'<g transform="translate({f(x)},{f(y)}) rotate({f(a)})">{"".join(g)}</g>')
        a += frame_step
        k += 1
    return "\n".join(out)


def clapperboard(x, y, s, rot, t):
    """Clapperboard that opens and snaps shut once per loop."""
    k = 1.0
    if 0.5 <= t < 0.88:
        k = max(0.0, 1 - math.sin(math.pi * (t - 0.5) / 0.76))
    open_deg = -26 * (1 - k)
    sw = 1.6 / s
    st = f'stroke="{INK}" stroke-width="{f(sw)}" stroke-linejoin="round"'
    stripes = "".join(
        f'<path d="M{f(-1 + i * 0.36)},-0.06 L{f(-0.82 + i * 0.36)},-0.06 L{f(-0.92 + i * 0.36)},-0.34 L{f(-1.1 + i * 0.36)},-0.34 Z" fill="#fff"/>'
        for i in range(6))
    stick = (f'<g transform="translate(-1,-0.06) rotate({f(open_deg)}) translate(1,0.06)">'
             f'<rect x="-1" y="-0.36" width="2" height="0.3" rx="0.04" fill="{FILM}"/>'
             f'<clipPath id="stk"><rect x="-1" y="-0.36" width="2" height="0.3"/></clipPath>'
             f'<g clip-path="url(#stk)">{stripes}</g>'
             f'<rect x="-1" y="-0.36" width="2" height="0.3" rx="0.04" fill="none" {st}/></g>')
    base_stripes = "".join(
        f'<path d="M{f(-1 + i * 0.36)},0 L{f(-0.82 + i * 0.36)},0 L{f(-0.72 + i * 0.36)},0.24 L{f(-0.9 + i * 0.36)},0.24 Z" fill="#fff"/>'
        for i in range(6))
    txt = (f'<text x="-0.86" y="0.62" font-family="{FONT}" font-weight="900" font-size="0.29" fill="#fff">ARIMA KANA</text>'
           f'<line x1="-0.9" y1="0.74" x2="0.9" y2="0.74" stroke="#fff" stroke-width="0.03" opacity="0.6"/>'
           f'<text x="-0.86" y="1.0" font-family="{FONT}" font-weight="700" font-size="0.2" fill="{GOLD}">SCENE 10</text>'
           f'<text x="0.12" y="1.0" font-family="{FONT}" font-weight="700" font-size="0.2" fill="{CRIMSON_LIGHT}">TAKE 1 ★</text>')
    return (f'<g transform="translate({f(x)},{f(y)}) rotate({f(rot)}) scale({f(s)})">'
            f'<rect x="-1" y="0" width="2" height="1.18" rx="0.08" fill="{FILM}" {st}/>'
            f'<clipPath id="bst"><rect x="-1" y="0" width="2" height="0.24"/></clipPath>'
            f'<g clip-path="url(#bst)">{base_stripes}</g>'
            f'<line x1="-1" y1="0.24" x2="1" y2="0.24" stroke="{INK}" stroke-width="{f(sw)}"/>'
            f'{txt}{stick}'
            f'<circle cx="-0.92" cy="-0.06" r="0.06" fill="{GOLD}" {st}/>'
            f'</g>')


def stopwatch(x, y, r, t):
    """Stopwatch whose hand runs 0 -> 10 seconds."""
    sw = 1.6 if r > 15 else 1.0
    hand = 60 * min(t / 0.8, 1.0)  # 10 s out of 60 = 60 deg
    ticks = []
    for i in range(12):
        a = math.radians(i * 30 - 90)
        r1, r2 = r * (0.62 if i % 3 else 0.55), r * 0.72
        ticks.append(f'<line x1="{f(math.cos(a) * r1)}" y1="{f(math.sin(a) * r1)}" x2="{f(math.cos(a) * r2)}" y2="{f(math.sin(a) * r2)}" '
                     f'stroke="{INK}" stroke-width="{f((1.2 if i % 3 == 0 else 0.7) * r / 21)}" stroke-linecap="round"/>')
    a1 = math.radians(hand - 90)
    wedge = (f'<path d="M0,0 L0,{f(-r * 0.7)} A{f(r * 0.7)},{f(r * 0.7)} 0 0 1 {f(math.cos(a1) * r * 0.7)},{f(math.sin(a1) * r * 0.7)} Z" '
             f'fill="{CRIMSON_LIGHT}" opacity="0.35"/>') if hand > 1 else ""
    hx, hy = math.cos(a1) * r * 0.66, math.sin(a1) * r * 0.66
    u = r / 21
    return (f'<g transform="translate({f(x)},{f(y)}) rotate(14) scale({f(u)})">'
            f'<rect x="-3.5" y="-28" width="7" height="5" rx="1.2" fill="url(#gold)" stroke="{INK}" stroke-width="{sw / u}"/>'
            f'<rect x="-1.6" y="-24" width="3.2" height="4" fill="{GOLD_DARK}" stroke="{INK}" stroke-width="{1 / u}"/>'
            f'<rect x="-2.5" y="-23" width="5" height="4" rx="1" fill="url(#gold)" stroke="{INK}" stroke-width="{1.2 / u}" transform="rotate(42)"/>'
            f'<circle r="21" fill="{CRIMSON}" stroke="{INK}" stroke-width="{sw / u}"/>'
            f'<circle r="17.2" fill="#fffaf4" stroke="{INK}" stroke-width="{1.2 / u}"/>'
            f'</g>'
            f'<g transform="translate({f(x)},{f(y)}) rotate(14)">'
            f'{wedge}{"".join(ticks)}'
            f'<text x="0" y="{f(r * 0.4)}" text-anchor="middle" font-family="{FONT_JP}" font-weight="700" font-size="{f(r * 0.36)}" fill="{CRIMSON}">10秒</text>'
            f'<line x1="0" y1="0" x2="{f(hx)}" y2="{f(hy)}" stroke="{INK}" stroke-width="{f(1.6 * u)}" stroke-linecap="round"/>'
            f'<circle r="{f(1.8 * u)}" fill="{CRIMSON}" stroke="{INK}" stroke-width="{f(0.8 * u)}"/>'
            f'<path d="M{f(-r * 0.62)},{f(-r * 0.52)} A{f(r * 0.8)},{f(r * 0.8)} 0 0 1 {f(-r * 0.2)},{f(-r * 0.78)}" fill="none" stroke="#fff" stroke-width="{f(1.6 * u)}" stroke-linecap="round" opacity="0.9"/>'
            f'</g>')


def tear(x, y, s, opacity=1.0):
    sw = 1.2 / s
    return (f'<g transform="translate({f(x)},{f(y)}) scale({f(s)})" opacity="{f(opacity)}">'
            f'<path d="M0,-1 C0.25,-0.5 0.55,-0.1 0.55,0.25 C0.55,0.6 0.28,0.8 0,0.8 C-0.28,0.8 -0.55,0.6 -0.55,0.25 C-0.55,-0.1 -0.25,-0.5 0,-1 Z" '
            f'fill="#bfe6ff" stroke="{INK}" stroke-width="{f(sw)}" stroke-linejoin="round"/>'
            f'<ellipse cx="-0.2" cy="0.2" rx="0.1" ry="0.2" fill="#fff"/></g>')


def falling_tear(x, y, s, t, drop=16):
    """Tear swells while the stopwatch runs, then falls once it hits 10 s."""
    if t >= 0.8:
        k = (t - 0.8) / 0.2
        return tear(x + 2 * k, y + drop * k, s, 1 - 0.7 * k)
    return tear(x, y, s * max(0.2, min(1.0, t / 0.8 * 1.2)))


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


def grumpy_pepper(x, y, s, rot):
    """Bell pepper with an annoyed face: she hates them (and sang Piman Taiso)."""
    sw = 1.4 / s
    st = f'stroke="{INK}" stroke-width="{f(sw)}" stroke-linejoin="round"'
    return (f'<g transform="translate({f(x)},{f(y)}) rotate({f(rot)}) scale({f(s)})">'
            f'<path d="M0,0.28 C-0.45,0.1 -0.8,0.35 -0.72,0.95 C-0.66,1.45 -0.3,1.55 -0.12,1.38 '
            f'C0,1.55 0.12,1.55 0.22,1.4 C0.4,1.6 0.8,1.4 0.8,0.9 C0.82,0.35 0.42,0.1 0,0.28 Z" fill="url(#pepperShine)" {st}/>'
            f'<path d="M-0.12,0.5 C-0.2,0.85 -0.18,1.15 -0.1,1.32 M0.22,0.5 C0.32,0.85 0.3,1.15 0.22,1.36" fill="none" stroke="{PEPPER_DARK}" stroke-width="{f(sw * 0.9)}" stroke-linecap="round"/>'
            f'<path d="M-0.36,0.3 C-0.15,0.12 0.15,0.12 0.38,0.3 C0.18,0.4 -0.15,0.42 -0.36,0.3 Z" fill="{PEPPER_DARK}" {st}/>'
            f'<path d="M-0.05,0.24 C-0.05,0.1 0,-0.02 0.12,-0.1 L0.2,-0.02 C0.1,0.05 0.07,0.14 0.08,0.24 Z" fill="#6b8e23" {st}/>'
            f'<path d="M-0.38,0.66 L-0.1,0.76 M0.48,0.66 L0.2,0.76" stroke="{INK}" stroke-width="{f(sw * 0.9)}" stroke-linecap="round"/>'
            f'<path d="M-0.3,0.86 L-0.12,0.86 M0.22,0.86 L0.4,0.86" stroke="{INK}" stroke-width="{f(sw * 1.1)}" stroke-linecap="round"/>'
            f'<path d="M-0.06,1.1 Q0.05,1.0 0.16,1.1" fill="none" stroke="{INK}" stroke-width="{f(sw * 0.8)}" stroke-linecap="round"/>'
            f'<ellipse cx="-0.45" cy="0.42" rx="0.08" ry="0.16" transform="rotate(25 -0.45 0.42)" fill="#fff" opacity="0.8"/>'
            f'</g>')


def anger_mark(x, y, s, rot=0):
    corners = "".join(
        f'<path d="M0.25,0.9 Q0.25,0.25 0.9,0.25" fill="none" stroke="{CRIMSON}" stroke-width="0.32" stroke-linecap="round" transform="rotate({a})"/>'
        for a in (0, 90, 180, 270))
    return f'<g transform="translate({f(x)},{f(y)}) rotate({f(rot)}) scale({f(s)})">{corners}</g>'


def hmph_bubble(x, y, t):
    bob = 1.2 * wave(t, 0.3)
    return (f'<g transform="translate({f(x)},{f(y + bob)}) rotate(6)">'
            f'<path d="M-24,-10 H24 Q28,-10 28,-6 V6 Q28,10 24,10 H-6 L-14,17 L-12,10 H-24 Q-28,10 -28,6 V-6 Q-28,-10 -24,-10 Z" '
            f'fill="#fff" stroke="{INK}" stroke-width="1.6" stroke-linejoin="round"/>'
            f'<text x="0" y="4.4" text-anchor="middle" font-family="{FONT}" font-weight="900" font-size="12.5" fill="{CRIMSON}" letter-spacing="0.3">Hmph!</text>'
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

def decoration(t):
    cx = cy = 144
    p = []

    # film strip wrapping the lower-left of the avatar
    p.append(film_strip(cx, cy, 120, 140, 92, 206, t))

    # white penlights crossed at the bottom-right (her member colour)
    p.append(penlight(208, 272, 18, -24 + 4 * wave(t, 0.0), pulse(t, 0.0)))
    p.append(penlight(238, 268, 18, 20 + 4 * wave(t, 0.5), pulse(t, 0.5)))

    # grumpy pepper + anger mark on the right
    p.append(grumpy_pepper(270, 160, 18, 8 * wave(t, 0.1)))
    p.append(anger_mark(282, 160, 5.2 * (0.85 + 0.2 * pulse(t, 0.0)), 10))

    # stopwatch at the top-right with a tear that falls when it reaches 10 s
    p.append(stopwatch(246, 74, 21, t))
    p.append(falling_tear(219, 82, 4.8, t))

    # tsundere bubble at the top
    p.append(hmph_bubble(172, 18, t))

    # clapperboard bottom-left, over the end of the film strip
    p.append(clapperboard(54, 236, 27, -16, t))

    # the beret, worn tilted on the top-left of the avatar
    p.append(beret(80, 52, 46, -28 + 1.5 * wave(t, 0.0)))

    for x, y, s, c, ph in [(140, 8, 5, GOLD, 0.0), (22, 112, 5.5, "#fff", 0.3), (280, 214, 5, GOLD, 0.6),
                           (110, 280, 5.5, "#fff", 0.15), (12, 160, 4, GOLD, 0.45), (276, 120, 3.5, "#fff", 0.8),
                           (205, 12, 3.5, "#fff", 0.7)]:
        p.append(sparkle(x, y, s * (0.5 + 0.55 * pulse(t, ph)), c, outline=True))

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

    # side props: grumpy pepper with anger mark, stopwatch + tear
    p.append(grumpy_pepper(398, 22, 12, 8 * wave(t, 0.2)))
    p.append(anger_mark(410, 24, 3.4, 10))
    p.append(stopwatch(312, 50, 11, t))
    p.append(falling_tear(298, 58, 3.1, t, drop=8))

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
