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
        "firstperson_righthand": {"rotation": [0, 90, 0], "translation": [2.5, 2.2, -1.5], "scale": [0.55, 0.55, 0.55]},
    },
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


def scrape(rng, length, lo=800, hi=5000, gain=0.25):
    n = int(length * RATE)
    t = np.linspace(0, 1, n)
    grain = band(rng.standard_normal(n), lo, hi) * (0.6 + 0.4 * np.sin(2 * np.pi * 90 * t * length))
    shape = np.sin(np.pi * t) ** 0.7
    return gain * grain * shape / (np.max(np.abs(grain)) + 1e-9)


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


def empty():
    rng = np.random.default_rng(7)
    out = np.zeros(int(0.25 * RATE))
    place(out, click(rng, ring=3200, gain=0.9), 0.0)
    place(out, click(rng, tau=0.002, ring=4100, gain=0.35), 0.06)
    return out


def reload():
    rng = np.random.default_rng(11)
    out = np.zeros(int(1.55 * RATE))
    place(out, click(rng, ring=2400, gain=0.5), 0.04)  # mag release
    place(out, scrape(rng, 0.16), 0.08)  # mag out
    place(out, scrape(rng, 0.12, gain=0.3), 0.55)  # mag in
    place(out, click(rng, length=0.06, tau=0.006, lo=400, hi=7000, ring=1800, gain=1.0), 0.68)  # seat
    place(out, scrape(rng, 0.14, lo=1200, gain=0.35), 1.0)  # slide back
    place(out, click(rng, length=0.08, tau=0.008, lo=300, hi=8000, ring=2900, gain=1.0), 1.2)  # slide snap
    place(out, click(rng, tau=0.002, ring=3600, gain=0.3), 1.23)
    return out


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
    write_json(MODELS / "glock_19_icon.json", flat_model("glock19:item/glock_19_icon"))
    write_json(MODELS / "ammo_9mm.json", flat_model("glock19:item/ammo_9mm"))

    for i, seed in enumerate((191, 192, 193), start=1):
        write_ogg(f"glock_shot_{i}", shot(seed))
    write_ogg("glock_empty", empty())
    write_ogg("glock_reload", reload())


if __name__ == "__main__":
    main()
