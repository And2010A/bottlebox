"""osu!catch playback scene."""

import bisect
import math

import pygame

from .catch import DASH_SPEED, DROPLET, FRUIT, TINY
from .play import BasePlayScene
from .ui import ACCENT, MUTED, WHITE, blit_centered, mix, rect, view

Y_TOP = -30      # where fruits appear (osu! pixels)
PLATE_Y = 340    # height of the catcher plate


class CatchPlayScene(BasePlayScene):
    def __init__(self, app, bm, play):
        super().__init__(app, bm, play)
        self.times = [o.time for o in play.objects]
        self.sound_events = [(o.time, "hit" if o.kind == FRUIT else "tick")
                             for o, c in zip(play.objects, play.caught)
                             if c and o.kind != TINY]
        self.on_resize()

    def first_time(self):
        return self.play.objects[0].time if self.play.objects else super().first_time()

    def last_time(self):
        return self.play.objects[-1].time if self.play.objects else super().last_time()

    # --- sprites --------------------------------------------------------------
    def build_sprites(self):
        sc = view.pf_scale
        self.rf = self.play.half * 0.5 * sc  # fruit radius in screen px
        cols = self.bm.colours
        self.fruit = [self._fruit(c, False) for c in cols]
        self.fruit_hyper = [self._fruit(c, True) for c in cols]
        self.droplet = [self._ball(c, 0.55) for c in cols]
        self.tiny = [self._ball(c, 0.3) for c in cols]
        self.banana = self._banana()
        self.catcher = self._catcher((255, 120, 185))
        self.catcher_hyper = self._catcher((255, 60, 60))
        self.ghost = self._catcher((255, 255, 255))
        self.ghost_hyper = self._catcher((255, 60, 60))

    def _fruit(self, colour, hyper):
        R = int(self.rf * 2)
        size = int(R * 2.8)
        s = pygame.Surface((size, size), pygame.SRCALPHA)
        c = size // 2
        if hyper:
            for k in range(8):
                pygame.draw.circle(s, (255, 40, 40, 18 + k * 10), (c, c), R * (1.35 - k * 0.04))
        pygame.draw.circle(s, mix(colour, (0, 0, 0), 0.55) + (255,), (c, c), R)
        for k in range(10):
            f = k / 9
            pygame.draw.circle(s, mix(mix(colour, (0, 0, 0), 0.25), mix(colour, WHITE, 0.35), f)
                               + (255,), (c - R * 0.12 * f, c - R * 0.12 * f), R * (0.9 - 0.5 * f))
        pygame.draw.ellipse(s, (255, 255, 255, 170),
                            (c - R * 0.55, c - R * 0.62, R * 0.45, R * 0.3))
        leaf = pygame.Rect(0, 0, R * 0.6, R * 0.3)
        leaf.center = (c + R * 0.25, c - R * 0.95)
        pygame.draw.ellipse(s, (90, 200, 90, 255), leaf)
        out = int(self.rf * 2.8)
        return pygame.transform.smoothscale(s, (out, out))

    def _ball(self, colour, k):
        R = max(2, int(self.rf * k * 2))
        s = pygame.Surface((R * 2 + 4, R * 2 + 4), pygame.SRCALPHA)
        c = R + 2
        pygame.draw.circle(s, mix(colour, (0, 0, 0), 0.5) + (255,), (c, c), R)
        pygame.draw.circle(s, mix(colour, WHITE, 0.25) + (255,), (c, c), R * 0.75)
        out = max(3, R + 2)
        return pygame.transform.smoothscale(s, (out, out))

    def _banana(self):
        R = int(self.rf * 2)
        size = R * 2 + 8
        s = pygame.Surface((size, size), pygame.SRCALPHA)
        r = pygame.Rect(0, 0, R * 1.8, R * 1.8)
        r.center = (size // 2, size // 2)
        pygame.draw.arc(s, (120, 90, 20, 255), r, math.pi * 1.05, math.pi * 1.95, max(3, int(R * 0.5)))
        pygame.draw.arc(s, (255, 225, 70, 255), r.inflate(-R * 0.15, -R * 0.15), math.pi * 1.1,
                        math.pi * 1.9, max(2, int(R * 0.36)))
        out = int(self.rf * 2.2)
        return pygame.transform.smoothscale(s, (out, out))

    def _catcher(self, colour):
        w = max(16, int(self.play.width / 0.8 * view.pf_scale))
        h = int(w * 0.62)
        big_w, big_h = w * 2, h * 2
        s = pygame.Surface((big_w, big_h), pygame.SRCALPHA)
        plate_h = big_h * 0.14
        pygame.draw.rect(s, (245, 245, 255, 255), (0, 0, big_w, plate_h), border_radius=int(plate_h / 2))
        body = pygame.Rect(big_w * 0.18, plate_h * 0.7, big_w * 0.64, big_h - plate_h * 0.7)
        pygame.draw.rect(s, colour + (255,), body, border_radius=int(big_w * 0.12))
        pygame.draw.rect(s, (255, 255, 255, 255), body, max(2, int(big_w * 0.02)),
                         border_radius=int(big_w * 0.12))
        for dx in (-1, 1):
            e = pygame.Rect(0, 0, big_w * 0.07, big_h * 0.2)
            e.center = (big_w / 2 + dx * big_w * 0.1, body.centery - big_h * 0.06)
            pygame.draw.ellipse(s, (255, 255, 255, 255), e)
        mouth = pygame.Rect(0, 0, big_w * 0.2, big_h * 0.2)
        mouth.center = (big_w / 2, body.centery + big_h * 0.08)
        pygame.draw.arc(s, (255, 255, 255, 255), mouth, math.pi * 1.15, math.pi * 1.85,
                        max(2, int(big_w * 0.02)))
        return pygame.transform.smoothscale(s, (w, h))

    # --- geometry --------------------------------------------------------------
    def fall_y(self, o, t):
        return PLATE_Y - (o.time - t) / self.bm.preempt * (PLATE_Y - Y_TOP)

    def catcher_screen(self, x):
        p = view.pf((x, PLATE_Y))
        return p

    # --- drawing -----------------------------------------------------------------
    def draw_playfield(self, surf, t):
        play = self.play
        objs = play.objects
        pre = self.bm.preempt
        lo = bisect.bisect_left(self.times, t - 600)
        hi = bisect.bisect_right(self.times, t + pre)
        # falling objects (far ones first)
        for i in range(hi - 1, lo - 1, -1):
            o = objs[i]
            caught = play.caught[i]
            if t > o.time and caught:
                continue
            y = self.fall_y(o, t)
            alpha = min(255, 255 * (t - (o.time - pre)) / 200)
            if t > o.time:
                alpha *= max(0.0, 1 - (t - o.time) / 400)
            if alpha <= 0:
                continue
            pos = view.pf((o.x, y))
            if o.kind == FRUIT:
                img = (self.fruit_hyper if o.hyper else self.fruit)[o.colour_index]
            elif o.kind == DROPLET:
                img = self.droplet[o.colour_index]
            elif o.kind == TINY:
                img = self.tiny[o.colour_index]
            else:
                img = self.banana
            blit_centered(surf, img, pos, alpha)
        self.draw_catcher(surf, t, lo, hi)
        self.draw_keys(surf, t)

    def draw_catcher(self, surf, t, lo, hi):
        play = self.play
        x, speed = play.catcher_at(t)
        hyper = speed > DASH_SPEED + 1e-6
        dashing = speed >= DASH_SPEED - 1e-6
        cw, ch = self.catcher.get_size()
        # afterimages while dashing / hyperdashing
        if dashing:
            ghost = self.ghost_hyper if hyper else self.ghost
            for k in range(5, 0, -1):
                gx, _ = play.catcher_at(t - k * 22)
                gp = self.catcher_screen(gx)
                ghost.set_alpha(int((110 if hyper else 70) * (1 - k / 6)))
                surf.blit(ghost, (gp[0] - cw / 2, gp[1]))
            ghost.set_alpha(255)
        # fruits stacked on the plate
        p = self.catcher_screen(x)
        recent_lo = bisect.bisect_left(self.times, t - 1500)
        stacked = 0
        idx = bisect.bisect_right(self.times, t) - 1
        while idx >= recent_lo and stacked < 14:
            o = play.objects[idx]
            if o.time <= t and play.caught[idx] and o.kind in (FRUIT, DROPLET):
                if o.combo_end and o.time < t - 300:
                    break
                off = (o.x - play.catch_pos[idx]) * view.pf_scale
                off = max(-cw * 0.42, min(cw * 0.42, off))
                img = self.fruit[o.colour_index] if o.kind == FRUIT else self.droplet[o.colour_index]
                blit_centered(surf, img, (p[0] + off, p[1] - self.rf * 0.6 - (stacked % 3) * 3),
                              230, 0.55)
                stacked += 1
            idx -= 1
        img = self.catcher_hyper if hyper else self.catcher
        surf.blit(img, (p[0] - cw / 2, p[1]))
        # catch flash
        idx = bisect.bisect_right(self.times, t) - 1
        while idx >= 0 and t - play.objects[idx].time < 160:
            o = play.objects[idx]
            if play.caught[idx] and o.kind == FRUIT:
                k = (t - o.time) / 160
                fx = p[0] + (o.x - play.catch_pos[idx]) * view.pf_scale
                pygame.draw.circle(surf, (255, 255, 255), (fx, p[1]), self.rf * (0.6 + 1.2 * k),
                                   max(1, int(3 * (1 - k)) + 1))
            idx -= 1

    def draw_keys(self, surf, t):
        tx = self.app.text
        play = self.play
        x0, _ = play.catcher_at(t - 16)
        x1, speed = play.catcher_at(t)
        left = x1 < x0 - 0.01
        right = x1 > x0 + 0.01
        dash = speed >= DASH_SPEED - 1e-6
        boxes = [("left", left), ("right", right), ("DASH", dash)]
        for k, (name, on) in enumerate(boxes):
            r = (1204, 260 + k * 66, 58, 58)
            rect(surf, ACCENT if on else (40, 36, 60), r, radius=8)
            rect(surf, WHITE, r, 2, radius=8)
            c = view.p(1233, 289 + k * 66)
            s = view.s(13)
            if name == "left":
                pygame.draw.polygon(surf, WHITE, [(c[0] - s, c[1]), (c[0] + s, c[1] - s), (c[0] + s, c[1] + s)])
            elif name == "right":
                pygame.draw.polygon(surf, WHITE, [(c[0] + s, c[1]), (c[0] - s, c[1] - s), (c[0] - s, c[1] + s)])
            else:
                tx.draw(surf, "DASH", 20, WHITE, (1233, 289 + k * 66), "center")
        counts = play.snapshot_at(t).counts
        misses = counts[3] + counts[4] + counts[5]
        tx.draw(surf, f"Промахи: {misses}   Банани: {counts[6]}", 26, MUTED, (1260, 98), "topright")
