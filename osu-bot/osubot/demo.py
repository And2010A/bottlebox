"""A generated demo beatmap, so the program can be tried without any maps."""

import math


def demo_osu(bpm=170, od=8, ar=9.3, cs=4, hp=5):
    beat = 60000 / bpm
    lines = []
    t = 2000.0

    def add_circle(x, y, nc=False):
        lines.append(f"{int(x)},{int(y)},{int(t)},{5 if nc else 1},0,0:0:0:0:")

    def add_slider(x, y, desc, slides, length, nc=False):
        lines.append(f"{int(x)},{int(y)},{int(t)},{6 if nc else 2},0,{desc},{slides},{length}")

    # 1) star jumps on 1/2
    for k in range(16):
        a = k * 2 * math.pi * 2 / 5
        add_circle(256 + 170 * math.cos(a), 192 + 150 * math.sin(a), nc=(k % 4 == 0))
        t += beat / 2
    t += beat
    # 2) sliders: bezier, perfect circle, linear, with repeats
    sl = [
        (100, 100, "B|180:40|260:120|340:60", 1, 280),
        (420, 280, "P|360:340|280:300", 1, 170),
        (80, 300, "L|240:300", 2, 160),
        (300, 80, "B|380:120|380:120|440:200", 1, 200),
    ]
    for x, y, d, s, ln in sl:
        add_slider(x, y, d, s, ln, nc=True)
        t += beat * (ln / (100 * 1.8)) * s + beat
    # 3) a stream (1/4) spiralling
    for k in range(32):
        a = k * 0.35
        add_circle(256 + (40 + 3 * k) * math.cos(a), 192 + (40 + 2.5 * k) * math.sin(a),
                   nc=(k % 8 == 0))
        t += beat / 4
    t += beat
    # 4) spinner
    lines.append(f"256,192,{int(t)},12,0,{int(t + beat * 8)}")
    t += beat * 9
    # 5) wide back-and-forth jumps
    for k in range(16):
        x = 60 if k % 2 == 0 else 452
        y = 80 + (k * 37) % 230
        add_circle(x, y, nc=(k % 4 == 0))
        t += beat / 2
    t += beat
    # 6) stacked triples
    for k in range(6):
        x, y = 140 + 45 * k, 150 + 30 * (k % 2)
        for _ in range(3):
            add_circle(x, y, nc=(_ == 0 and k % 2 == 0))
            t += beat / 4
        t += beat / 4

    return f"""osu file format v14

[General]
AudioFilename: none.mp3
AudioLeadIn: 0
Mode: 0
StackLeniency: 0.7

[Metadata]
Title:Claude Bot Demo
TitleUnicode:Claude Bot Demo
Artist:Generator
ArtistUnicode:Generator
Creator:Claude
Version:Demo {bpm}bpm

[Difficulty]
HPDrainRate:{hp}
CircleSize:{cs}
OverallDifficulty:{od}
ApproachRate:{ar}
SliderMultiplier:1.8
SliderTickRate:2

[Events]

[TimingPoints]
0,{beat},4,2,0,60,1,0

[Colours]
Combo1 : 255,128,192
Combo2 : 120,200,255
Combo3 : 255,220,100

[HitObjects]
""" + "\n".join(lines) + "\n"
