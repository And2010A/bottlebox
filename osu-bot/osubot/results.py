"""Results screen."""

import time

import pygame

from .play import JUDGE_COLOURS
from .ui import ACCENT, GRADE_COLOURS, MUTED, WHITE, Button, rect, view

SKILL_TEXT = ["Новачок", "Новачок", "Аматор", "Аматор", "Досвідчений", "Досвідчений",
              "Профі", "Профі", "Топ-гравець", "Майже Auto"]


class ResultScene:
    def __init__(self, app, scene):
        self.app = app
        self.scene = scene
        self.play = scene.play
        self.bm = scene.bm
        self.t0 = time.perf_counter()
        self.buttons = [
            Button((760, 610, 230, 64), "Ще раз (R)", app.start_play, colour=ACCENT),
            Button((1010, 610, 230, 64), "Меню (Esc)", app.go_menu),
        ]

    def on_resize(self):
        self.scene.on_resize()

    def handle(self, ev):
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            pos = view.to_logical(ev.pos)
            for b in self.buttons:
                if b.click(pos):
                    return
        elif ev.type == pygame.KEYDOWN:
            if ev.key == pygame.K_r:
                self.app.start_play()
            elif ev.key in (pygame.K_ESCAPE, pygame.K_RETURN):
                self.app.go_menu()

    def update(self):
        pass

    def rows(self):
        c = self.play.final.counts
        if self.play.ruleset == "catch":
            fr, dr, tn = (c[0], c[0] + c[3]), (c[1], c[1] + c[4]), (c[2], c[2] + c[5])
            return [("Фрукти", f"{fr[0]}/{fr[1]}", (255, 150, 120)),
                    ("Краплі", f"{dr[0]}/{dr[1]}", (120, 200, 255)),
                    ("Дрібні краплі", f"{tn[0]}/{tn[1]}", (160, 230, 160)),
                    ("Банани", f"{c[6]}", (255, 225, 70))]
        n300, n100, n50, nm = c
        return [("300", f"{n300}x", JUDGE_COLOURS[300]), ("100", f"{n100}x", JUDGE_COLOURS[100]),
                ("50", f"{n50}x", JUDGE_COLOURS[50]), ("Промах", f"{nm}x", JUDGE_COLOURS[0])]

    def draw(self, surf):
        tx = self.app.text
        play = self.play
        bm = self.bm
        sc = self.scene
        surf.blit(sc.background, (0, 0))
        sc.dim_surf.set_alpha(int(255 * max(0.6, self.app.settings["dim"] / 100)))
        surf.blit(sc.dim_surf, (0, 0))
        k = min(1.0, (time.perf_counter() - self.t0) / 0.6)
        info = bm.info
        tx.draw(surf, f"{info.artist} - {info.title}"[:60], 40, WHITE, (40, 26), weight="black")
        tx.draw(surf, f"[{info.version}]  мапер: {info.creator}"[:70], 28, ACCENT, (40, 74))
        mods = ", ".join(sorted(bm.mods)) or "без модів"
        mode = f"ціль — ранг {play.target}" if play.mode == "grade" else \
            f"скіл {int(play.skill)}/10 ({SKILL_TEXT[int(play.skill) - 1]})"
        ruleset = "osu!catch" if play.ruleset == "catch" else "osu!"
        tx.draw(surf, f"Бот Claude • {ruleset} • {mode} • моди: {mods}", 26, MUTED, (40, 108))

        rect(surf, (16, 12, 28), (40, 150, 640, 440), radius=16)
        for r, (name, v, col) in enumerate(self.rows()):
            x = 70 + (r % 2) * 310
            y = 176 + (r // 2) * 92
            tx.draw(surf, name, 30, col, (x, y))
            tx.draw(surf, v, 52, WHITE, (x, y + 30), weight="black")
        tx.draw(surf, "Очки", 28, MUTED, (70, 372))
        tx.draw(surf, f"{play.final.score:,}".replace(",", " "), 50, WHITE, (70, 400), weight="black")
        tx.draw(surf, "Макс. комбо", 28, MUTED, (380, 372))
        tx.draw(surf, f"{play.final.max_combo}x / {play.max_combo_possible()}x", 44, WHITE,
                (380, 404), weight="black")
        tx.draw(surf, "Точність", 28, MUTED, (70, 472))
        tx.draw(surf, f"{play.accuracy * 100:.2f}%", 50, WHITE, (70, 500), weight="black")
        if play.unstable_rate is not None:
            tx.draw(surf, "Unstable Rate", 28, MUTED, (380, 472))
            tx.draw(surf, f"{play.unstable_rate:.1f}", 44, WHITE, (380, 504), weight="black")

        g = play.grade
        tx.draw(surf, g, 300, GRADE_COLOURS[g], (960, 330 + 30 * (1 - k)), "center", 255 * k,
                weight="black")
        if play.failed:
            msg, col = "Бот втратив усе HP — карту провалено", (255, 120, 120)
        elif play.mode == "grade":
            ok = g == play.target
            msg = "Ціль виконано!" if ok else f"Ціль була {play.target}"
            col = (130, 240, 140) if ok else (255, 190, 90)
        else:
            msg, col = None, None
        if msg:
            tx.draw(surf, msg, 34, col, (960, 540), "center")
        mouse = view.to_logical(pygame.mouse.get_pos())
        for b in self.buttons:
            b.draw(surf, tx, mouse)
