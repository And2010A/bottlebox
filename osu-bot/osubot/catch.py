"""osu!catch: converting a beatmap into fruits, and a bot that moves the catcher.

Conversion follows osu!'s rules: circles become fruits, sliders become juice
streams (fruits, droplets and tiny droplets), spinners become banana showers.
Hyperdash fruits are generated the same way the game does it.
"""

import bisect
import random

from .beatmap import MOD_SCORE
from .sim import Snapshot

BASE_SIZE = 106.75
ALLOWED_CATCH_RANGE = 0.8
WALK_SPEED = 0.5    # px per ms
DASH_SPEED = 1.0

GRADES = ["SS", "S", "A", "B", "C", "D", "F"]
TARGET_ACC = {"S": 0.99, "A": 0.96, "B": 0.92, "C": 0.875, "D": 0.72, "F": 0.35}

# counts layout: caught fruit/droplet/tiny, missed fruit/droplet/tiny, bananas caught
FRUIT, DROPLET, TINY, BANANA = "fruit", "droplet", "tiny", "banana"
KIND_INDEX = {FRUIT: 0, DROPLET: 1, TINY: 2}


def catch_accuracy(counts):
    caught = counts[0] + counts[1] + counts[2]
    total = caught + counts[3] + counts[4] + counts[5]
    return caught / total if total else 1.0


def catch_grade(counts, failed=False):
    if failed:
        return "F"
    acc = catch_accuracy(counts)
    if acc == 1:
        return "SS"
    if acc > 0.98:
        return "S"
    if acc > 0.94:
        return "A"
    if acc > 0.90:
        return "B"
    if acc > 0.85:
        return "C"
    return "D"


class CatchObject:
    __slots__ = ("time", "x", "kind", "colour_index", "hyper", "src", "combo_end")

    def __init__(self, time, x, kind, colour_index, src):
        self.time = time
        self.x = min(max(x, 0.0), 512.0)
        self.kind = kind
        self.colour_index = colour_index
        self.hyper = False
        self.src = src
        self.combo_end = False


def convert(bm, rng):
    out = []
    for i, ho in enumerate(bm.objects):
        col = ho.colour_index
        if ho.kind == "circle":
            out.append(CatchObject(ho.time, ho.x, FRUIT, col, i))
        elif ho.kind == "slider":
            events = []
            for p in ho.parts:
                if p.kind == "tail":
                    events.append((ho.end_time, FRUIT, ho.path.at(ho.progress_at(ho.end_time))[0]))
                else:
                    kind = DROPLET if p.kind == "tick" else FRUIT
                    events.append((p.time, kind, ho.path.at(p.progress)[0]))
            events.sort(key=lambda e: e[0])
            last = None
            for t, kind, x in events:
                if last is not None:
                    since = int(t) - int(last)
                    if since > 80:
                        step = since
                        while step > 100:
                            step /= 2
                        k = step
                        while k < since:
                            tt = last + k
                            tx = ho.path.at(ho.progress_at(tt))[0] + rng.randint(-20, 20)
                            out.append(CatchObject(tt, tx, TINY, col, i))
                            k += step
                out.append(CatchObject(t, x, kind, col, i))
                last = t
        else:
            duration = ho.end_time - ho.time
            spacing = duration
            while spacing > 100:
                spacing /= 2
            if spacing > 0:
                t = ho.time
                while t <= ho.end_time:
                    out.append(CatchObject(t, rng.uniform(0, 512), BANANA, col, i))
                    t += spacing
    out.sort(key=lambda o: o.time)
    # mark the last fruit of every combo (the catcher plate is cleared there)
    for k, o in enumerate(out):
        nxt = next((n for n in out[k + 1:k + 400] if n.kind != TINY), None)
        if o.kind != TINY and (nxt is None or bm.objects[nxt.src].combo_number == 1
                               and nxt.src != o.src):
            o.combo_end = True
    return out


def catch_width(cs):
    return BASE_SIZE * abs(1 - 0.7 * (cs - 5) / 5) * ALLOWED_CATCH_RANGE


def init_hyperdash(objs, cs):
    palpable = [o for o in objs if o.kind in (FRUIT, DROPLET)]
    half = catch_width(cs) / 2 / ALLOWED_CATCH_RANGE
    last_dir = 0
    last_excess = half
    for a, b in zip(palpable, palpable[1:]):
        a.hyper = False
        direction = 1 if b.x > a.x else -1
        time_to_next = int(b.time) - int(a.time) - 1000 / 60 / 4
        dist = abs(b.x - a.x) - (last_excess if last_dir == direction else half)
        to_hyper = time_to_next * DASH_SPEED - dist
        if to_hyper < 0:
            a.hyper = True
            last_excess = half
        else:
            last_excess = min(max(to_hyper, 0), half)
        last_dir = direction


class CatchPlay:
    ruleset = "catch"

    def __init__(self, beatmap, mode="grade", target="SS", skill=7.0, seed=None):
        self.bm = beatmap
        self.mode = mode
        self.target = target
        self.skill = skill
        seed = random.randrange(1 << 30) if seed is None else seed
        self.objects = convert(beatmap, random.Random(1337))
        init_hyperdash(self.objects, beatmap.cs)
        self.width = catch_width(beatmap.cs)
        self.half = self.width / 2
        # scored objects (no bananas) for accuracy
        self.scored = [o for o in self.objects if o.kind != BANANA]
        best = None
        for attempt in range(12):
            self.rng = random.Random(seed + attempt * 7919)
            self._simulate()
            if mode != "grade" or self.grade == target:
                break
            if best is None or abs(GRADES.index(self.grade) - GRADES.index(target)) < \
                    abs(GRADES.index(best[0]) - GRADES.index(target)):
                best = (self.grade, attempt)
        else:
            if best is not None:
                self.rng = random.Random(seed + best[1] * 7919)
                self._simulate()

    # ------------------------------------------------------------------
    def _plan_misses(self):
        """Grade mode: pick which objects the bot will drop on purpose."""
        if self.mode != "grade" or self.target == "SS":
            return set()
        n = len(self.scored)
        if n == 0:
            return set()
        k = max(1, round((1 - TARGET_ACC[self.target]) * n))
        if self.target == "S":
            cand = [o for o in self.scored if o.kind == TINY] or list(self.scored)
        elif self.target == "F":
            cand = [o for o in self.scored if o.kind == FRUIT] or list(self.scored)
            k = min(len(cand), max(k, int(len(cand) * 0.7)))
        else:
            cand = list(self.scored)
        k = min(k, len(cand))
        step = len(cand) / k
        rng = self.rng
        return {id(cand[min(len(cand) - 1, int((j + rng.uniform(0.15, 0.85)) * step))])
                for j in range(k)}

    def _skill_sigma(self):
        u = (min(max(self.skill, 1), 10) - 1) / 9
        return self.half * 0.95 * (0.07 / 0.95) ** u

    def _simulate(self):
        objs = self.objects
        n = len(objs)
        miss_ids = self._plan_misses()
        half = self.half
        margin = half * 0.85
        want = [o.kind != BANANA and id(o) not in miss_ids for o in objs]

        # backward pass: positions from which the rest stays catchable
        lo = [0.0] * n
        hi = [512.0] * n
        for i in range(n - 1, -1, -1):
            o = objs[i]
            if i == n - 1:
                elo, ehi = 0.0, 512.0
            else:
                dt = objs[i + 1].time - o.time
                if o.hyper and want[i]:
                    elo, ehi = 0.0, 512.0
                else:
                    elo = max(0.0, lo[i + 1] - DASH_SPEED * dt)
                    ehi = min(512.0, hi[i + 1] + DASH_SPEED * dt)
            if want[i]:
                a, b = max(elo, o.x - margin), min(ehi, o.x + margin)
                if a > b:
                    a, b = max(0.0, o.x - margin), min(512.0, o.x + margin)
                lo[i], hi[i] = a, b
            else:
                lo[i], hi[i] = elo, ehi

        # forward pass
        sigma = self._skill_sigma() if self.mode == "skill" else 0.0
        rng = self.rng
        pos = 256.0
        prev_t = None
        prev_hyper = False
        self.waypoints = [(objs[0].time - 3000 if objs else 0.0, 256.0)]
        self.caught = [False] * n
        self.catch_pos = [0.0] * n
        hp = 1.0
        for i, o in enumerate(objs):
            if prev_t is None:
                rlo, rhi = 0.0, 512.0
            else:
                dt = o.time - prev_t
                reach = 1e9 if prev_hyper else DASH_SPEED * dt
                rlo, rhi = max(0.0, pos - reach), min(512.0, pos + reach)
            a, b = max(rlo, lo[i]), min(rhi, hi[i])
            if a > b:
                a, b = rlo, rhi
            if o.kind == BANANA:
                ca, cb = max(a, o.x - margin), min(b, o.x + margin)
                p = min(max(o.x, ca), cb) if ca <= cb else min(max(o.x, a), b)
            elif want[i] or (self.target != "F" and hp + self.hp_delta(o.kind, False) < 0.3):
                p = min(max(o.x, a), b)
                if sigma:
                    s = sigma * (1.3 if o.kind == TINY else 1.0)
                    speed = abs(p - pos) / max(1.0, o.time - (prev_t or o.time - 1000))
                    p = min(max(p + rng.gauss(0, s * (1 + 1.2 * min(speed, 3))), rlo), rhi)
            else:
                # deliberate miss: stay out of the catching range if we can
                left, right = o.x - half - 4, o.x + half + 4
                options = []
                if a <= left:
                    options.append(min(max(pos, a), left))
                if b >= right:
                    options.append(min(max(pos, right), b))
                p = min(options, key=lambda q: abs(q - pos)) if options else min(max(pos, a), b)
            caught = abs(p - o.x) <= half
            if o.kind != BANANA:
                hp = min(1.0, max(0.0, hp + self.hp_delta(o.kind, caught)))
            self.caught[i] = caught
            self.catch_pos[i] = p
            self.waypoints.append((o.time, p))
            pos = p
            prev_t = o.time
            prev_hyper = o.hyper and caught
        self._build_timeline()
        self._build_motion()

    def _build_motion(self):
        """Catcher path: move right after a catch, then wait (like a player)."""
        segs = []  # (t0, t1, x0, x1, speed)
        wp = self.waypoints
        for (t0, x0), (t1, x1) in zip(wp, wp[1:]):
            dist = abs(x1 - x0)
            dt = max(t1 - t0, 1e-6)
            need = dist / dt
            speed = WALK_SPEED if need <= WALK_SPEED else DASH_SPEED if need <= DASH_SPEED else need
            dur = dist / speed if speed > 0 else 0
            segs.append((t0, t0 + dur, x0, x1, speed))
        self.segs = segs
        self.seg_t = [s[0] for s in segs]

    def catcher_at(self, t):
        """Returns (x, speed) of the catcher at game time t."""
        if not self.segs:
            return 256.0, 0.0
        i = bisect.bisect_right(self.seg_t, t) - 1
        if i < 0:
            return self.segs[0][2], 0.0
        t0, t1, x0, x1, speed = self.segs[i]
        if t >= t1:
            return x1, 0.0
        f = (t - t0) / max(t1 - t0, 1e-6)
        return x0 + (x1 - x0) * f, speed if x1 != x0 else 0.0

    # ------------------------------------------------------------------
    def hp_delta(self, kind, caught):
        dr = self.bm.hp
        gain = 1 - dr * 0.04
        if caught:
            return {FRUIT: 0.03, DROPLET: 0.012, TINY: 0.004}.get(kind, 0) * gain
        return {FRUIT: -(0.05 + 0.01 * dr), DROPLET: -(0.03 + 0.006 * dr),
                TINY: -0.003}.get(kind, 0)

    def _build_timeline(self):
        bm = self.bm
        hos = bm.objects
        drain_s = max((hos[-1].end_time - hos[0].time) / 1000, 1)
        diff = round((bm.info.hp + bm.info.cs + bm.info.od
                      + min(max(len(hos) / drain_s * 8, 0), 16)) / 38 * 5)
        mod_mul = 1.0
        for m in bm.mods:
            mod_mul *= MOD_SCORE.get(m, 1.0)
        nofail = "NF" in bm.mods
        score, combo, max_combo, hp = 0, 0, 0, 1.0
        counts = [0] * 7
        snaps = [Snapshot(-1e9, 0, 0, 0, tuple(counts), 1.0)]
        self.fail_time = None
        for i, o in enumerate(self.objects):
            caught = self.caught[i]
            if o.kind == BANANA:
                if caught:
                    counts[6] += 1
                    score += 1100
                snaps.append(Snapshot(o.time, score, combo, max_combo, tuple(counts), hp))
                continue
            k = KIND_INDEX[o.kind]
            if caught:
                counts[k] += 1
                if o.kind != TINY:
                    combo += 1
                value = {FRUIT: 300, DROPLET: 100, TINY: 10}[o.kind]
                score += int(value + value * max(combo - 1, 0) * diff * mod_mul / 25) \
                    if o.kind != TINY else value
            else:
                counts[3 + k] += 1
                if o.kind != TINY:
                    combo = 0
            hp = min(1.0, max(0.0, hp + self.hp_delta(o.kind, caught)))
            max_combo = max(max_combo, combo)
            snaps.append(Snapshot(o.time, score, combo, max_combo, tuple(counts), hp))
            if hp <= 0 and not nofail:
                self.fail_time = o.time
                break
        self.snapshots = snaps
        self.snap_times = [s.time for s in snaps]
        self.final = snaps[-1]
        self.failed = self.fail_time is not None
        self.grade = catch_grade(self.final.counts, self.failed)
        self.accuracy = catch_accuracy(self.final.counts)
        self.end_time = self.fail_time if self.failed else \
            max(hos[-1].end_time, self.objects[-1].time if self.objects else 0)
        self.unstable_rate = None

    def snapshot_at(self, t):
        i = bisect.bisect_right(self.snap_times, t) - 1
        return self.snapshots[max(i, 0)]

    @staticmethod
    def acc_of(counts):
        return catch_accuracy(counts)

    @staticmethod
    def grade_of(counts):
        return catch_grade(counts)

    def max_combo_possible(self):
        return sum(1 for o in self.objects if o.kind in (FRUIT, DROPLET))
