import io
import math
import os
import sys
import wave
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from osubot.beatmap import Beatmap, BeatmapError, SliderPath, list_difficulties
from osubot.demo import demo_osu
from osubot.sim import GRADES, Play, grade_of

OLD_FORMAT = """osu file format v5

[General]
AudioFilename: song.wav

[Metadata]
Title:Old
Artist:Someone
Version:Insane

[Difficulty]
HPDrainRate:6
CircleSize:5
OverallDifficulty:7
SliderMultiplier:1.6
SliderTickRate:1

[TimingPoints]
1000,400,4,1,0,100
3000,-50,4,1,0,100

[HitObjects]
100,100,1000,1,0
200,100,1400,1,0
300,300,1800,2,0,C|350:250|400:300|450:250,1,180
300,300,3000,2,0,B|400:300,3,100
256,192,5000,12,0,7000
50,50,7500,5,0
"""


def test_all_grade_targets_are_met():
    for mods in ((), ("HR",), ("DT",), ("EZ",)):
        bm = Beatmap(demo_osu(), mods)
        for g in GRADES:
            for seed in range(5):
                p = Play(bm, "grade", g, seed=seed)
                assert p.grade == g, (mods, g, seed, p.final.counts)


def test_nofail_prevents_fail_in_skill_mode():
    bm = Beatmap(demo_osu(), ("NF",))
    p = Play(bm, "skill", skill=1, seed=3)
    assert not p.failed


def test_skill_is_monotonic_on_average():
    bm = Beatmap(demo_osu(), ())
    accs = []
    for s in (2, 5, 8, 10):
        accs.append(sum(Play(bm, "skill", skill=s, seed=k).accuracy for k in range(8)) / 8)
    assert accs == sorted(accs)
    assert accs[-1] > 0.98


def test_old_format_and_curves():
    bm = Beatmap(OLD_FORMAT)
    assert bm.ar == bm.od == 7
    kinds = [o.kind for o in bm.objects]
    assert kinds == ["circle", "circle", "slider", "slider", "spinner", "circle"]
    s = bm.objects[3]
    # sv 2x via inherited point: 100px at 1.6*100*2/400 px/ms
    assert s.span_duration == pytest.approx(100 / (1.6 * 100 * 2 / 400))
    assert [p.kind for p in s.parts].count("repeat") == 2
    assert abs(bm.objects[2].path.length - 180) < 1e-6
    Play(bm, "grade", "SS", seed=1)


def test_perfect_circle_arc_length():
    path = SliderPath("P", [(0, 0), (100, 100), (200, 0)], 0)
    assert path.length == pytest.approx(math.pi * 100, rel=0.01)


def test_grade_rules():
    assert grade_of(100, 0, 0, 0) == "SS"
    assert grade_of(95, 5, 0, 0) == "S"
    assert grade_of(95, 4, 0, 1) == "A"
    assert grade_of(85, 15, 0, 0) == "A"
    assert grade_of(75, 25, 0, 0) == "B"
    assert grade_of(65, 30, 0, 5) == "C"
    assert grade_of(10, 10, 10, 70) == "D"
    assert grade_of(100, 0, 0, 0, failed=True) == "F"


def test_osz_loading(tmp_path):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(b"\0\0" * 22050)
    osz = tmp_path / "map.osz"
    with zipfile.ZipFile(osz, "w") as z:
        z.writestr("old.osu", OLD_FORMAT)
        z.writestr("demo.osu", demo_osu().replace("none.mp3", "SONG.wav"))
        z.writestr("song.wav", buf.getvalue())
    entries = list_difficulties(str(osz))
    assert len(entries) == 2
    for info, src, text in entries:
        bm = Beatmap(text, (), src)
        assert bm.audio_bytes()  # case-insensitive lookup


def test_rejects_other_modes():
    with pytest.raises(BeatmapError):
        Beatmap(demo_osu().replace("Mode: 0", "Mode: 3"))


def test_catch_grade_targets_and_conversion():
    from osubot.catch import GRADES as CATCH_GRADES, CatchPlay
    for text in (demo_osu(), demo_osu().replace("Mode: 0", "Mode: 2")):
        bm = Beatmap(text)
        for g in CATCH_GRADES:
            p = CatchPlay(bm, "grade", g, seed=4)
            assert p.grade == g, (g, p.final.counts)
        kinds = {o.kind for o in p.objects}
        assert {"fruit", "droplet", "tiny", "banana"} <= kinds
        assert any(o.hyper for o in p.objects)


def test_catch_skill_scales():
    from osubot.catch import CatchPlay
    bm = Beatmap(demo_osu())
    low = sum(CatchPlay(bm, "skill", skill=2, seed=k).accuracy for k in range(4))
    high = sum(CatchPlay(bm, "skill", skill=10, seed=k).accuracy for k in range(4))
    assert low < high


def test_taiko_mania_rejected_with_message():
    with pytest.raises(BeatmapError, match="taiko"):
        Beatmap(demo_osu().replace("Mode: 0", "Mode: 1"))
