"""Playback scenes: the shared base (clock, music, background, HUD) and osu!standard."""

import bisect
import math
import time

import pygame

from .beatmap import as_file
from .sim import FOLLOW_SCALE
from .ui import (ACCENT, GRADE_COLOURS, MUTED, WHITE, blit_centered, cover, load_image, make_icon,
                 mix, rect, view)

JUDGE_COLOURS = {300: (110, 190, 255), 100: (120, 230, 100), 50: (255, 190, 70), 0: (255, 60, 60)}


class BasePlayScene:
    """Everything a playback scene needs except drawing the ruleset itself."""

    def __init__(self, app, bm, play):
        self.app = app
        self.bm = bm
        self.play = play
        self.sound_events = []  # (time, "hit" | "tick")
        self.sound_idx = 0
        self.hp_shown = 1.0
        self.paused = False
        self.pause_real = 0.0
        self.failed_real = None
        self.finished = False
        self.bg_img = load_image(bm.background_bytes(), bm.info.background)
        self.dim_now = 1.0
        self.avatar = None
        self.music = None
        self.music_sound = None
        self.music_array = None
        self.channel = None
        self.music_note = None
        self._load_music()
        first = self.first_time()
        lead = max(bm.preempt + 800, 1500)
        self.start_game = min(0.0, first - lead)
        self.skip_to = first - lead if first - lead > 3000 else None
        self.music_started = False
        self.base_game = self.start_game
        self.real_start = self.base_real = time.perf_counter()
        self.auto_skip_at = self.base_real + 3.0

    def first_time(self):
        return self.bm.objects[0].time

    def last_time(self):
        return self.bm.objects[-1].end_time

    # --- resources --------------------------------------------------------
    def on_resize(self):
        size = (view.win_w, view.win_h)
        self.background = cover(self.bg_img, *size)
        self.dim_surf = pygame.Surface(size)
        self.dim_surf.fill((0, 0, 0))
        self.overlay = pygame.Surface(size, pygame.SRCALPHA)
        self.avatar = make_icon(max(16, int(view.s(30))))
        self.build_sprites()

    def build_sprites(self):
        pass

    def _load_music(self):
        if not self.app.audio_ok:
            self.music_note = "немає аудіопристрою"
            return
        data = self.bm.audio_bytes()
        name = self.bm.info.audio or "audio.mp3"
        if not data:
            self.music_note = None if self.bm.source is None else "музику не знайдено"
            return
        rate = self.bm.rate
        try:
            if rate == 1.0:
                self.music = as_file(data, name)
                pygame.mixer.music.load(self.music, name)
                pygame.mixer.music.set_volume(0.55)
            else:
                import numpy as np
                snd = pygame.mixer.Sound(file=as_file(data, name))
                arr = pygame.sndarray.array(snd)
                idx = (np.arange(int(len(arr) / rate)) * rate).astype(np.int64)
                self.music_array = arr[idx]
        except Exception:
            self.music = None
            self.music_array = None
            self.music_note = "не вдалося відтворити музику"

    def _start_music(self, game_t):
        pos = max(0.0, game_t) / 1000
        try:
            if self.music is not None:
                pygame.mixer.music.play(start=pos)
            elif self.music_array is not None:
                import numpy as np
                freq = pygame.mixer.get_init()[0]
                start = int(pos * freq / self.bm.rate)
                if start < len(self.music_array):
                    chunk = np.ascontiguousarray(self.music_array[start:])
                    self.music_sound = pygame.sndarray.make_sound(chunk)
                    self.music_sound.set_volume(0.55)
                    self.channel = self.music_sound.play()
        except Exception:
            self.music_note = "не вдалося відтворити музику"
        self.music_started = True

    def _stop_music(self, fade=0):
        try:
            if fade:
                pygame.mixer.music.fadeout(fade)
                if self.channel:
                    self.channel.fadeout(fade)
            else:
                pygame.mixer.music.stop()
                if self.channel:
                    self.channel.stop()
        except Exception:
            pass

    def stop(self):
        self._stop_music()
        try:
            pygame.mixer.music.unload()
        except Exception:
            pass

    # --- clock ----------------------------------------------------------------
    def now(self):
        real = self.pause_real if self.paused else time.perf_counter()
        return self.base_game + (real - self.base_real) * 1000 * self.bm.rate

    def seek(self, game_t):
        self.base_game = game_t
        self.base_real = time.perf_counter()
        self._stop_music()
        self.music_started = False
        if game_t >= 0:
            self._start_music(game_t)
        self.sound_idx = bisect.bisect_left([e[0] for e in self.sound_events], game_t)

    def toggle_pause(self):
        if self.failed_real or self.finished:
            return
        try:
            if self.paused:
                self.base_real += time.perf_counter() - self.pause_real
                self.paused = False
                pygame.mixer.music.unpause()
                if self.channel:
                    self.channel.unpause()
            else:
                self.pause_real = time.perf_counter()
                self.paused = True
                pygame.mixer.music.pause()
                if self.channel:
                    self.channel.pause()
        except Exception:
            pass

    # --- events -----------------------------------------------------------------
    def handle(self, ev):
        if ev.type != pygame.KEYDOWN:
            return
        if ev.key == pygame.K_ESCAPE:
            self.app.go_menu()
        elif ev.key == pygame.K_r:
            self.app.start_play()
        elif ev.key == pygame.K_p:
            self.toggle_pause()
        elif ev.key == pygame.K_SPACE:
            self.do_skip()

    def do_skip(self):
        if self.skip_to is not None and self.now() < self.skip_to:
            self.seek(self.skip_to)
            self.skip_to = None

    def update(self):
        if self.paused:
            return
        t = self.now()
        if self.skip_to is not None and time.perf_counter() >= self.auto_skip_at:
            self.do_skip()  # the bot presses "skip" by itself
            t = self.now()
        if not self.music_started and t >= 0:
            self._start_music(t)
        evs = self.sound_events
        limit = self.play.fail_time if self.play.failed else float("inf")
        while self.sound_idx < len(evs) and evs[self.sound_idx][0] <= min(t, limit):
            et, kind = evs[self.sound_idx]
            self.sound_idx += 1
            if self.app.settings["hitsounds"] and t - et < 80:
                snd = self.app.tick_sound if kind == "tick" else self.app.hit_sound
                if snd:
                    snd.play()
        if self.play.failed and t >= self.play.fail_time and self.failed_real is None:
            self.failed_real = time.perf_counter()
            self._stop_music(1500)
        if self.failed_real and time.perf_counter() - self.failed_real > 2.6:
            self.finish()
        elif not self.play.failed and t > self.play.end_time + 1500:
            self.finish()

    def finish(self):
        if self.finished:
            return
        self.finished = True
        self._stop_music(800)
        from .results import ResultScene
        self.app.scene = ResultScene(self.app, self)

    # --- drawing -------------------------------------------------------------------
    def in_break(self, t):
        if t < self.first_time() - self.bm.preempt or t > self.last_time() + 200:
            return True
        return any(s + 300 <= t <= e - 600 for s, e in self.bm.breaks)

    def draw(self, surf):
        t = self.now()
        if self.play.failed and t > self.play.fail_time:
            t = self.play.fail_time
        self.draw_background(surf, t)
        self.draw_playfield(surf, t)
        self.draw_hud(surf, t)
        tx = self.app.text
        if self.failed_real:
            k = min(1.0, (time.perf_counter() - self.failed_real) / 1.2)
            self.overlay.fill((60, 0, 0, int(150 * k)))
            surf.blit(self.overlay, (0, 0))
            tx.draw(surf, "ПРОВАЛ", int(80 + 40 * k), (255, 90, 90), (640, 360), "center",
                    weight="black")
        if self.paused:
            self.overlay.fill((0, 0, 0, 150))
            surf.blit(self.overlay, (0, 0))
            tx.draw(surf, "ПАУЗА  (P — продовжити)", 56, WHITE, (640, 360), "center")

    def draw_background(self, surf, t):
        dim = self.app.settings["dim"] / 100
        target = dim * 0.45 if self.in_break(t) else dim
        self.dim_now += (target - self.dim_now) * 0.05
        fade_in = max(0.0, 1 - (time.perf_counter() - self.real_start) / 0.8)
        surf.blit(self.background, (0, 0))
        a = max(self.dim_now, fade_in)
        if a > 0.004:
            self.dim_surf.set_alpha(int(255 * min(1.0, a)))
            surf.blit(self.dim_surf, (0, 0))
        if self.in_break(t) and self.first_time() < t < self.last_time():
            self.app.text.draw(surf, "ПЕРЕРВА", 44, WHITE, (640, 300), "center", 200)

    def draw_playfield(self, surf, t):
        pass

    def mode_label(self):
        play = self.play
        mode = f"Ціль: {play.target}" if play.mode == "grade" else f"Скіл {int(play.skill)}/10"
        mods = " +" + "".join(sorted(self.bm.mods)) if self.bm.mods else ""
        ruleset = "osu!catch" if play.ruleset == "catch" else "osu!"
        return f"BOT Claude  •  {ruleset}  •  {mode}{mods}"

    def draw_hud(self, surf, t):
        tx = self.app.text
        play = self.play
        snap = play.snapshot_at(t)
        self.hp_shown += (snap.hp - self.hp_shown) * 0.15
        rect(surf, (0, 0, 0), (20, 16, 420, 18), radius=9)
        hp_col = mix((255, 70, 70), (120, 240, 140), min(1, self.hp_shown * 1.5))
        rect(surf, hp_col, (22, 18, max(1, 416 * self.hp_shown), 14), radius=7)
        first, last = self.first_time(), self.last_time()
        prog = min(1.0, max(0.0, (t - first) / max(1, last - first)))
        rect(surf, (60, 60, 80), (20, 40, 420, 5), radius=3)
        rect(surf, (200, 200, 230), (20, 40, max(1, 420 * prog), 5), radius=3)
        surf.blit(self.avatar, view.p(20, 52))
        tx.draw(surf, self.mode_label(), 26, ACCENT, (58, 56))
        tx.draw(surf, f"{snap.score:08d}", 58, WHITE, (1260, 6), "topright", weight="black")
        acc = play.acc_of(snap.counts)
        tx.draw(surf, f"{acc * 100:.2f}%", 36, WHITE, (1260, 58), "topright")
        g = play.grade_of(snap.counts)
        tx.draw(surf, g, 38, GRADE_COLOURS[g], (1135, 56), "topright", weight="black")
        tx.draw(surf, f"{snap.combo}x", 72, WHITE, (20, 712), "bottomleft", weight="black")
        info = self.bm.info
        tx.draw(surf, f"{info.artist} - {info.title} [{info.version}]"[:70], 22, MUTED,
                (1260, 712), "bottomright")
        if self.music_note:
            tx.draw(surf, f"Музика: {self.music_note}", 22, MUTED, (1260, 690), "bottomright")
        if self.skip_to is not None and t < self.skip_to:
            tx.draw(surf, "SPACE — пропустити вступ", 32, WHITE, (1240, 630), "bottomright")


# ----------------------------------------------------------------------------
# osu!standard
# ----------------------------------------------------------------------------

class Sprites:
    def __init__(self, bm, text):
        self.r = bm.radius * view.pf_scale
        self.circles = [self._circle(c) for c in bm.colours]
        self.approach = [self._ring(c) for c in bm.colours]
        self.numbers = {}
        self.font = text.font_px(max(10, int(self.r * 1.15)), "black")
        self.cursor = self._cursor()
        self.trail = self._dot(max(2, int(self.r * 0.32)), (255, 200, 120))
        self.follow = self._ring((255, 255, 255), base=max(8, int(self.r * FOLLOW_SCALE * 2)),
                                 width=0.05)
        self.ball = self._ball()

    def _circle(self, colour):
        R = int(self.r * 2)
        size = R * 2 + 8
        s = pygame.Surface((size, size), pygame.SRCALPHA)
        c = size // 2
        pygame.draw.circle(s, (0, 0, 0, 110), (c, c + 3), R)
        steps = 14
        for k in range(steps):
            f = k / (steps - 1)
            pygame.draw.circle(s, mix(mix(colour, (0, 0, 0), 0.45), colour, f) + (255,),
                               (c, c), R * (0.92 - 0.55 * f))
        pygame.draw.circle(s, (255, 255, 255, 255), (c, c), R * 0.96, max(2, int(R * 0.12)))
        out = int(self.r * 2) + 4
        return pygame.transform.smoothscale(s, (out, out))

    def _ring(self, colour, base=256, width=0.04):
        big = base * 2
        s = pygame.Surface((big, big), pygame.SRCALPHA)
        pygame.draw.circle(s, colour + (255,), (base, base), base - 2, max(2, int(big * width)))
        return pygame.transform.smoothscale(s, (base, base))

    def _cursor(self):
        size = max(8, int(self.r * 1.3))
        big = size * 2
        s = pygame.Surface((big, big), pygame.SRCALPHA)
        c = big // 2
        for k in range(10):
            pygame.draw.circle(s, (255, 170, 60, 12 + k * 8), (c, c), c * (1 - k * 0.07))
        pygame.draw.circle(s, (255, 230, 170, 255), (c, c), c * 0.42)
        pygame.draw.circle(s, (255, 255, 255, 255), (c, c), c * 0.42, max(2, int(c * 0.08)))
        return pygame.transform.smoothscale(s, (size, size))

    def _dot(self, radius, colour):
        s = pygame.Surface((radius * 2 + 2, radius * 2 + 2), pygame.SRCALPHA)
        pygame.draw.circle(s, colour + (255,), (radius + 1, radius + 1), radius)
        return s

    def _ball(self):
        R = int(self.r * 2)
        size = R * 2 + 4
        s = pygame.Surface((size, size), pygame.SRCALPHA)
        c = size // 2
        pygame.draw.circle(s, (255, 255, 255, 255), (c, c), R * 0.85)
        pygame.draw.circle(s, (255, 140, 200, 255), (c, c), R * 0.68)
        out = int(self.r * 2)
        return pygame.transform.smoothscale(s, (out, out))

    def number(self, n):
        surf = self.numbers.get(n)
        if surf is None:
            surf = self.numbers[n] = self.font.render(str(n), True, WHITE)
        return surf


class StdPlayScene(BasePlayScene):
    def __init__(self, app, bm, play):
        super().__init__(app, bm, play)
        self.judges = [e for e in play.events if e.kind == "judge"]
        self.judge_times = [e.time for e in self.judges]
        self.sound_events = [(e.time, "tick" if e.sub == "tick" else "hit")
                             for e in play.events
                             if e.value and (e.kind == "judge" and bm.objects[e.obj].kind != "slider"
                                             or e.kind == "part")]
        self.err_times = [e[0] for e in play.hit_errors]
        self.on_resize()

    def build_sprites(self):
        self.sprites = Sprites(self.bm, self.app.text)
        self.slider_cache = {}

    # --- playfield --------------------------------------------------------------
    def draw_playfield(self, surf, t):
        self.draw_objects(surf, t)
        self.draw_judgements(surf, t)
        self.draw_cursor(surf, t)
        self.draw_keys(surf, t)
        self.draw_error_bar(surf, t)

    def slider_surface(self, i, obj):
        cached = self.slider_cache.get(i)
        if cached:
            return cached
        R = self.sprites.r
        length = obj.path.length
        step = max(2.5 / view.pf_scale, length / 1200)
        pts = []
        d = 0.0
        while d <= length:
            pts.append(view.pf(obj.path_pos(d / length)))
            d += step
        pts.append(view.pf(obj.path_pos(1.0)))
        minx = min(p[0] for p in pts) - R - 4
        miny = min(p[1] for p in pts) - R - 4
        maxx = max(p[0] for p in pts) + R + 4
        maxy = max(p[1] for p in pts) + R + 4
        s = pygame.Surface((int(maxx - minx) + 1, int(maxy - miny) + 1), pygame.SRCALPHA)
        local = [(p[0] - minx, p[1] - miny) for p in pts]
        colour = self.bm.colours[obj.colour_index]
        for p in local:
            pygame.draw.circle(s, (255, 255, 255, 255), p, R)
        layers = 9
        for k in range(layers):
            f = k / (layers - 1)
            col = mix(mix(colour, (0, 0, 0), 0.7), mix(colour, (0, 0, 0), 0.25), f) + (255,)
            rr = R * (0.87 - 0.6 * f)
            for p in local:
                pygame.draw.circle(s, col, p, rr)
        self.slider_cache[i] = (s, (minx, miny))
        return self.slider_cache[i]

    def visible(self, t):
        out = []
        pre = self.bm.preempt
        for i, o in enumerate(self.bm.objects):
            if o.time - pre > t:
                break
            if o.end_time + 800 >= t:
                out.append(i)
        return out

    def draw_objects(self, surf, t):
        bm = self.bm
        sp = self.sprites
        objs = bm.objects
        res = self.play.results
        for i in reversed(self.visible(t)):
            o = objs[i]
            r = res[i]
            fade = min(1.0, (t - (o.time - bm.preempt)) / bm.fade_in)
            if o.kind == "spinner":
                self.draw_spinner(surf, t, o, r)
                continue
            if o.kind == "slider":
                end_fade = 1.0 if t <= o.end_time else max(0.0, 1 - (t - o.end_time) / 220)
                if end_fade <= 0:
                    continue
                body, (bx, by) = self.slider_surface(i, o)
                body.set_alpha(int(210 * fade * end_fade))
                surf.blit(body, (bx, by))
                body.set_alpha(255)
                a = 255 * fade * end_fade
                blit_centered(surf, sp.circles[o.colour_index], view.pf(o.path_pos(1.0)), a * 0.8)
                for p in o.parts:
                    if p.kind == "tick" and p.time > t:
                        pygame.draw.circle(surf, WHITE, view.pf(o.path_pos(p.progress)),
                                           max(2, sp.r * 0.13))
                if o.slides > 1 and t < o.end_time:
                    span = int(max(0, t - o.time) / o.span_duration) if t > o.time else 0
                    if span < o.slides - 1:
                        self.draw_arrow(surf, o, span % 2 == 0)
                    if span < o.slides - 2:
                        self.draw_arrow(surf, o, span % 2 != 0)
                head_done = r.head_hit and t >= r.head_time
                head_gone = t >= getattr(r, "head_judge_time", o.time)
                if not head_gone or (head_done and t < r.head_time + 220):
                    self.draw_circle(surf, t, o, fade, r.head_time if r.head_hit else None,
                                     o.time + bm.w50)
                if o.time <= t <= o.end_time:
                    bpos = view.pf(o.ball(t))
                    blit_centered(surf, sp.ball, bpos)
                    if r.release is not None and r.head_time <= t <= r.release:
                        blit_centered(surf, sp.follow, bpos, 200)
                continue
            if t > r.judge_time + 240:
                continue
            self.draw_circle(surf, t, o, fade, r.judge_time if r.hit else None, r.judge_time)

    def draw_arrow(self, surf, o, at_end):
        if at_end:
            p = o.path_pos(1.0)
            q = o.path_pos(max(0.0, 1.0 - 4 / o.path.length))
        else:
            p = o.path_pos(0.0)
            q = o.path_pos(min(1.0, 4 / o.path.length))
        ang = math.atan2(q[1] - p[1], q[0] - p[0])
        c = view.pf(p)
        R = self.sprites.r * 0.5
        pts = [(c[0] + math.cos(ang + a) * R * k, c[1] + math.sin(ang + a) * R * k)
               for a, k in ((0, 1.0), (2.4, 0.9), (-2.4, 0.9))]
        pygame.draw.polygon(surf, WHITE, pts)

    def draw_circle(self, surf, t, o, fade, hit_time, miss_time):
        bm = self.bm
        sp = self.sprites
        pos = view.pf(o.pos)
        alpha = 255 * fade
        scale = 1.0
        if hit_time is not None and t >= hit_time:
            k = min(1.0, (t - hit_time) / 220)
            alpha = 255 * (1 - k)
            scale = 1 + 0.4 * k
        elif hit_time is None and t >= miss_time:
            k = min(1.0, (t - miss_time) / 160)
            alpha = 255 * fade * (1 - k)
        if alpha <= 1:
            return
        blit_centered(surf, sp.circles[o.colour_index], pos, alpha, scale)
        if scale == 1.0:
            blit_centered(surf, sp.number(o.combo_number), pos, alpha)
        if t < o.time and (hit_time is None or t < hit_time):
            f = (o.time - t) / bm.preempt
            size = sp.r * 2 * (1 + 3 * f) * 1.05
            img = pygame.transform.smoothscale(sp.approach[o.colour_index], (int(size), int(size)))
            blit_centered(surf, img, pos, min(255, alpha * 0.9))

    def draw_spinner(self, surf, t, o, r):
        tx = self.app.text
        if t < o.time - 300:
            return
        a = min(1.0, (t - (o.time - 300)) / 300)
        if t > o.end_time:
            a *= max(0.0, 1 - (t - o.end_time) / 300)
        if a <= 0:
            return
        c = view.pf((256, 192))
        c = (int(c[0]), int(c[1]))
        big = int(view.s(250))
        ov = self.overlay
        ov.fill((0, 0, 0, 0))
        pygame.draw.circle(ov, (20, 20, 40, int(170 * a)), c, big)
        pygame.draw.circle(ov, (255, 255, 255, int(220 * a)), c, big, max(2, int(view.s(4))))
        start, stop, omega, required = r.spin
        tt = min(max(t, start), stop)
        spun = omega * (tt - start)
        rot = spun / (2 * math.pi)
        prog = min(1.0, rot / required) if required else 1.0
        inner = view.s(40)
        for k in range(8):
            ang = spun + k * math.pi / 4
            p1 = (c[0] + math.cos(ang) * inner, c[1] + math.sin(ang) * inner)
            p2 = (c[0] + math.cos(ang) * (big - view.s(14)), c[1] + math.sin(ang) * (big - view.s(14)))
            pygame.draw.line(ov, (255, 140, 200, int(160 * a)), p1, p2, max(1, int(view.s(3))))
        if o.time <= t <= o.end_time:
            rem = 1 - (t - o.time) / (o.end_time - o.time)
            pygame.draw.circle(ov, (120, 200, 255, int(220 * a)), c, max(6, int(big * rem)),
                               max(2, int(view.s(3))))
        arc = pygame.Rect(0, 0, big * 2 + view.s(30), big * 2 + view.s(30))
        arc.center = c
        if prog > 0:
            pygame.draw.arc(ov, (120, 255, 150, int(255 * a)), arc, math.pi / 2,
                            math.pi / 2 + 2 * math.pi * prog, max(2, int(view.s(8))))
        surf.blit(ov, (0, 0))
        ov.fill((0, 0, 0, 0))
        rpm = omega * 60000 / (2 * math.pi) if start <= t <= stop else 0
        label = "ГОТОВО!" if prog >= 1 else "КРУТИ!"
        tx.draw(surf, label, 52, WHITE, (c[0], c[1] - view.s(40)), "center", 255 * a,
                weight="black", screen=True)
        tx.draw(surf, f"{rot:.1f} / {required} обертів", 30, WHITE, (c[0], c[1] + view.s(10)),
                "center", 255 * a, screen=True)
        tx.draw(surf, f"RPM {rpm:.0f}", 30, MUTED, (c[0], c[1] + big + view.s(30)), "center",
                255 * a, screen=True)

    def draw_judgements(self, surf, t):
        tx = self.app.text
        lo = bisect.bisect_left(self.judge_times, t - 700)
        hi = bisect.bisect_right(self.judge_times, t)
        for e in self.judges[lo:hi]:
            age = t - e.time
            a = 255 * (1 - age / 700)
            pos = view.pf(e.pos)
            if self.bm.objects[e.obj].kind == "spinner":
                pos = view.pf((256, 192 + 60))
            col = JUDGE_COLOURS[e.value]
            if e.value == 0:
                s = view.s(14 + age * 0.02)
                y = pos[1] + view.s(age * 0.04)
                w = max(2, int(view.s(6)))
                pygame.draw.line(surf, col, (pos[0] - s, y - s), (pos[0] + s, y + s), w)
                pygame.draw.line(surf, col, (pos[0] - s, y + s), (pos[0] + s, y - s), w)
            elif e.value == 300:
                if age < 300:
                    tx.draw(surf, "300", 26, col, pos, "center", 100 * (1 - age / 300), screen=True)
            else:
                tx.draw(surf, str(e.value), 40, col, (pos[0], pos[1] - view.s(age * 0.02)), "center",
                        a, weight="black", screen=True)

    def draw_cursor(self, surf, t):
        sp = self.sprites
        cur = self.play.cursor
        if self.app.settings["trail"]:
            n = 26
            for k in range(n, 0, -1):
                p = view.pf(cur.at(t - k * 5 * self.bm.rate))
                blit_centered(surf, sp.trail, p, 140 * (1 - k / n) ** 1.5, 1 - 0.5 * k / n)
        blit_centered(surf, sp.cursor, view.pf(cur.at(t)))

    def draw_keys(self, surf, t):
        tx = self.app.text
        keys = self.play.keys
        down = keys.keys_down(t)
        for k in range(2):
            r = (1204, 300 + k * 66, 58, 58)
            rect(surf, ACCENT if down[k] else (40, 36, 60), r, radius=8)
            rect(surf, WHITE, r, 2, radius=8)
            cnt = keys.count_before(t, k)
            tx.draw(surf, f"K{k + 1}" if cnt == 0 else str(cnt), 26, WHITE, (1233, 329 + k * 66),
                    "center")
        n300, n100, n50, nm = self.play.snapshot_at(t).counts
        tx.draw(surf, f"100: {n100}   50: {n50}   X: {nm}", 26, MUTED, (1260, 98), "topright")

    def draw_error_bar(self, surf, t):
        bm = self.bm
        cx, y = 640, 696
        k = 1.4
        w50 = bm.w50 * k
        for w, col in ((bm.w50, (230, 170, 60)), (bm.w100, (100, 210, 90)), (bm.w300, (80, 170, 255))):
            rect(surf, col, (cx - w * k, y - 3, 2 * w * k, 6))
        rect(surf, WHITE, (cx - 1, y - 12, 3, 24))
        errs = self.play.hit_errors
        lo = bisect.bisect_left(self.err_times, t - 6000)
        hi = bisect.bisect_right(self.err_times, t)
        for et, e in errs[lo:hi]:
            a = 1 - (t - et) / 6000
            x = cx + max(-w50, min(w50, e * k))
            pygame.draw.line(surf, mix((20, 20, 30), WHITE, a), view.p(x, y - 10), view.p(x, y + 10),
                             max(1, int(view.s(2))))
