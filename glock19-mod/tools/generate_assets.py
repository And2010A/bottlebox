"""Generates the Glock 19 mod's art and audio.

Writes, under src/main/resources/assets/glock19/:
  models/item/glock_19.json       3D held model (Blockbench-compatible)
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


def hex_rgba(value):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4)) + (255,)


# ---------------------------------------------------------------- textures

def model_texture():
    """32x32 atlas of 8x8 material patches; the model's faces map onto these."""
    rng = np.random.default_rng(19)
    img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    px = img.load()

    def patch(col, row, fn):
        for y in range(8):
            for x in range(8):
                px[col * 8 + x, row * 8 + y] = fn(x, y)

    def noisy(base, amount=6):
        r, g, b, a = hex_rgba(base)

        def fn(x, y):
            n = int(rng.integers(-amount, amount + 1))
            return (max(0, min(255, r + n)), max(0, min(255, g + n)), max(0, min(255, b + n)), a)
        return fn

    slide = noisy("#3d4045", 4)
    patch(0, 0, lambda x, y: hex_rgba("#5a5e64") if y == 0 else hex_rgba("#2c2e32") if y == 7 else slide(x, y))
    patch(1, 0, lambda x, y: hex_rgba("#26282c") if x % 2 == 0 else hex_rgba("#4a4d52"))
    patch(2, 0, noisy("#45484d", 4))
    patch(3, 0, noisy("#1f2023", 3))

    def stipple(x, y):
        roll = rng.random()
        if roll < 0.25:
            return hex_rgba("#17181a")
        if roll < 0.45:
            return hex_rgba("#2f3034")
        return hex_rgba("#232427")
    patch(0, 1, stipple)
    patch(1, 1, lambda x, y: hex_rgba("#050505") if 1 <= x <= 6 and 1 <= y <= 6 else hex_rgba("#3d4045"))
    patch(2, 1, lambda x, y: hex_rgba("#f0f0f0") if 3 <= x <= 4 and 3 <= y <= 4 else hex_rgba("#1f2023"))
    patch(3, 1, noisy("#5d6066", 5))
    patch(0, 2, noisy("#141416", 2))
    patch(1, 2, lambda x, y: hex_rgba("#5b5e63") if x in (0, 7) or y in (0, 7) else noisy("#7d8086", 5)(x, y))
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

# UV rectangles (0-16 space) of the atlas patches in model_texture().
SLIDE, SERRATIONS, SLIDE_TOP, FRAME = [0, 0, 4, 4], [4, 0, 8, 4], [8, 0, 12, 4], [12, 0, 16, 4]
GRIP, BORE, SIGHT, METAL = [0, 4, 4, 8], [4, 4, 8, 8], [8, 4, 12, 8], [12, 4, 16, 8]
MAG_BASE, HOOD = [0, 8, 4, 12], [4, 8, 8, 12]


def box(name, frm, to, default, **overrides):
    """A cuboid. The gun points east (+x); `overrides` sets single faces."""
    faces = {}
    for face in ("north", "east", "south", "west", "up", "down"):
        faces[face] = {"uv": overrides.get(face, default), "texture": "#gun"}
    return {"name": name, "from": frm, "to": to, "faces": faces}


def glock_model():
    elements = [
        box("slide_rear", [0.5, 9.5, 7], [4, 12.5, 9], SLIDE, north=SERRATIONS, south=SERRATIONS, up=SLIDE_TOP),
        box("slide_front", [4, 9.5, 7], [15.5, 12.5, 9], SLIDE, up=SLIDE_TOP),
        box("barrel_hood", [5.5, 12.5, 7.4], [8.5, 12.6, 8.8], HOOD),
        box("bore", [15.5, 10.4, 7.5], [15.6, 11.6, 8.5], SLIDE, east=BORE),
        box("front_sight", [14.2, 12.5, 7.7], [15, 13.1, 8.3], FRAME, west=SIGHT),
        box("rear_sight", [1, 12.5, 7.3], [2.2, 13.1, 8.7], FRAME, west=SIGHT),
        box("dust_cover", [4.5, 8.5, 7.2], [15.2, 9.5, 8.8], FRAME),
        box("frame_rear", [0.8, 8.5, 7.2], [4.5, 9.5, 8.8], FRAME),
        box("grip_1", [1.0, 6.5, 7.1], [4.6, 8.5, 8.9], GRIP, up=FRAME),
        box("grip_2", [0.6, 4.5, 7.1], [4.1, 6.5, 8.9], GRIP),
        box("grip_3", [0.2, 2.5, 7.1], [3.7, 4.5, 8.9], GRIP),
        box("grip_4", [-0.2, 1.0, 7.1], [3.3, 2.5, 8.9], GRIP),
        box("mag_base", [-0.4, 0.4, 7.0], [3.4, 1.0, 9.0], MAG_BASE),
        box("guard_bottom", [4.6, 6.3, 7.5], [8.2, 6.9, 8.5], FRAME),
        box("guard_front", [7.6, 6.3, 7.5], [8.2, 8.5, 8.5], FRAME),
        box("trigger", [5.6, 6.9, 7.8], [6.1, 8.5, 8.2], METAL),
    ]
    return {
        "credit": "Generated by glock19-mod/tools/generate_assets.py",
        "texture_size": [32, 32],
        "textures": {"gun": "glock19:item/glock_19", "particle": "glock19:item/glock_19"},
        "elements": elements,
        # Barrel along +x, grip down. Derived from vanilla's handheld transforms;
        # fine-tune in Blockbench's Display tab if the hold looks off.
        "display": {
            "thirdperson_righthand": {"rotation": [0, -90, 90], "translation": [0, 2, -1.6], "scale": [0.85, 0.85, 0.85]},
            "thirdperson_lefthand": {"rotation": [0, 90, -90], "translation": [0, 2, -1.6], "scale": [0.85, 0.85, 0.85]},
            "firstperson_righthand": {"rotation": [0, -90, 0], "translation": [1.13, 0.5, 3.2], "scale": [0.68, 0.68, 0.68]},
            "firstperson_lefthand": {"rotation": [0, 90, 0], "translation": [1.13, 0.5, 3.2], "scale": [0.68, 0.68, 0.68]},
            "head": {"rotation": [0, 180, 0], "translation": [0, 13, 7]},
        },
    }


def flat_model(texture):
    return {"parent": "minecraft:item/generated", "textures": {"layer0": texture}}


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
    for d in (TEXTURES, MODELS, SOUNDS):
        d.mkdir(parents=True, exist_ok=True)

    model_texture().save(TEXTURES / "glock_19.png")
    icon = pixel_art(GLOCK_ICON)
    icon.save(TEXTURES / "glock_19_icon.png")
    pixel_art(AMMO_ICON).save(TEXTURES / "ammo_9mm.png")
    icon.resize((128, 128), Image.NEAREST).save(ASSETS / "icon.png")

    write_json(MODELS / "glock_19.json", glock_model())
    write_json(MODELS / "glock_19_icon.json", flat_model("glock19:item/glock_19_icon"))
    write_json(MODELS / "ammo_9mm.json", flat_model("glock19:item/ammo_9mm"))

    for i, seed in enumerate((191, 192, 193), start=1):
        write_ogg(f"glock_shot_{i}", shot(seed))
    write_ogg("glock_empty", empty())
    write_ogg("glock_reload", reload())


if __name__ == "__main__":
    main()
