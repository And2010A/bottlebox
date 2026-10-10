"""The bot: plans cursor movement / key presses and judges them by osu! rules.

Everything is precomputed before playback, so the renderer only replays the
result. Times are in beatmap (game) milliseconds.
"""

import bisect
import math
import random

from .beatmap import MOD_SCORE

# Target fractions of (300, 100, 50, miss) for every rank the bot can aim for.
GRADE_PROFILES = {
    "SS": (1.00, 0.00, 0.00, 0.00),
    "S": (0.95, 0.05, 0.00, 0.00),
    "A": (0.86, 0.12, 0.02, 0.00),
    "B": (0.75, 0.20, 0.05, 0.00),
    "C": (0.66, 0.24, 0.05, 0.05),
    "D": (0.45, 0.30, 0.10, 0.15),
    "F": (0.20, 0.15, 0.10, 0.55),
}
GRADES = ["SS", "S", "A", "B", "C", "D", "F"]
VALUES = (300, 100, 50, 0)
MAX_RPM = 477
FOLLOW_SCALE = 2.4


def grade_of(n300, n100, n50, nmiss, failed=False):
    if failed:
        return "F"
    total = n300 + n100 + n50 + nmiss
    if total == 0:
        return "SS"
    r300 = n300 / total
    r50 = n50 / total
    if r300 == 1:
        return "SS"
    if r300 > 0.9 and r50 <= 0.01 and nmiss == 0:
        return "S"
    if (r300 > 0.8 and nmiss == 0) or r300 > 0.9:
        return "A"
    if (r300 > 0.7 and nmiss == 0) or r300 > 0.8:
        return "B"
    if r300 > 0.6:
        return "C"
    return "D"


def accuracy(n300, n100, n50, nmiss):
    total = n300 + n100 + n50 + nmiss
    if total == 0:
        return 1.0
    return (300 * n300 + 100 * n100 + 50 * n50) / (300 * total)


# --------------------------------------------------------------------------
# Cursor path and key presses
# --------------------------------------------------------------------------

class CursorPath:
    def __init__(self, start_pos, start_time):
        self.t0s = []
        self.segs = []
        self.add(start_time - 1e6, start_time, lambda t, p=start_pos: p)

    def add(self, t0, t1, fn):
        if self.t0s and t0 < self.t0s[-1]:
            t0 = self.t0s[-1]
        t1 = max(t0, t1)
        self.t0s.append(t0)
        self.segs.append((t0, t1, fn))

    def at(self, t):
        i = bisect.bisect_right(self.t0s, t) - 1
        if i < 0:
            i = 0
            t = self.segs[0][0]
        t0, t1, fn = self.segs[i]
        return fn(min(t, t1))


class Keys:
    def __init__(self):
        self.presses = []  # (down, up, key)
        self.next_key = 0

    def press(self, down, up, key=None):
        if key is None:
            key = self.next_key
            self.next_key ^= 1
        self.presses.append((down, max(up, down + 1), key))

    def finalize(self):
        self.presses.sort()
        self.downs = [p[0] for p in self.presses]

    def held(self, t):
        i = bisect.bisect_right(self.downs, t) - 1
        # look back a few presses; slider holds can overlap short taps
        for j in range(i, max(-1, i - 4), -1):
            d, u, _ = self.presses[j]
            if d <= t <= u:
                return True
        return False

    def keys_down(self, t):
        down = [False, False]
        i = bisect.bisect_right(self.downs, t) - 1
        for j in range(i, max(-1, i - 6), -1):
            d, u, k = self.presses[j]
            if d <= t <= u:
                down[k] = True
        return down

    def count_before(self, t, key):
        i = bisect.bisect_right(self.downs, t)
        return sum(1 for p in self.presses[:i] if p[2] == key)


def ease(f):
    return 0.5 - 0.5 * math.cos(math.pi * min(max(f, 0.0), 1.0))


def move_fn(p0, p1, t0, t1, bend=0.0):
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    cx = (p0[0] + p1[0]) / 2 - dy * bend
    cy = (p0[1] + p1[1]) / 2 + dx * bend
    dur = max(t1 - t0, 1e-6)

    def fn(t):
        f = ease((t - t0) / dur)
        a = (1 - f) * (1 - f)
        b = 2 * (1 - f) * f
        c = f * f
        return (a * p0[0] + b * cx + c * p1[0], a * p0[1] + b * cy + c * p1[1])
    return fn


# --------------------------------------------------------------------------
# Results
# --------------------------------------------------------------------------

class Event:
    __slots__ = ("time", "kind", "value", "obj", "pos", "error", "combo", "sub")

    def __init__(self, time, kind, value, obj, pos=None, error=None, combo=True, sub=None):
        self.sub = sub        # head / tick / repeat / tail for slider parts
        self.time = time
        self.kind = kind      # judgement / part
        self.value = value    # 300/100/50/0 for judgements, True/False for parts
        self.obj = obj
        self.pos = pos
        self.error = error
        self.combo = combo


class ObjResult:
    def __init__(self):
        self.value = 0
        self.judge_time = 0.0
        self.hit = False
        self.head_hit = False
        self.head_time = None
        self.release = None
        self.part_hits = []
        self.spin = None  # (start, stop, omega, required)


class Snapshot:
    __slots__ = ("time", "score", "combo", "max_combo", "counts", "hp")

    def __init__(self, time, score, combo, max_combo, counts, hp):
        self.time = time
        self.score = score
        self.combo = combo
        self.max_combo = max_combo
        self.counts = counts
        self.hp = hp


class Play:
    """A complete simulated play of a beatmap."""

    ruleset = "osu"

    @staticmethod
    def acc_of(counts):
        return accuracy(*counts)

    @staticmethod
    def grade_of(counts):
        return grade_of(*counts)

    def max_combo_possible(self):
        return self.bm.max_combo()

    def __init__(self, beatmap, mode="grade", target="SS", skill=7.0, seed=None):
        self.bm = beatmap
        self.mode = mode
        self.target = target
        self.skill = skill
        self.rng = random.Random(seed)
        first = beatmap.objects[0].time
        self.cursor = CursorPath((256, 192), first - 2000)
        self.keys = Keys()
        self.events = []
        self.results = [ObjResult() for _ in beatmap.objects]
        self.state_pos = (256, 192)
        self.state_time = first - 2000
        self.counts = [0, 0, 0, 0]
        self.hp = 1.0
        self._plan()
        self.keys.finalize()
        self._build_timeline()

    # ----- skill parameters -------------------------------------------
    def _skill_params(self):
        u = (min(max(self.skill, 1), 10) - 1) / 9
        rate = self.bm.rate  # a human reacts in real time, the map runs in game time
        return {
            "sigma": 45 * (4 / 45) ** u * rate,
            "vmax": 1.2 * (15 / 1.2) ** u / rate,
            "aim": 0.5 * (0.08 / 0.5) ** u,
            "rpm": (250 + 220 * u) / rate,
            "drop": 0.03 * (1 - u) ** 2,
        }

    # ----- HP model -----------------------------------------------------
    def hp_delta(self, kind, value):
        dr = self.bm.hp
        gain = 1 - dr * 0.04
        if kind == "part":
            return 0.01 * gain if value else -(0.01 + 0.002 * dr)
        return {300: 0.035 * gain, 100: 0.015 * gain, 50: 0.004 * gain}.get(
            value, -(0.05 + 0.01 * dr))

    # ----- planning -----------------------------------------------------
    def _choose_outcome(self, obj):
        profile = GRADE_PROFILES[self.target]
        n = sum(self.counts) + 1
        allowed = [k for k in range(4) if profile[k] > 0]
        if self.target != "F" and 3 in allowed:
            parts = len(obj.parts) if obj.kind == "slider" else 0
            penalty = -self.hp_delta("judge", 0) - parts * self.hp_delta("part", False)
            if self.hp - penalty < 0.3:
                allowed.remove(3)
        best, best_k = -1e9, allowed[0]
        for k in allowed:
            d = profile[k] * n - self.counts[k] + self.rng.random() * 0.6
            if d > best:
                best, best_k = d, k
        return best_k

    def _record(self, i, value, time, pos, error=None):
        r = self.results[i]
        r.value = value
        r.judge_time = time
        r.hit = value > 0
        self.counts[VALUES.index(value)] += 1
        self.events.append(Event(time, "judge", value, i, pos, error))
        self.hp = min(1.0, max(0.0, self.hp + self.hp_delta("judge", value)))

    def _plan(self):
        objs = self.bm.objects
        for i, obj in enumerate(objs):
            if self.mode == "grade":
                outcome = self._choose_outcome(obj)
            else:
                outcome = None
            if obj.kind == "circle":
                self._plan_circle(i, obj, outcome)
            elif obj.kind == "slider":
                self._plan_slider(i, obj, outcome)
            else:
                self._plan_spinner(i, obj, outcome)

    def _move_to(self, target, arrive, bend=0.0):
        start = max(self.state_time, arrive - 450)
        if arrive > start:
            self.cursor.add(start, arrive, move_fn(self.state_pos, target, start, arrive, bend))
        self.state_pos = target
        self.state_time = max(arrive, self.state_time)

    def _bend(self):
        if self.mode == "grade" and self.target == "SS":
            return 0.0
        return self.rng.uniform(-0.18, 0.18)

    def _aim_click(self, i, obj, outcome):
        """Decide click time / position for a circle or slider head.

        Returns (click_time, click_pos) or None if the bot skips the object.
        """
        bm = self.bm
        r = bm.radius
        t = obj.time
        target = obj.pos
        rng = self.rng
        if self.mode == "grade":
            if outcome == 0:
                spread = 0.05 if self.target == "SS" else 0.3
                e = max(-0.8 * bm.w300, min(0.8 * bm.w300, rng.gauss(0, bm.w300 * spread)))
            elif outcome == 1:
                e = rng.choice((-1, 1)) * rng.uniform(bm.w300 + 2, bm.w100 - 2)
            elif outcome == 2:
                e = rng.choice((-1, 1)) * rng.uniform(bm.w100 + 2, bm.w50 - 2)
            else:
                e = rng.gauss(0, bm.w300 * 0.5)
            if outcome == 3:
                ang = rng.uniform(0, 2 * math.pi)
                dist = rng.uniform(1.3, 1.9) * r
            elif self.target == "SS":
                ang, dist = 0.0, 0.0
            else:
                ang = rng.uniform(0, 2 * math.pi)
                dist = rng.uniform(0, 0.4) * r
            tc = max(t + e, self.state_time + 1)
            pos = (target[0] + math.cos(ang) * dist, target[1] + math.sin(ang) * dist)
            self._move_to(pos, tc, self._bend())
            return tc, pos
        # skill mode: physics decide
        sp = self._skill_params()
        tc = t + rng.gauss(0, sp["sigma"])
        d = math.hypot(target[0] - self.state_pos[0], target[1] - self.state_pos[1])
        start = max(self.state_time, tc - 450)
        min_dur = (math.pi / 2) * d / sp["vmax"]
        if tc - start < min_dur:
            tc = start + min_dur
        speed = d / max(tc - start, 1) / sp["vmax"]
        sigma = sp["aim"] * r * (0.5 + 1.5 * speed)
        pos = (target[0] + rng.gauss(0, sigma), target[1] + rng.gauss(0, sigma))
        return tc, pos

    def _judge_click(self, obj, tc, pos):
        bm = self.bm
        e = tc - obj.time
        inside = math.hypot(pos[0] - obj.pos[0], pos[1] - obj.pos[1]) <= bm.radius
        if not inside or abs(e) > bm.w50:
            return 0, e
        if abs(e) <= bm.w300:
            return 300, e
        if abs(e) <= bm.w100:
            return 100, e
        return 50, e

    def _plan_circle(self, i, obj, outcome):
        bm = self.bm
        if self.mode == "skill":
            tc, pos = self._aim_click(i, obj, outcome)
            if tc > obj.time + bm.w50:
                # cannot reach it in time - give up on it
                self._record(i, 0, obj.time + bm.w50, obj.pos)
                return
            self._move_to(pos, tc, self._bend())
        else:
            tc, pos = self._aim_click(i, obj, outcome)
        self.keys.press(tc, tc + 55)
        value, e = self._judge_click(obj, tc, pos)
        if value:
            self._record(i, value, tc, obj.pos, e)
        else:
            self._record(i, 0, max(tc, obj.time + bm.w50), obj.pos)

    def _plan_slider(self, i, obj, outcome):
        bm = self.bm
        res = self.results[i]
        parts = obj.parts
        n = len(parts)
        release = obj.end_time
        press = None
        if self.mode == "grade":
            if outcome == 3:
                # miss: wander near the head without pressing
                ang = self.rng.uniform(0, 2 * math.pi)
                d = 1.6 * bm.radius
                pos = (obj.pos[0] + math.cos(ang) * d, obj.pos[1] + math.sin(ang) * d)
                self._move_to(pos, max(obj.time, self.state_time + 1), self._bend())
            else:
                tc, pos = self._aim_click(i, obj, 0)
                press = tc
                if outcome == 1:
                    k = max(1, int(n * 0.3))
                    k = min(k, n - 1)
                    keep = parts[n - k - 1]
                    nxt = parts[n - k]
                    release = keep.time + min(25, (nxt.time - keep.time) / 2)
                elif outcome == 2:
                    release = parts[0].time + min(25, (parts[1].time - parts[0].time) / 2)
        else:
            sp = self._skill_params()
            tc, pos = self._aim_click(i, obj, None)
            if tc >= obj.end_time - 20:
                self._record(i, 0, obj.end_time, obj.end_pos)
                res.part_hits = [False] * n
                for p in parts:
                    self.events.append(Event(p.time, "part", False, i, obj.path_pos(p.progress),
                                             combo=(p.kind != "tail"), sub=p.kind))
                return
            if tc > obj.time + bm.w50:
                pos = obj.ball(tc)  # late: grab the ball wherever it is
            self._move_to(pos, tc, self._bend())
            press = tc
            for p in parts[1:]:
                if p.time > tc and self.rng.random() < sp["drop"]:
                    release = max(tc + 10, p.time - 15)
                    break

        if press is not None:
            hold_from = press
            ball_off = (pos[0] - obj.ball(press)[0], pos[1] - obj.ball(press)[1])

            def follow(t, ob=obj, off=ball_off, t0=hold_from):
                bx, by = ob.ball(t)
                # the offset from an imperfect click shrinks quickly
                k = max(0.0, 1 - (t - t0) / 120)
                return (bx + off[0] * k, by + off[1] * k)
            self.cursor.add(press, release, follow)
            self.keys.press(press, release)
            self.state_pos = follow(release)
            self.state_time = release
            res.head_time = press
            res.release = release

        # judge parts
        hits = []
        head_value, err = (0, None)
        if press is not None:
            head_value, err = self._judge_click(obj, press, pos)
        res.head_hit = head_value > 0
        hits.append(res.head_hit)
        head_t = press if (press is not None and res.head_hit) else obj.time + bm.w50
        res.head_judge_time = head_t
        self.events.append(Event(head_t, "part", res.head_hit, i, obj.pos,
                                 err if res.head_hit else None, sub="head"))
        self.hp += self.hp_delta("part", res.head_hit)
        follow_r = bm.radius * FOLLOW_SCALE
        for p in parts[1:]:
            ok = False
            if press is not None and press <= p.time <= release:
                c = self.cursor.at(p.time)
                b = obj.path_pos(p.progress)
                ok = math.hypot(c[0] - b[0], c[1] - b[1]) <= follow_r
            hits.append(ok)
            self.events.append(Event(p.time, "part", ok, i, obj.path_pos(p.progress),
                                     combo=(p.kind != "tail"), sub=p.kind))
            self.hp += self.hp_delta("part", ok)
        self.hp = min(1.0, max(0.0, self.hp))
        res.part_hits = hits
        ratio = sum(hits) / n
        value = 300 if ratio == 1 else 100 if ratio >= 0.5 else 50 if ratio > 0 else 0
        self._record(i, value, obj.end_time, obj.end_pos)

    def _plan_spinner(self, i, obj, outcome):
        res = self.results[i]
        center = (256, 192)
        radius = 55
        if self.mode == "grade":
            rpm = 460
        else:
            rpm = self._skill_params()["rpm"]
        omega = min(rpm, MAX_RPM) / 60000 * 2 * math.pi  # rad per ms
        duration = obj.end_time - obj.time
        required = int(duration / 1000 * self.bm.spins_per_second)
        cp = self.state_pos
        ang0 = math.atan2(cp[1] - center[1], cp[0] - center[0])
        entry = (center[0] + math.cos(ang0) * radius, center[1] + math.sin(ang0) * radius)
        arrive = max(obj.time, self.state_time + 60)
        self._move_to(entry, arrive)
        start = arrive
        stop = obj.end_time
        if self.mode == "grade" and required > 0:
            frac = {0: 1.2, 1: 0.93, 2: 0.8, 3: 0.3}[outcome]
            if frac < 1:
                stop = min(stop, start + frac * required * 2 * math.pi / omega)
        stop = max(stop, start)

        def spin(t, a0=ang0, s=start):
            a = a0 + omega * (t - s)
            return (center[0] + math.cos(a) * radius, center[1] + math.sin(a) * radius)
        self.cursor.add(start, stop, spin)
        self.keys.press(start, stop, 0)
        self.state_pos = spin(stop)
        self.state_time = stop
        rotations = omega * (min(stop, obj.end_time) - start) / (2 * math.pi)
        ratio = rotations / required if required > 0 else 1.0
        res.spin = (start, stop, omega, required)
        value = 300 if ratio >= 1 else 100 if ratio >= 0.9 else 50 if ratio >= 0.75 else 0
        self._record(i, value, obj.end_time, center)

    # ----- score / combo / HP timeline -----------------------------------
    def _build_timeline(self):
        bm = self.bm
        objs = bm.objects
        drain_s = max((objs[-1].end_time - objs[0].time) / 1000, 1)
        diff = round((bm.info.hp + bm.info.cs + bm.info.od
                      + min(max(len(objs) / drain_s * 8, 0), 16)) / 38 * 5)
        mod_mul = 1.0
        for m in bm.mods:
            mod_mul *= MOD_SCORE.get(m, 1.0)
        self.events.sort(key=lambda e: (e.time, e.kind != "part"))
        score, combo, max_combo = 0, 0, 0
        counts = [0, 0, 0, 0]
        hp = 1.0
        snaps = [Snapshot(-1e9, 0, 0, 0, (0, 0, 0, 0), 1.0)]
        self.fail_time = None
        self.hit_errors = []
        nofail = "NF" in bm.mods
        for ev in self.events:
            if ev.kind == "part":
                if ev.value:
                    combo += 1
                    score += 10
                elif ev.combo:
                    combo = 0
                if ev.error is not None:
                    self.hit_errors.append((ev.time, ev.error))
                hp += self.hp_delta("part", ev.value)
            else:
                v = ev.value
                counts[VALUES.index(v)] += 1
                if objs[ev.obj].kind != "slider":
                    if v:
                        combo += 1
                    else:
                        combo = 0
                if v:
                    score += int(v + v * max(combo - 1, 0) * diff * mod_mul / 25)
                if ev.error is not None:
                    self.hit_errors.append((ev.time, ev.error))
                hp += self.hp_delta("judge", v)
            hp = min(1.0, max(0.0, hp))
            max_combo = max(max_combo, combo)
            snaps.append(Snapshot(ev.time, score, combo, max_combo, tuple(counts), hp))
            if hp <= 0 and not nofail:
                self.fail_time = ev.time
                break
        self.snapshots = snaps
        self.snap_times = [s.time for s in snaps]
        final = snaps[-1]
        self.final = final
        self.failed = self.fail_time is not None
        self.grade = grade_of(*final.counts, failed=self.failed)
        self.accuracy = accuracy(*final.counts)
        errs = [e for _, e in self.hit_errors]
        if len(errs) > 1:
            mean = sum(errs) / len(errs)
            self.unstable_rate = 10 * math.sqrt(sum((e - mean) ** 2 for e in errs) / len(errs))
        else:
            self.unstable_rate = 0.0
        self.end_time = self.fail_time if self.failed else objs[-1].end_time

    def snapshot_at(self, t):
        i = bisect.bisect_right(self.snap_times, t) - 1
        return self.snapshots[max(i, 0)]
