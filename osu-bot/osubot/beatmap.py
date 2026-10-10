"""Parsing of osu!standard beatmaps (.osu / .osz) and slider geometry."""

import bisect
import io
import math
import os
import zipfile

PLAYFIELD_W = 512
PLAYFIELD_H = 384

DEFAULT_COLOURS = [(255, 192, 0), (0, 202, 0), (18, 124, 255), (242, 24, 57)]

MOD_RATE = {"DT": 1.5, "HT": 0.75}
MOD_SCORE = {"EZ": 0.5, "HT": 0.3, "HR": 1.06, "DT": 1.12, "NF": 0.5}


class BeatmapError(Exception):
    pass


def difficulty_range(d, lo, mid, hi):
    if d > 5:
        return mid + (hi - mid) * (d - 5) / 5
    if d < 5:
        return mid - (mid - lo) * (5 - d) / 5
    return mid


# --------------------------------------------------------------------------
# Sources: a beatmap folder or an .osz archive
# --------------------------------------------------------------------------

class FolderSource:
    def __init__(self, folder):
        self.folder = folder
        try:
            self._names = {n.lower(): n for n in os.listdir(folder)}
        except OSError:
            self._names = {}

    def read(self, name):
        if not name:
            return None
        name = name.replace("\\", "/")
        path = os.path.join(self.folder, name)
        if not os.path.isfile(path):
            real = self._names.get(name.lower())
            if real is None:
                return None
            path = os.path.join(self.folder, real)
        try:
            with open(path, "rb") as f:
                return f.read()
        except OSError:
            return None


class ZipSource:
    def __init__(self, path):
        self.zip = zipfile.ZipFile(path)
        self._names = {n.lower(): n for n in self.zip.namelist()}

    def read(self, name):
        if not name:
            return None
        real = self._names.get(name.replace("\\", "/").lower())
        if real is None:
            return None
        return self.zip.read(real)

    def osu_members(self):
        return [n for n in self.zip.namelist() if n.lower().endswith(".osu")]


def decode_text(data):
    return data.decode("utf-8-sig", errors="replace")


def list_difficulties(path):
    """Return [(BeatmapInfo, source, text)] for an .osu or .osz file."""
    low = path.lower()
    if low.endswith(".osz") or low.endswith(".zip"):
        try:
            src = ZipSource(path)
        except zipfile.BadZipFile:
            raise BeatmapError("Файл .osz пошкоджений")
        entries = []
        for member in src.osu_members():
            text = decode_text(src.zip.read(member))
            entries.append((parse_info(text), src, text))
        if not entries:
            raise BeatmapError("В архіві немає жодного .osu файлу")
    elif low.endswith(".osu"):
        with open(path, "rb") as f:
            text = decode_text(f.read())
        src = FolderSource(os.path.dirname(os.path.abspath(path)))
        entries = [(parse_info(text), src, text)]
    else:
        raise BeatmapError("Підтримуються лише файли .osu та .osz")
    entries.sort(key=lambda e: (e[0].mode != 0, e[0].od, e[0].ar, e[0].version))
    return entries


# --------------------------------------------------------------------------
# Raw parsing
# --------------------------------------------------------------------------

def split_sections(text):
    sections = {}
    current = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("//"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1]
            sections.setdefault(current, [])
            continue
        if current is not None:
            sections[current].append(line)
    return sections


def key_values(lines):
    out = {}
    for line in lines:
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def fnum(value, default=0.0):
    try:
        v = float(value)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except (TypeError, ValueError):
        return default


class BeatmapInfo:
    def __init__(self, text):
        s = split_sections(text)
        g = key_values(s.get("General", []))
        m = key_values(s.get("Metadata", []))
        d = key_values(s.get("Difficulty", []))
        self.mode = int(fnum(g.get("Mode"), 0))
        self.audio = g.get("AudioFilename", "")
        self.audio_lead_in = fnum(g.get("AudioLeadIn"), 0)
        self.stack_leniency = fnum(g.get("StackLeniency"), 0.7)
        self.title = m.get("TitleUnicode") or m.get("Title", "Без назви")
        self.artist = m.get("ArtistUnicode") or m.get("Artist", "")
        self.creator = m.get("Creator", "")
        self.version = m.get("Version", "")
        self.hp = fnum(d.get("HPDrainRate"), 5)
        self.cs = fnum(d.get("CircleSize"), 5)
        self.od = fnum(d.get("OverallDifficulty"), 5)
        self.ar = fnum(d.get("ApproachRate"), self.od)
        self.slider_multiplier = fnum(d.get("SliderMultiplier"), 1.4) or 1.4
        self.slider_tick_rate = fnum(d.get("SliderTickRate"), 1)
        self.sections = s
        self.background = None
        for line in s.get("Events", []):
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 3 and parts[0] == "0":
                self.background = parts[2].strip('"')
                break

    @property
    def label(self):
        return f"{self.artist} - {self.title} [{self.version}]"


def parse_info(text):
    return BeatmapInfo(text)


# --------------------------------------------------------------------------
# Curves
# --------------------------------------------------------------------------

def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _polyline_length(pts):
    return sum(_dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def bezier(ctrl):
    n = len(ctrl)
    if n <= 2:
        return list(ctrl)
    steps = int(max(8, min(_polyline_length(ctrl) / 2.5, 400)))
    out = []
    for i in range(steps + 1):
        t = i / steps
        pts = list(ctrl)
        for k in range(n - 1, 0, -1):
            pts = [(pts[j][0] + (pts[j + 1][0] - pts[j][0]) * t,
                    pts[j][1] + (pts[j + 1][1] - pts[j][1]) * t) for j in range(k)]
        out.append(pts[0])
    return out


def perfect_circle(a, b, c):
    d = 2 * (a[0] * (b[1] - c[1]) + b[0] * (c[1] - a[1]) + c[0] * (a[1] - b[1]))
    if abs(d) < 1e-3:
        return None
    a2 = a[0] ** 2 + a[1] ** 2
    b2 = b[0] ** 2 + b[1] ** 2
    c2 = c[0] ** 2 + c[1] ** 2
    ux = (a2 * (b[1] - c[1]) + b2 * (c[1] - a[1]) + c2 * (a[1] - b[1])) / d
    uy = (a2 * (c[0] - b[0]) + b2 * (a[0] - c[0]) + c2 * (b[0] - a[0])) / d
    r = math.hypot(a[0] - ux, a[1] - uy)
    if r > 10000:
        return None
    t_start = math.atan2(a[1] - uy, a[0] - ux)
    t_end = math.atan2(c[1] - uy, c[0] - ux)
    while t_end < t_start:
        t_end += 2 * math.pi
    direction = 1
    t_range = t_end - t_start
    ortho = (c[1] - a[1], -(c[0] - a[0]))
    if ortho[0] * (b[0] - a[0]) + ortho[1] * (b[1] - a[1]) < 0:
        direction = -1
        t_range = 2 * math.pi - t_range
    n = int(max(2, min(math.ceil(t_range * r / 2), 1000)))
    return [(ux + r * math.cos(t_start + direction * i / (n - 1) * t_range),
             uy + r * math.sin(t_start + direction * i / (n - 1) * t_range))
            for i in range(n)]


def catmull(pts):
    out = []
    for i in range(len(pts) - 1):
        v1 = pts[i - 1] if i > 0 else pts[i]
        v2 = pts[i]
        v3 = pts[i + 1]
        v4 = pts[i + 2] if i + 2 < len(pts) else (2 * v3[0] - v2[0], 2 * v3[1] - v2[1])
        for c in range(50):
            t = c / 50
            t2, t3 = t * t, t * t * t
            out.append(tuple(
                0.5 * (2 * v2[k] + (-v1[k] + v3[k]) * t
                       + (2 * v1[k] - 5 * v2[k] + 4 * v3[k] - v4[k]) * t2
                       + (-v1[k] + 3 * v2[k] - 3 * v3[k] + v4[k]) * t3)
                for k in range(2)))
    out.append(pts[-1])
    return out


class SliderPath:
    def __init__(self, curve_type, ctrl, expected_length):
        pts = self._compute(curve_type, ctrl)
        dedup = [pts[0]]
        for p in pts[1:]:
            if _dist(p, dedup[-1]) > 1e-4:
                dedup.append(p)
        pts = dedup
        cum = [0.0]
        for i in range(1, len(pts)):
            cum.append(cum[-1] + _dist(pts[i - 1], pts[i]))
        length = expected_length if expected_length and expected_length > 0 else cum[-1]
        if len(pts) == 1:
            pts.append((pts[0][0] + 1e-3, pts[0][1]))
            cum.append(1e-3)
        if cum[-1] > length:
            # truncate
            i = bisect.bisect_left(cum, length)
            seg = cum[i] - cum[i - 1]
            f = (length - cum[i - 1]) / seg if seg > 0 else 0
            p0, p1 = pts[i - 1], pts[i]
            pts = pts[:i] + [(p0[0] + (p1[0] - p0[0]) * f, p0[1] + (p1[1] - p0[1]) * f)]
            cum = cum[:i] + [length]
        elif cum[-1] < length:
            # extend the last segment linearly
            p0, p1 = pts[-2], pts[-1]
            seg = _dist(p0, p1)
            extra = length - cum[-1]
            if seg > 0:
                pts.append((p1[0] + (p1[0] - p0[0]) / seg * extra,
                            p1[1] + (p1[1] - p0[1]) / seg * extra))
                cum.append(length)
        self.points = pts
        self.cum = cum
        self.length = max(cum[-1], 1e-3)

    @staticmethod
    def _compute(curve_type, ctrl):
        if curve_type == "P" and len(ctrl) == 3:
            arc = perfect_circle(*ctrl)
            if arc:
                return arc
            curve_type = "B"
        if curve_type == "L":
            return list(ctrl)
        if curve_type == "C":
            return catmull(ctrl)
        # Bezier with red anchors (repeated points split segments)
        out = []
        seg = [ctrl[0]]
        for p in ctrl[1:]:
            if p == seg[-1]:
                if len(seg) > 1:
                    out.extend(bezier(seg))
                seg = [p]
            else:
                seg.append(p)
        if len(seg) > 1:
            out.extend(bezier(seg))
        return out or list(ctrl)

    def at(self, progress):
        d = min(max(progress, 0.0), 1.0) * self.length
        i = bisect.bisect_left(self.cum, d)
        if i <= 0:
            return self.points[0]
        if i >= len(self.cum):
            return self.points[-1]
        seg = self.cum[i] - self.cum[i - 1]
        f = (d - self.cum[i - 1]) / seg if seg > 0 else 0
        p0, p1 = self.points[i - 1], self.points[i]
        return (p0[0] + (p1[0] - p0[0]) * f, p0[1] + (p1[1] - p0[1]) * f)


# --------------------------------------------------------------------------
# Hit objects
# --------------------------------------------------------------------------

class HitObject:
    kind = "circle"

    def __init__(self, x, y, time, new_combo, combo_skip):
        self.x, self.y = x, y
        self.time = time
        self.end_time = time
        self.new_combo = new_combo
        self.combo_skip = combo_skip
        self.stack = 0
        self.ox = self.oy = 0.0  # stack offset
        self.combo_number = 1
        self.colour_index = 0

    @property
    def pos(self):
        return (self.x + self.ox, self.y + self.oy)

    @property
    def raw_end(self):
        return (self.x, self.y)

    @property
    def end_pos(self):
        return self.pos


class Circle(HitObject):
    kind = "circle"


class Spinner(HitObject):
    kind = "spinner"

    def __init__(self, time, end_time, new_combo, combo_skip):
        super().__init__(256, 192, time, new_combo, combo_skip)
        self.end_time = max(end_time, time + 1)


class SliderPart:
    __slots__ = ("time", "kind", "progress")

    def __init__(self, time, kind, progress):
        self.time = time
        self.kind = kind  # head / tick / repeat / tail
        self.progress = progress


class Slider(HitObject):
    kind = "slider"

    def __init__(self, x, y, time, new_combo, combo_skip, curve_type, ctrl, slides, length):
        super().__init__(x, y, time, new_combo, combo_skip)
        self.curve_type = curve_type
        self.ctrl = ctrl
        self.slides = max(1, slides)
        self.pixel_length = length
        self.path = None
        self.parts = []

    def build(self, beat_length, sv, multiplier, tick_rate):
        self.path = SliderPath(self.curve_type, self.ctrl, self.pixel_length)
        length = self.path.length
        velocity = 100 * multiplier * sv / beat_length  # px per ms
        self.velocity = velocity
        self.span_duration = length / velocity
        self.duration = self.span_duration * self.slides
        self.end_time = self.time + self.duration
        parts = [SliderPart(self.time, "head", 0.0)]
        tick_distance = 100 * multiplier * sv / tick_rate if tick_rate > 0 else 0
        min_from_end = velocity * 10
        ticks = []
        if tick_distance > 0 and length / tick_distance < 1000:
            d = tick_distance
            while d < length - min_from_end:
                ticks.append(d / length)
                d += tick_distance
        for span in range(self.slides):
            start = self.time + span * self.span_duration
            reverse = span % 2 == 1
            order = reversed(ticks) if reverse else ticks
            for p in order:
                tp = 1 - p if reverse else p
                parts.append(SliderPart(start + tp * self.span_duration, "tick", p))
            if span < self.slides - 1:
                parts.append(SliderPart(start + self.span_duration, "repeat",
                                        0.0 if reverse else 1.0))
        tail_time = max(self.time + self.duration / 2, self.end_time - 36)
        parts.append(SliderPart(tail_time, "tail", self.progress_at(self.end_time)))
        parts.sort(key=lambda p: p.time)
        self.parts = parts

    def progress_at(self, t):
        if self.span_duration <= 0:
            return 0.0
        p = (t - self.time) / self.span_duration
        p = min(max(p, 0.0), float(self.slides))
        span = min(int(p), self.slides - 1)
        f = p - span
        if span % 2 == 1:
            f = 1 - f
        return f

    def path_pos(self, progress):
        x, y = self.path.at(progress)
        return (x + self.ox, y + self.oy)

    def ball(self, t):
        return self.path_pos(self.progress_at(t))

    @property
    def raw_end(self):
        x, y = self.path.at(self.progress_at(self.end_time))
        return (x, y)

    @property
    def end_pos(self):
        return self.ball(self.end_time)


# --------------------------------------------------------------------------
# Beatmap
# --------------------------------------------------------------------------

class Beatmap:
    def __init__(self, text, mods=(), source=None):
        info = BeatmapInfo(text)
        if info.mode != 0:
            raise BeatmapError("Підтримується лише режим osu!standard (не taiko/catch/mania)")
        self.info = info
        self.source = source
        self.mods = set(mods)
        self.rate = 1.0
        for m in self.mods:
            self.rate = MOD_RATE.get(m, self.rate)

        cs, ar, od, hp = info.cs, info.ar, info.od, info.hp
        if "EZ" in self.mods:
            cs, ar, od, hp = cs * 0.5, ar * 0.5, od * 0.5, hp * 0.5
        if "HR" in self.mods:
            cs = min(cs * 1.3, 10)
            ar, od, hp = min(ar * 1.4, 10), min(od * 1.4, 10), min(hp * 1.4, 10)
        self.cs, self.ar, self.od, self.hp = cs, ar, od, hp

        self.radius = 54.4 - 4.48 * cs
        self.preempt = difficulty_range(ar, 1800, 1200, 450)
        self.fade_in = 400 * min(1.0, self.preempt / 450)
        self.w300 = 80 - 6 * od
        self.w100 = 140 - 8 * od
        self.w50 = 200 - 10 * od
        self.spins_per_second = difficulty_range(od, 1.5, 2.5, 3.75)

        self.colours = self._parse_colours(info.sections.get("Colours", []))
        self._parse_timing(info.sections.get("TimingPoints", []))
        self.objects = self._parse_objects(info.sections.get("HitObjects", []))
        if not self.objects:
            raise BeatmapError("У карті немає об'єктів")
        self._apply_stacking(info.stack_leniency)
        self._assign_combos()

        self.breaks = []
        for line in info.sections.get("Events", []):
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 3 and parts[0] in ("2", "Break"):
                self.breaks.append((fnum(parts[1]), fnum(parts[2])))

    # --- difficulty helpers for display ---------------------------------
    @property
    def length_ms(self):
        return self.objects[-1].end_time - self.objects[0].time

    def bpm_range(self):
        bpms = [60000 / bl for (_, bl, _, un) in self.timing_raw if un and bl > 0]
        if not bpms:
            return (0, 0)
        return (min(bpms) * self.rate, max(bpms) * self.rate)

    def max_combo(self):
        total = 0
        for o in self.objects:
            total += len(o.parts) if o.kind == "slider" else 1
        return total

    # --- parsing --------------------------------------------------------
    @staticmethod
    def _parse_colours(lines):
        cols = []
        for k, v in sorted(key_values(lines).items()):
            if k.startswith("Combo"):
                try:
                    rgb = tuple(int(float(c)) for c in v.split(",")[:3])
                    if len(rgb) == 3:
                        cols.append((int(k[5:] or 0), rgb))
                except ValueError:
                    pass
        cols.sort()
        return [c for _, c in cols] or list(DEFAULT_COLOURS)

    def _parse_timing(self, lines):
        raw = []
        for line in lines:
            p = line.split(",")
            if len(p) < 2:
                continue
            t, bl = fnum(p[0]), fnum(p[1])
            if len(p) >= 7:
                un = p[6].strip() == "1"
            else:
                un = bl > 0
            raw.append((t, bl, len(raw), un))
        raw.sort(key=lambda r: (r[0], not r[3], r[2]))
        self.timing_raw = raw
        times, beats, svs = [], [], []
        beat, sv = None, 1.0
        first_beat = next((bl for (_, bl, _, un) in raw if un and bl > 0), 500.0)
        for t, bl, _, un in raw:
            if un:
                if bl <= 0:
                    continue
                beat, sv = bl, 1.0
            else:
                sv = min(max(-100 / bl, 0.1), 10) if bl < 0 else 1.0
            times.append(t)
            beats.append(beat if beat else first_beat)
            svs.append(sv)
        self._tp_times, self._tp_beats, self._tp_svs = times, beats, svs
        self._first_beat = first_beat

    def timing_at(self, t):
        i = bisect.bisect_right(self._tp_times, t + 0.5) - 1
        if i < 0:
            return self._first_beat, 1.0
        return self._tp_beats[i], self._tp_svs[i]

    def _parse_objects(self, lines):
        hr = "HR" in self.mods
        objs = []
        for line in lines:
            p = line.split(",")
            if len(p) < 4:
                continue
            try:
                x, y, t, typ = float(p[0]), float(p[1]), float(p[2]), int(p[3])
            except ValueError:
                continue
            if hr:
                y = PLAYFIELD_H - y
            nc = bool(typ & 4)
            skip = (typ >> 4) & 7
            if typ & 1:
                objs.append(Circle(x, y, t, nc, skip))
            elif typ & 2 and len(p) >= 6:
                desc = p[5].split("|")
                ctype = desc[0].strip().upper()[:1] or "B"
                ctrl = [(x, y)]
                for c in desc[1:]:
                    if ":" in c:
                        cx, cy = c.split(":", 1)
                        cy = fnum(cy)
                        ctrl.append((fnum(cx), PLAYFIELD_H - cy if hr else cy))
                slides = int(fnum(p[6], 1)) if len(p) > 6 else 1
                length = fnum(p[7], 0) if len(p) > 7 else 0
                if len(ctrl) < 2:
                    objs.append(Circle(x, y, t, nc, skip))
                    continue
                s = Slider(x, y, t, nc, skip, ctype, ctrl, slides, length)
                beat, sv = self.timing_at(t)
                s.build(beat, sv, self.info.slider_multiplier, self.info.slider_tick_rate)
                objs.append(s)
            elif typ & 8:
                end = fnum(p[5], t) if len(p) > 5 else t
                objs.append(Spinner(t, end, nc, skip))
        objs.sort(key=lambda o: o.time)
        return objs

    def _apply_stacking(self, leniency):
        objs = self.objects
        threshold = self.preempt * leniency
        stack_distance = 3
        for i in range(len(objs) - 1, -1, -1):
            n = i
            oi = objs[i]
            if oi.stack != 0 or oi.kind == "spinner":
                continue
            if oi.kind == "circle":
                while n > 0:
                    n -= 1
                    on = objs[n]
                    if on.kind == "spinner":
                        continue
                    if oi.time - on.end_time > threshold:
                        break
                    if on.kind == "slider" and _dist(on.raw_end, (oi.x, oi.y)) < stack_distance:
                        offset = oi.stack - on.stack + 1
                        for j in range(n + 1, i + 1):
                            oj = objs[j]
                            if _dist(on.raw_end, (oj.x, oj.y)) < stack_distance:
                                oj.stack -= offset
                        break
                    if _dist((on.x, on.y), (oi.x, oi.y)) < stack_distance:
                        on.stack = oi.stack + 1
                        oi = on
            else:
                while n > 0:
                    n -= 1
                    on = objs[n]
                    if on.kind == "spinner":
                        continue
                    if oi.time - on.time > threshold:
                        break
                    if _dist(on.raw_end, (oi.x, oi.y)) < stack_distance:
                        on.stack = oi.stack + 1
                        oi = on
        step = -0.1 * self.radius
        for o in objs:
            o.ox = o.oy = o.stack * step

    def _assign_combos(self):
        colour = -1
        number = 0
        prev_spinner = False
        for i, o in enumerate(self.objects):
            if i == 0 or o.new_combo or o.kind == "spinner" or prev_spinner:
                colour += 1 + (o.combo_skip if i > 0 else 0)
                number = 0
            number += 1
            o.colour_index = colour % len(self.colours)
            o.combo_number = number
            prev_spinner = o.kind == "spinner"

    # --- assets -----------------------------------------------------------
    def audio_bytes(self):
        if self.source is None:
            return None
        return self.source.read(self.info.audio)

    def background_bytes(self):
        if self.source is None or not self.info.background:
            return None
        return self.source.read(self.info.background)


def as_file(data, name):
    f = io.BytesIO(data)
    f.name = name
    return f
