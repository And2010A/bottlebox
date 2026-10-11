"""Generates the Glock 19 mod's art and audio.

Writes, under src/main/resources/assets/glock19/:
  models/item/glock_19.json       3D held model (Blockbench-compatible)
  models/item/glock_19_{frame,slide,mag}.json + items/  parts moved by the reload animation
  models/item/glock_19_icon.json  flat inventory icon
  models/item/ammo_9mm.json
  textures/item/*.png
  sounds/*.ogg                    synthesized shot / empty click / reload
  icon.png                        mod list icon

Needs numpy, Pillow and ffmpeg (with libvorbis). Run from glock19-mod/:
    python3 tools/generate_assets.py
"""

import json
import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "src/main/resources/assets/glock19"
TEXTURES = ASSETS / "textures/item"
MODELS = ASSETS / "models/item"
SOUNDS = ASSETS / "sounds"
ITEMS = ASSETS / "items"


def hex_rgba(value):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4)) + (255,)


# ---------------------------------------------------------------- textures

# Model atlas: 64x64, 4 px per model unit. Rectangles are (x0, y0, x1, y1) in pixels.
PATCHES = {
    "slide_l": (0, 0, 56, 10),      # slide left side (north face), muzzle at the left
    "slide_r": (0, 10, 56, 20),     # slide right side (south face), muzzle at the right
    "slide_top": (0, 20, 56, 26),   # u runs rear -> muzzle, v runs left -> right
    "dust_l": (0, 26, 40, 30),
    "dust_r": (0, 30, 40, 34),
    "rail": (40, 26, 60, 32),
    "slide_front": (56, 0, 64, 10),
    "slide_rear": (56, 10, 64, 20),
    "poly": (0, 36, 16, 44),
    "stipple": (16, 36, 32, 64),
    "metal": (32, 36, 40, 40),
    "dark": (32, 40, 36, 44),
    "sight_rear": (40, 36, 46, 39),
    "sight_front": (46, 36, 50, 39),
    "slide_plain": (50, 36, 58, 44),
    "mag": (32, 44, 48, 52),
    "mag_base": (48, 44, 56, 48),
    "brass": (56, 44, 60, 48),
}


def model_texture():
    rng = np.random.default_rng(19)
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    px = img.load()

    def fill(name, base, noise=0):
        x0, y0, x1, y1 = PATCHES[name]
        r, g, b, a = hex_rgba(base)
        for y in range(y0, y1):
            for x in range(x0, x1):
                n = int(rng.integers(-noise, noise + 1)) if noise else 0
                px[x, y] = (max(0, min(255, r + n)), max(0, min(255, g + n)), max(0, min(255, b + n)), a)

    def put(name, x, y, color):
        x0, y0, _, _ = PATCHES[name]
        px[x0 + x, y0 + y] = hex_rgba(color)

    def rect(name, x0, y0, x1, y1, color):
        for y in range(y0, y1):
            for x in range(x0, x1):
                put(name, x, y, color)

    # Slide sides: highlight on top, shadow at the bottom, front and rear cocking serrations.
    for side in ("slide_l", "slide_r"):
        fill(side, "#3b3e43", 3)
        rect(side, 0, 0, 56, 1, "#585c62")
        rect(side, 0, 9, 56, 10, "#2a2c30")
        rear = range(46, 55, 2) if side == "slide_l" else range(2, 11, 2)
        front = range(2, 8, 2) if side == "slide_l" else range(49, 55, 2)
        for col in rear:
            rect(side, col, 2, col + 1, 9, "#212327")
        for col in front:
            rect(side, col, 3, col + 1, 9, "#26282c")
    # Ejection port with the barrel hood showing, and the extractor behind it.
    rect("slide_r", 12, 0, 28, 6, "#17181a")
    fill_hood = [(x, y) for y in range(0, 5) for x in range(13, 27)]
    for x, y in fill_hood:
        shade = 0x70 + int(rng.integers(-5, 6)) + (8 if y == 0 else 0)
        put("slide_r", x, y, "#%02x%02x%02x" % (shade, shade + 3, shade + 7))
    rect("slide_r", 8, 3, 12, 5, "#2e3034")
    rect("slide_r", 8, 3, 12, 4, "#4a4d52")

    fill("slide_top", "#45484d", 3)
    rect("slide_top", 12, 2, 28, 6, "#17181a")
    for y in range(3, 6):
        for x in range(13, 27):
            shade = 0x76 + int(rng.integers(-5, 6))
            put("slide_top", x, y, "#%02x%02x%02x" % (shade, shade + 3, shade + 7))

    fill("slide_front", "#34373b", 2)
    for y in range(10):
        for x in range(8):
            d = ((x + 0.5 - 4) ** 2 + (y + 0.5 - 3.6) ** 2) ** 0.5
            if d < 1.7:
                put("slide_front", x, y, "#030303")
            elif d < 2.6:
                put("slide_front", x, y, "#24262a")

    fill("slide_rear", "#2f3135", 2)
    rect("slide_rear", 1, 2, 7, 9, "#232528")

    for side in ("dust_l", "dust_r"):
        fill(side, "#1f2023", 3)
        rect(side, 0, 0, 40, 1, "#2b2c30")
    fill("rail", "#1b1c1f", 2)
    for col in (4, 9, 14):
        rect("rail", col, 0, col + 2, 6, "#0f1012")

    fill("poly", "#1f2023", 3)
    x0, y0, x1, y1 = PATCHES["stipple"]
    for y in range(y0, y1):
        for x in range(x0, x1):
            roll = rng.random()
            px[x, y] = hex_rgba("#16171a" if roll < 0.3 else "#2c2d31" if roll < 0.5 else "#212226")
    fill("metal", "#5a5d63", 5)
    fill("dark", "#0b0b0c")
    fill("sight_rear", "#141414")
    rect("sight_rear", 0, 1, 1, 3, "#ececec")
    rect("sight_rear", 5, 1, 6, 3, "#ececec")
    rect("sight_rear", 1, 2, 5, 3, "#ececec")
    fill("sight_front", "#141414")
    rect("sight_front", 1, 0, 3, 2, "#f4f4f4")
    fill("slide_plain", "#3e4146", 3)
    fill("mag", "#2b2d31", 3)
    for row in (1, 3, 5):
        rect("mag", 11, row, 13, row + 1, "#0d0d0e")
    fill("mag_base", "#151517", 2)
    fill("brass", "#c9a24a", 6)
    return img


# One character per pixel; see ICON_COLORS.
GLOCK_ICON = [
    "................",
    "................",
    "................",
    ".r............f.",
    ".HHHHHHHHHHHHHHH",
    ".SsSsSSSSSSSSSSb",
    ".SsSsSSSSSSSSSSb",
    "..FFFFFFFFFFFFF.",
    "..GGGG.t.F......",
    "..GgGGFFFF......",
    ".GGgG...........",
    ".GgGG...........",
    "GGGg............",
    "GgGG............",
    "MMMM............",
    "................",
]
ICON_COLORS = {
    "r": "#e8e8e8", "f": "#e8e8e8", "H": "#6b6f75", "S": "#44474c", "s": "#2a2c30",
    "b": "#000000", "F": "#1e1f22", "G": "#2a2b2f", "g": "#1a1b1e", "t": "#5d6066",
    "M": "#101012", "c": "#c9a24a", "C": "#e9c46a", "d": "#9a7a30", "p": "#b86b3c",
    "P": "#d98a55", "k": "#5c4a1c",
}

AMMO_ICON = [
    "................",
    "................",
    "..........P.....",
    "......P..Ppp....",
    ".....Ppp.Ppp....",
    "..P..Ppp.CcCd...",
    ".Ppp.CcCdCcCd...",
    ".PppdCcCdCcCd...",
    ".CcCdCcCdCcCd...",
    ".CcCdCcCdCcCd...",
    ".CcCdCcCdCcCd...",
    ".CcCdCcCdCcCd...",
    ".CcCdCcCdkkkk...",
    ".CcCdkkkk.......",
    ".kkkk...........",
    "................",
]


def bullet_texture():
    """16x16: copper jacket, tracer core, tracer glow, tracer tail."""
    img = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    for (x0, color, light) in ((0, "#b8642f", "#e08a52"), (4, "#fffbe0", "#ffffff"), (8, "#ffd060", "#ffe9a0"),
                               (12, "#ff8a1e", "#ffb050")):
        for y in range(4):
            for x in range(x0, x0 + 4):
                img.putpixel((x, y), hex_rgba(light if y == 0 else color))
    return img


def pixel_art(rows):
    img = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch != ".":
                img.putpixel((x, y), hex_rgba(ICON_COLORS[ch]))
    return img


# ---------------------------------------------------------------- models

# Size of each face in model units: (width, height) as it appears on the texture.
FACE_SIZE = {
    "north": lambda d: (d[0], d[1]), "south": lambda d: (d[0], d[1]),
    "east": lambda d: (d[2], d[1]), "west": lambda d: (d[2], d[1]),
    "up": lambda d: (d[0], d[2]), "down": lambda d: (d[0], d[2]),
}


def face_uv(patch, face, dims):
    """Maps a face onto a patch. Patches as large as the face are sampled 1:1 from their corner."""
    x0, y0, x1, y1 = PATCHES[patch]
    w, h = FACE_SIZE[face](dims)
    u1 = x0 + min(x1 - x0, w * 4)
    v1 = y0 + min(y1 - y0, h * 4)
    return [round(x0 / 4, 3), round(y0 / 4, 3), round(u1 / 4, 3), round(v1 / 4, 3)]


def box(name, frm, to, default, rotation=None, **overrides):
    """A cuboid. The gun points east (+x), its right side faces south (+z)."""
    dims = [t - f for f, t in zip(frm, to)]
    faces = {}
    for face in ("north", "east", "south", "west", "up", "down"):
        faces[face] = {"uv": face_uv(overrides.get(face, default), face, dims), "texture": "#gun"}
    element = {"name": name, "from": frm, "to": to, "faces": faces}
    if rotation:
        element["rotation"] = rotation
    return element


# The grip and magazine rake back 22.5 degrees around the top of the grip.
GRIP_ANGLE = {"angle": -22.5, "axis": "z", "origin": [2.7, 8.4, 8]}


SLIDE = [
    box("slide_body", [1.2, 9.4, 7.0], [15.2, 11.9, 9.0], "slide_plain",
        north="slide_l", south="slide_r", east="slide_front", west="slide_rear", down="dark"),
    box("slide_top", [1.2, 11.9, 7.25], [15.2, 12.25, 8.75], "slide_plain", up="slide_top"),
    box("rear_sight", [1.3, 12.25, 7.3], [2.4, 12.85, 8.7], "poly", west="sight_rear"),
    box("front_sight", [14.3, 12.25, 7.75], [14.9, 12.8, 8.25], "poly", west="sight_front"),
]

FRAME = [
    box("dust_cover", [5.0, 8.4, 7.1], [15.0, 9.4, 8.9], "poly", north="dust_l", south="dust_r"),
    box("rail", [9.6, 8.0, 7.3], [14.7, 8.4, 8.7], "poly", down="rail"),
    box("frame_rear", [0.9, 8.4, 7.05], [5.0, 9.4, 8.95], "poly"),
    box("beavertail", [0.5, 8.7, 7.25], [1.0, 9.4, 8.75], "poly"),
    box("slide_stop", [5.3, 9.25, 6.9], [6.9, 9.5, 7.15], "metal"),
    box("takedown", [7.7, 8.95, 6.95], [8.4, 9.3, 9.05], "metal"),
    box("guard_bottom", [4.5, 6.0, 7.45], [8.7, 6.55, 8.55], "poly"),
    box("guard_front", [8.15, 6.0, 7.45], [8.7, 8.4, 8.55], "poly"),
    box("trigger", [5.65, 6.7, 7.75], [6.2, 8.4, 8.25], "metal"),
    box("grip_top", [1.2, 7.4, 7.1], [4.6, 8.4, 8.9], "poly"),
    box("grip", [1.0, 1.8, 7.1], [4.4, 8.4, 8.9], "stipple", GRIP_ANGLE, up="poly"),
    box("magwell", [0.85, 1.8, 6.95], [4.55, 2.3, 9.05], "poly", GRIP_ANGLE, down="dark"),
]

# Hidden inside the grip while seated; slides out along the grip during a reload.
MAGAZINE = [
    box("mag_base", [0.8, 1.2, 7.05], [4.6, 1.8, 8.95], "mag_base", GRIP_ANGLE),
    box("mag_body", [1.4, 1.8, 7.4], [4.0, 7.9, 8.6], "mag", GRIP_ANGLE),
    box("round", [1.9, 7.9, 7.75], [3.9, 8.25, 8.25], "brass", GRIP_ANGLE),
]

# Shared by the whole gun and by the parts the reload animation moves separately,
# so they line up exactly. Barrel along +x, grip down.
DISPLAY_MODEL = {
    "credit": "Generated by glock19-mod/tools/generate_assets.py",
    "texture_size": [64, 64],
    "textures": {"gun": "glock19:item/glock_19", "particle": "glock19:item/glock_19"},
    "display": {
        "thirdperson_righthand": {"rotation": [0, -90, 90], "translation": [0, 2, -1.6], "scale": [0.85, 0.85, 0.85]},
        "firstperson_righthand": {"rotation": [0, 90, 0], "translation": [1.5, 4.6, -1.5], "scale": [0.55, 0.55, 0.55]},
    },
}


def bullet_box(name, frm, to, uv):
    return {"name": name, "from": frm, "to": to,
            "faces": {f: {"uv": uv, "texture": "#bullet"} for f in ("north", "east", "south", "west", "up", "down")}}


# The bullet flies towards +x; the tracer streak trails behind it.
BULLET_MODEL = {
    "credit": "Generated by glock19-mod/tools/generate_assets.py",
    "textures": {"bullet": "glock19:item/bullet", "particle": "glock19:item/bullet"},
    "elements": [
        bullet_box("tail", [0, 7.7, 7.7], [4, 8.3, 8.3], [12, 0, 16, 4]),
        bullet_box("glow", [4, 7.5, 7.5], [12.4, 8.5, 8.5], [8, 0, 12, 4]),
        bullet_box("core", [9, 7.4, 7.4], [12.6, 8.6, 8.6], [4, 0, 8, 4]),
        bullet_box("jacket", [12.6, 7.55, 7.55], [14.2, 8.45, 8.45], [0, 0, 4, 4]),
        bullet_box("nose", [14.2, 7.75, 7.75], [14.8, 8.25, 8.25], [0, 0, 4, 4]),
    ],
    "display": {"ground": {"rotation": [0, 0, 0], "translation": [0, 0, 0], "scale": [1, 1, 1]}},
}


def part_model(elements):
    return {"parent": "glock19:item/glock_19_display", "elements": elements}


def flat_model(texture):
    return {"parent": "minecraft:item/generated", "textures": {"layer0": texture}}


def item_definition(model):
    return {"model": {"type": "minecraft:model", "model": model}}


# ---------------------------------------------------------------- sounds

RATE = 44100


def band(signal, lo=None, hi=None):
    spectrum = np.fft.rfft(signal)
    freqs = np.fft.rfftfreq(len(signal), 1 / RATE)
    if lo is not None:
        spectrum[freqs < lo] *= np.clip((freqs[freqs < lo] / lo) ** 2, 0, 1)
    if hi is not None:
        spectrum[freqs > hi] *= np.clip((hi / freqs[freqs > hi]) ** 2, 0, 1)
    return np.fft.irfft(spectrum, len(signal))


def env(n, tau, attack=0.0005):
    t = np.arange(n) / RATE
    rise = np.clip(t / attack, 0, 1) if attack > 0 else 1
    return rise * np.exp(-t / tau)


def place(out, sound, at):
    start = int(at * RATE)
    end = min(len(out), start + len(sound))
    out[start:end] += sound[:end - start]


def click(rng, length=0.03, tau=0.003, lo=1500, hi=9000, ring=None, gain=1.0):
    n = int(length * RATE)
    s = band(rng.standard_normal(n), lo, hi) * env(n, tau, 0.0002)
    if ring:
        t = np.arange(n) / RATE
        s += 0.35 * np.sin(2 * np.pi * ring * t) * env(n, tau * 4, 0.0002)
    return gain * s / (np.max(np.abs(s)) + 1e-9)


def shot(seed):
    rng = np.random.default_rng(seed)
    n = int(0.9 * RATE)
    t = np.arange(n) / RATE
    out = np.zeros(n)
    crack = band(rng.standard_normal(n), 1800, None) * env(n, 0.006, 0.0001)
    body = band(rng.standard_normal(n), 120, 2500) * env(n, 0.045, 0.0003)
    sweep = 110 * np.exp(-t / 0.05) + 55
    thump = np.sin(2 * np.pi * np.cumsum(sweep) / RATE) * env(n, 0.05, 0.0005)
    tail = band(rng.standard_normal(n), 80, 900) * env(n, 0.22, 0.01)
    out += 1.0 * crack + 0.9 * body + 0.8 * thump + 0.25 * tail
    place(out, click(rng, ring=2600, gain=0.18), 0.032)  # slide cycling
    out = np.tanh(out * 2.2)
    return out


def modal(rng, modes, length=0.3, gain=1.0, strike_tau=0.0006):
    """A struck object: a short noise strike exciting damped resonances.

    `modes` is a list of (frequency Hz, decay seconds, amplitude). Frequencies are jittered a little
    per call so repeated hits don't sound identical.
    """
    n = int(length * RATE)
    t = np.arange(n) / RATE
    out = np.zeros(n)
    for freq, decay, amp in modes:
        f = freq * (1.0 + rng.normal(0, 0.012))
        out += amp * np.sin(2 * np.pi * f * t + rng.uniform(0, 2 * np.pi)) * np.exp(-t / decay)
    out *= np.clip(t / 0.0004, 0, 1)
    strike = band(rng.standard_normal(n), 1500, 14000) * env(n, strike_tau, 0.0001)
    out += 0.6 * strike / (np.max(np.abs(strike)) + 1e-9)
    return gain * out / (np.max(np.abs(out)) + 1e-9)


# Resonances (Hz, decay s, amplitude) for the parts involved.
POLYMER_CLICK = [(1850, 0.010, 1.0), (3150, 0.008, 0.7), (4700, 0.006, 0.5)]
SMALL_STEEL = [(2950, 0.045, 1.0), (4480, 0.035, 0.6), (6350, 0.025, 0.45), (8150, 0.018, 0.3)]
MAG_BODY = [(880, 0.030, 1.0), (1720, 0.028, 0.7), (2640, 0.022, 0.5), (3910, 0.016, 0.35)]
POLYMER_BODY = [(240, 0.030, 1.0), (410, 0.022, 0.6), (730, 0.016, 0.4)]
SLIDE_STEEL = [(640, 0.090, 0.8), (1460, 0.070, 1.0), (2370, 0.060, 0.7), (3820, 0.045, 0.55), (5230, 0.030, 0.4)]
BARREL_LOCK = [(1120, 0.050, 1.0), (2860, 0.040, 0.6), (4400, 0.030, 0.4)]


def friction(rng, length, lo, hi, gain=0.3, sweep=0.0, grain_rate=140):
    """Sliding contact: band-limited noise broken into stick-slip grains. `sweep` raises the band over time."""
    n = int(length * RATE)
    t = np.linspace(0, 1, n)
    noise = rng.standard_normal(n)
    # Split into two bands and crossfade to approximate a sweeping band-pass.
    low = band(noise, lo, hi)
    high = band(noise, lo * (1 + sweep), hi * (1 + sweep))
    texture = low * (1 - t * min(sweep, 1)) + high * t * min(sweep, 1)
    grains = np.zeros(n)
    count = max(1, int(grain_rate * length))
    for pos in rng.integers(0, n, count):
        width = int(rng.uniform(0.002, 0.006) * RATE)
        end = min(n, pos + width)
        grains[pos:end] += np.hanning(width)[:end - pos] * rng.uniform(0.4, 1.0)
    shape = np.sin(np.pi * t) ** 0.6
    out = texture * (0.35 + grains) * shape
    return gain * out / (np.max(np.abs(out)) + 1e-9)


def handling(rng, length, gain=0.08):
    """Low hand/grip rustle under the mechanical sounds."""
    n = int(length * RATE)
    t = np.linspace(0, 1, n)
    rustle = band(rng.standard_normal(n), 150, 1200) * np.sin(np.pi * t) ** 1.5
    return gain * rustle / (np.max(np.abs(rustle)) + 1e-9)


def room(signal, rng, rt60=0.32, mix=0.16):
    """Small-room reverb from a synthetic exponentially decaying impulse response."""
    n = int(rt60 * 1.2 * RATE)
    t = np.arange(n) / RATE
    ir = band(rng.standard_normal(n), 200, 6000) * np.exp(-6.9 * t / rt60)
    ir[: int(0.004 * RATE)] = 0  # pre-delay
    ir /= np.sqrt(np.sum(ir ** 2)) + 1e-9
    wet = np.convolve(signal, ir)[: len(signal)]
    wet /= np.max(np.abs(wet)) + 1e-9
    dry = signal / (np.max(np.abs(signal)) + 1e-9)
    return (1 - mix) * dry + mix * wet


def empty():
    rng = np.random.default_rng(7)
    out = np.zeros(int(0.3 * RATE))
    place(out, modal(rng, POLYMER_CLICK, 0.05, 0.5), 0.0)  # trigger travel
    place(out, modal(rng, SMALL_STEEL, 0.12, 1.0), 0.012)  # striker falls on nothing
    place(out, modal(rng, POLYMER_CLICK, 0.04, 0.25), 0.075)  # trigger reset
    return room(out, rng, rt60=0.22, mix=0.12)


def reload():
    """Mag release, mag out, new mag in and seated, slide racked and released (1.55 s).

    Timed to the first-person animation in GunAnimator (32 ticks).
    """
    rng = np.random.default_rng(11)
    out = np.zeros(int(1.55 * RATE))
    place(out, handling(rng, 0.25), 0.0)
    place(out, modal(rng, POLYMER_CLICK, 0.05, 0.55), 0.035)  # release button
    place(out, modal(rng, SMALL_STEEL, 0.10, 0.25), 0.045)  # catch lets go
    place(out, friction(rng, 0.17, 900, 4500, 0.32, grain_rate=90), 0.06)  # mag slides out
    place(out, modal(rng, MAG_BODY, 0.12, 0.22), 0.22)  # mag clears the well
    place(out, handling(rng, 0.3, 0.07), 0.3)
    place(out, friction(rng, 0.17, 700, 3800, 0.36, sweep=0.4, grain_rate=110), 0.47)  # new mag in
    place(out, modal(rng, POLYMER_BODY, 0.12, 0.75), 0.665)  # seats in the grip
    place(out, modal(rng, MAG_BODY, 0.18, 0.7), 0.668)
    place(out, modal(rng, SMALL_STEEL, 0.10, 0.45), 0.684)  # catch engages
    place(out, handling(rng, 0.25, 0.06), 0.85)
    place(out, friction(rng, 0.15, 1400, 6500, 0.4, sweep=0.6, grain_rate=200), 0.99)  # slide back, spring loading
    place(out, modal(rng, SLIDE_STEEL, 0.15, 0.4), 1.14)  # slide hits the rear stop
    place(out, modal(rng, SLIDE_STEEL, 0.35, 1.0, strike_tau=0.0004), 1.19)  # slide slams home
    place(out, modal(rng, BARREL_LOCK, 0.25, 0.65), 1.198)  # barrel locks up
    place(out, modal(rng, SMALL_STEEL, 0.12, 0.3), 1.215)  # rattle
    out = room(out, rng)
    return np.tanh(out * 1.6)


def impact(seed):
    """Bullet hitting a block: sharp crack, a dull thud and some debris."""
    rng = np.random.default_rng(seed)
    n = int(0.35 * RATE)
    out = np.zeros(n)
    crack = band(rng.standard_normal(n), 2500, 12000) * env(n, 0.004, 0.0001)
    thud = band(rng.standard_normal(n), 80, 900) * env(n, 0.03, 0.0005)
    out += 0.9 * crack / (np.max(np.abs(crack)) + 1e-9) + 0.8 * thud / (np.max(np.abs(thud)) + 1e-9)
    for _ in range(5):  # debris
        place(out, click(rng, length=0.02, tau=0.002, lo=2000, hi=8000, gain=rng.uniform(0.08, 0.2)), rng.uniform(0.02, 0.18))
    return room(np.tanh(out * 1.5), rng, rt60=0.25, mix=0.15)


def write_ogg(name, samples):
    samples = samples / (np.max(np.abs(samples)) + 1e-9) * 0.89
    pcm = (samples * 32767).astype(np.int16)
    with tempfile.TemporaryDirectory() as tmp:
        wav_path = Path(tmp) / "s.wav"
        with wave.open(str(wav_path), "wb") as w:
            w.setnchannels(1)  # mono, so Minecraft positions it in 3D
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(pcm.tobytes())
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(wav_path), "-c:a", "libvorbis", "-q:a", "6",
                        str(SOUNDS / f"{name}.ogg")], check=True)


# ---------------------------------------------------------------- main

def write_json(path, data):
    path.write_text(json.dumps(data, indent="\t") + "\n")


def main():
    for d in (TEXTURES, MODELS, SOUNDS, ITEMS):
        d.mkdir(parents=True, exist_ok=True)

    model_texture().save(TEXTURES / "glock_19.png")
    icon = pixel_art(GLOCK_ICON)
    icon.save(TEXTURES / "glock_19_icon.png")
    pixel_art(AMMO_ICON).save(TEXTURES / "ammo_9mm.png")
    icon.resize((128, 128), Image.NEAREST).save(ASSETS / "icon.png")

    write_json(MODELS / "glock_19_display.json", DISPLAY_MODEL)
    write_json(MODELS / "glock_19.json", part_model(SLIDE + FRAME + MAGAZINE))
    for part, elements in (("frame", FRAME), ("slide", SLIDE), ("mag", MAGAZINE)):
        write_json(MODELS / f"glock_19_{part}.json", part_model(elements))
        write_json(ITEMS / f"glock_19_{part}.json", item_definition(f"glock19:item/glock_19_{part}"))
    bullet_texture().save(TEXTURES / "bullet.png")
    write_json(MODELS / "bullet.json", BULLET_MODEL)
    write_json(ITEMS / "bullet.json", item_definition("glock19:item/bullet"))
    write_json(MODELS / "glock_19_icon.json", flat_model("glock19:item/glock_19_icon"))
    write_json(MODELS / "ammo_9mm.json", flat_model("glock19:item/ammo_9mm"))

    for i, seed in enumerate((191, 192, 193), start=1):
        write_ogg(f"glock_shot_{i}", shot(seed))
    write_ogg("glock_empty", empty())
    write_ogg("glock_reload", reload())
    for i, seed in enumerate((31, 32), start=1):
        write_ogg(f"bullet_impact_{i}", impact(seed))


if __name__ == "__main__":
    main()
