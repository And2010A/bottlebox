"""pygame front-end: menu, playback of the bot's play, and results screen."""

import math
import os
import random
import sys
import time

import pygame

from .beatmap import Beatmap, as_file, list_difficulties
from .demo import demo_osu
from .sim import GRADES, Play, accuracy, grade_of

W, H = 1280, 720
SCALE = H * 0.8 / 384
OX = (W - 512 * SCALE) / 2
OY = (H - 384 * SCALE) / 2 + 10

WHITE = (255, 255, 255)
BG = (18, 14, 30)
PANEL = (34, 28, 54)
PANEL_HI = (52, 44, 82)
ACCENT = (255, 102, 170)
MUTED = (160, 150, 190)

GRADE_COLOURS = {
    "SS": (255, 222, 90), "S": (255, 190, 60), "A": (120, 225, 95), "B": (85, 165, 255),
    "C": (200, 115, 255), "D": (255, 85, 85), "F": (150, 150, 165),
}
GRADE_TEXT = {
    "SS": "100% точність — ідеально, як Auto",
    "S": "понад 90% «300», жодного промаху",
    "A": "понад 80% «300», без промахів",
    "B": "понад 70% «300», без промахів",
    "C": "понад 60% «300», трохи промахів",
    "D": "багато помилок, але карту пройдено",
    "F": "провал — бот втрачає все HP",
}
SKILL_TEXT = ["Новачок", "Новачок", "Аматор", "Аматор", "Досвідчений", "Досвідчений",
              "Профі", "Профі", "Топ-гравець", "Майже Auto"]
MOD_TEXT = {"EZ": "Easy", "HT": "Half Time", "HR": "Hard Rock", "DT": "Double Time",
            "NF": "No Fail"}
JUDGE_COLOURS = {300: (110, 190, 255), 100: (120, 230, 100), 50: (255, 190, 70), 0: (255, 60, 60)}


def to_screen(p):
    return (OX + p[0] * SCALE, OY + p[1] * SCALE)


def mix(c, d, f):
    return tuple(int(c[i] + (d[i] - c[i]) * f) for i in range(3))


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------

class Text:
    def __init__(self):
        self.fonts = {}
        self.cache = {}

    def font(self, size):
        f = self.fonts.get(size)
        if f is None:
            f = self.fonts[size] = pygame.font.Font(None, size)
        return f

    def render(self, s, size, colour=WHITE):
        key = (s, size, colour)
        surf = self.cache.get(key)
        if surf is None:
            if len(self.cache) > 800:
                self.cache.clear()
            surf = self.cache[key] = self.font(size).render(str(s), True, colour)
        return surf

    def draw(self, target, s, size, colour, pos, anchor="topleft", alpha=255):
        surf = self.render(s, size, colour)
        rect = surf.get_rect(**{anchor: (int(pos[0]), int(pos[1]))})
        if alpha < 255:
            surf.set_alpha(int(max(alpha, 0)))
            target.blit(surf, rect)
            surf.set_alpha(255)
        else:
            target.blit(surf, rect)
        return rect


class Button:
    def __init__(self, rect, label, on_click, colour=PANEL_HI, size=28, sel_colour=ACCENT):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.on_click = on_click
        self.colour = colour
        self.sel_colour = sel_colour
        self.size = size
        self.selected = False
        self.enabled = True

    def draw(self, surf, text, mouse):
        hover = self.enabled and self.rect.collidepoint(mouse)
        col = self.sel_colour if self.selected else self.colour
        if hover:
            col = mix(col, WHITE, 0.15)
        if not self.enabled:
            col = mix(col, BG, 0.6)
        pygame.draw.rect(surf, col, self.rect, border_radius=10)
        if self.selected:
            pygame.draw.rect(surf, WHITE, self.rect, 2, border_radius=10)
        fg = WHITE if self.enabled else MUTED
        text.draw(surf, self.label, self.size, fg, self.rect.center, "center")

    def click(self, pos):
        if self.enabled and self.rect.collidepoint(pos):
            self.on_click()
            return True
        return False


def make_tick_sound(freq=1700, length=0.07, noise=0.35, volume=0.5):
    try:
        import numpy as np
        rate, _, channels = pygame.mixer.get_init()
        n = int(rate * length)
        t = np.arange(n) / rate
        env = np.exp(-t * 55)
        wave = (np.sin(2 * np.pi * freq * t) * (1 - noise)
                + np.random.uniform(-1, 1, n) * noise * np.exp(-t * 120)) * env
        data = (wave * 32767 * volume).astype(np.int16)
        if channels > 1:
            data = np.repeat(data[:, None], channels, axis=1)
        return pygame.sndarray.make_sound(np.ascontiguousarray(data))
    except Exception:
        return None


def ask_file():
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception:
        return None
    initial = None
    local = os.environ.get("LOCALAPPDATA")
    if local and os.path.isdir(os.path.join(local, "osu!", "Songs")):
        initial = os.path.join(local, "osu!", "Songs")
    root = tk.Tk()
    root.withdraw()
    try:
        root.attributes("-topmost", True)
    except Exception:
        pass
    path = filedialog.askopenfilename(
        title="Вибери карту osu!",
        initialdir=initial,
        filetypes=[("Карти osu!", "*.osu *.osz"), ("Усі файли", "*.*")])
    root.destroy()
    return path or None


# --------------------------------------------------------------------------
# App
# --------------------------------------------------------------------------

class App:
    def __init__(self):
        try:
            pygame.mixer.pre_init(44100, -16, 2, 512)
        except Exception:
            pass
        pygame.init()
        self.audio_ok = pygame.mixer.get_init() is not None
        flags = pygame.SCALED | pygame.RESIZABLE
        try:
            self.screen = pygame.display.set_mode((W, H), flags, vsync=1)
        except Exception:
            self.screen = pygame.display.set_mode((W, H), flags)
        pygame.display.set_caption("osu! bot by Claude — симулятор")
        self.text = Text()
        self.clock = pygame.time.Clock()
        self.settings = {"mode": "grade", "target": "SS", "skill": 7, "mods": set(),
                         "hitsounds": True, "trail": True}
        self.entries = []          # difficulties of the chosen file
        self.selected = 0
        self.map_name = None
        self.error = None
        self.hit_sound = make_tick_sound() if self.audio_ok else None
        self.tick_sound = make_tick_sound(2600, 0.03, 0.6, 0.25) if self.audio_ok else None
        self.bg = self._gradient()
        self.scene = MenuScene(self)
        self.load_demo()
        if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
            self.load_file(sys.argv[1])

    def _gradient(self):
        s = pygame.Surface((W, H))
        for y in range(H):
            pygame.draw.line(s, mix((40, 22, 62), (10, 10, 22), y / H), (0, y), (W, y))
        return s

    # --- map loading ---------------------------------------------------
    def load_demo(self):
        from .beatmap import parse_info
        text = demo_osu()
        self.entries = [(parse_info(text), None, text)]
        self.selected = 0
        self.map_name = "Демо-карта"
        self.error = None

    def load_file(self, path):
        try:
            entries = list_difficulties(path)
        except Exception as e:
            self.error = f"Не вдалося відкрити: {e}"
            return
        self.entries = entries
        std = [i for i, e in enumerate(entries) if e[0].mode == 0]
        self.selected = std[-1] if std else 0
        self.map_name = os.path.basename(path)
        self.error = None if std else "У цьому файлі немає карт osu!standard"

    def build_beatmap(self):
        info, src, text = self.entries[self.selected]
        return Beatmap(text, self.settings["mods"], src)

    # --- main loop -------------------------------------------------------
    def run(self):
        while True:
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    pygame.quit()
                    return
                if ev.type == pygame.KEYDOWN and ev.key == pygame.K_F11:
                    pygame.display.toggle_fullscreen()
                    continue
                if ev.type == pygame.DROPFILE:
                    self.load_file(ev.file)
                    if not isinstance(self.scene, MenuScene):
                        self.go_menu()
                    continue
                self.scene.handle(ev)
            self.scene.update()
            self.scene.draw(self.screen)
            pygame.display.flip()
            self.clock.tick(240)

    def go_menu(self):
        if hasattr(self.scene, "stop"):
            self.scene.stop()
        self.scene = MenuScene(self)

    def start_play(self):
        try:
            bm = self.build_beatmap()
        except Exception as e:
            self.error = f"Помилка карти: {e}"
            return
        if hasattr(self.scene, "stop"):
            self.scene.stop()
        try:
            self.scene = PlayScene(self, bm)
        except Exception as e:
            self.error = f"Не вдалося запустити карту: {e}"
            self.scene = MenuScene(self)


# --------------------------------------------------------------------------
# Menu
# --------------------------------------------------------------------------

class MenuScene:
    def __init__(self, app):
        self.app = app
        self.scroll = 0
        self.t0 = time.perf_counter()
        self.preview = None
        self.preview_key = None
        self._layout()

    def _layout(self):
        self.buttons = []
        b = lambda *args, **kw: self.buttons.append(Button(*args, **kw)) or self.buttons[-1]
        b((40, 130, 360, 56), "Вибрати карту (.osu / .osz)", self.pick_file, colour=ACCENT, size=30)
        b((410, 130, 150, 56), "Демо-карта", self.pick_demo)

        # mode
        self.mode_grade = b((660, 130, 280, 48), "Ціль: ранг", lambda: self.set_mode("grade"))
        self.mode_skill = b((950, 130, 290, 48), "Скіл гравця", lambda: self.set_mode("skill"))
        self.grade_buttons = []
        for k, g in enumerate(GRADES):
            btn = b((660 + k * 83, 200, 75, 64), g, lambda g=g: self.set_target(g),
                    colour=mix(GRADE_COLOURS[g], BG, 0.55), size=40,
                    sel_colour=mix(GRADE_COLOURS[g], BG, 0.1))
            btn.grade = g
            self.grade_buttons.append(btn)
        self.skill_minus = b((660, 200, 64, 64), "-", lambda: self.add_skill(-1), size=44)
        self.skill_plus = b((1176, 200, 64, 64), "+", lambda: self.add_skill(1), size=44)

        # mods
        self.mod_buttons = []
        for k, m in enumerate(["EZ", "HT", "HR", "DT", "NF"]):
            btn = b((660 + k * 117, 360, 108, 52), m, lambda m=m: self.toggle_mod(m), size=32)
            btn.mod = m
            self.mod_buttons.append(btn)

        self.hs_button = b((660, 470, 285, 46), "", self.toggle_hs, size=26)
        self.trail_button = b((955, 470, 285, 46), "", self.toggle_trail, size=26)
        self.play_button = b((660, 560, 580, 80), "ГРАТИ  (Enter)", self.app.start_play,
                             colour=(70, 190, 120), size=46, sel_colour=(70, 190, 120))
        self.diff_buttons = []
        self._sync()

    def _sync(self):
        s = self.app.settings
        self.mode_grade.selected = s["mode"] == "grade"
        self.mode_skill.selected = s["mode"] == "skill"
        for btn in self.grade_buttons:
            btn.selected = s["target"] == btn.grade
            btn.enabled = s["mode"] == "grade"
        self.skill_minus.enabled = self.skill_plus.enabled = s["mode"] == "skill"
        for btn in self.mod_buttons:
            btn.selected = btn.mod in s["mods"]
        self.hs_button.label = "Звуки ударів: " + ("так" if s["hitsounds"] else "ні")
        self.trail_button.label = "Слід курсора: " + ("так" if s["trail"] else "ні")
        self.hs_button.selected = s["hitsounds"]
        self.trail_button.selected = s["trail"]
        self.play_button.enabled = bool(self.app.entries) and \
            self.app.entries[self.app.selected][0].mode == 0
        # difficulty list
        self.diff_buttons = []
        entries = self.app.entries if len(self.app.entries) > 1 else []
        for i, (info, _, _) in enumerate(entries):
            y = 330 + (i - self.scroll) * 46
            if 330 <= y <= 330 + 46 * 5:
                label = info.version or "(без назви)"
                if info.mode != 0:
                    label += "  (не standard)"
                btn = Button((40, y, 520, 40), label[:46], lambda i=i: self.select(i), size=26)
                btn.selected = i == self.app.selected
                btn.enabled = info.mode == 0
                self.diff_buttons.append(btn)

    # actions
    def pick_file(self):
        path = ask_file()
        if path:
            self.app.load_file(path)
            self.scroll = 0
        self._sync()

    def pick_demo(self):
        self.app.load_demo()
        self.scroll = 0
        self._sync()

    def select(self, i):
        self.app.selected = i
        self._sync()

    def set_mode(self, m):
        self.app.settings["mode"] = m
        self._sync()

    def set_target(self, g):
        self.app.settings["target"] = g
        self._sync()

    def add_skill(self, d):
        s = self.app.settings
        s["skill"] = min(10, max(1, s["skill"] + d))

    def toggle_mod(self, m):
        mods = self.app.settings["mods"]
        if m in mods:
            mods.discard(m)
        else:
            mods.add(m)
            other = {"EZ": "HR", "HR": "EZ", "DT": "HT", "HT": "DT"}.get(m)
            mods.discard(other)
        self._sync()

    def toggle_hs(self):
        s = self.app.settings
        s["hitsounds"] = not s["hitsounds"]
        self._sync()

    def toggle_trail(self):
        s = self.app.settings
        s["trail"] = not s["trail"]
        self._sync()

    def handle(self, ev):
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            for btn in self.buttons + self.diff_buttons:
                if btn.click(ev.pos):
                    break
        elif ev.type == pygame.MOUSEWHEEL:
            n = len(self.app.entries)
            self.scroll = min(max(0, self.scroll - ev.y), max(0, n - 6))
            self._sync()
        elif ev.type == pygame.KEYDOWN:
            if ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                if self.play_button.enabled:
                    self.app.start_play()
            elif ev.key == pygame.K_o:
                self.pick_file()
            elif ev.key == pygame.K_ESCAPE:
                pygame.event.post(pygame.event.Event(pygame.QUIT))

    def update(self):
        # keep in sync with drag&drop loads
        key = (id(self.app.entries), self.app.selected, frozenset(self.app.settings["mods"]))
        if key != self.preview_key:
            self.preview_key = key
            self.scroll = min(self.scroll, max(0, len(self.app.entries) - 6))
            self._sync()
            try:
                self.preview = self.app.build_beatmap() if self.play_button.enabled else None
            except Exception as e:
                self.preview = None
                self.app.error = f"Помилка карти: {e}"

    def draw(self, surf):
        a = self.app
        tx = a.text
        surf.blit(a.bg, (0, 0))
        t = time.perf_counter() - self.t0
        # decorative circles
        for k in range(6):
            r = 60 + 40 * k + 20 * math.sin(t * 0.8 + k)
            pygame.draw.circle(surf, mix((60, 40, 90), BG, 0.3 + k * 0.1), (W - 90, H - 60), r, 2)
        tx.draw(surf, "osu! BOT", 72, ACCENT, (40, 28))
        tx.draw(surf, "by Claude", 40, WHITE, (290, 50))
        tx.draw(surf, "бот сам проходить будь-яку карту — ти лише вибираєш файл", 28, MUTED, (40, 92))
        mouse = pygame.mouse.get_pos()

        # left: map
        tx.draw(surf, "або перетягни файл .osu / .osz прямо у вікно", 24, MUTED, (40, 196))
        if a.map_name:
            tx.draw(surf, a.map_name[:60], 24, MUTED, (40, 222))
        if a.entries:
            info = a.entries[a.selected][0]
            tx.draw(surf, f"{info.artist} — {info.title}"[:52], 32, WHITE, (40, 250))
            tx.draw(surf, f"[{info.version}]  мапер: {info.creator}"[:60], 26, ACCENT, (40, 284))
        if len(a.entries) > 1:
            tx.draw(surf, f"Складності ({len(a.entries)}) — колесо миші для прокрутки",
                    22, MUTED, (40, 312))
        for btn in self.diff_buttons:
            btn.draw(surf, tx, mouse)
        if self.preview:
            bm = self.preview
            lo, hi = bm.bpm_range()
            bpm = f"{lo:.0f}" if abs(hi - lo) < 1 else f"{lo:.0f}-{hi:.0f}"
            secs = bm.length_ms / 1000 / bm.rate
            stats = [("CS", bm.cs), ("AR", bm.ar), ("OD", bm.od), ("HP", bm.hp)]
            y = 604 if len(a.entries) > 1 else 340
            x = 40
            for name, v in stats:
                pygame.draw.rect(surf, PANEL, (x, y, 120, 54), border_radius=8)
                tx.draw(surf, name, 22, MUTED, (x + 10, y + 6))
                tx.draw(surf, f"{v:.1f}", 34, WHITE, (x + 110, y + 28), "midright")
                x += 130
            if len(a.entries) == 1:
                lines = [f"BPM: {bpm}", f"Довжина: {int(secs // 60)}:{int(secs % 60):02d}",
                         f"Об'єктів: {len(bm.objects)}", f"Макс. комбо: {bm.max_combo()}x"]
                for k, line in enumerate(lines):
                    tx.draw(surf, line, 30, WHITE, (40, 420 + k * 36))
            else:
                tx.draw(surf, f"BPM {bpm}  •  {int(secs // 60)}:{int(secs % 60):02d}  •  "
                              f"{len(bm.objects)} об'єктів  •  {bm.max_combo()}x",
                        26, WHITE, (40, 664))
        if a.error:
            tx.draw(surf, a.error[:90], 26, (255, 110, 110), (40, 590 if len(a.entries) == 1 else 290))

        # right: bot settings
        pygame.draw.line(surf, PANEL_HI, (620, 130), (620, 650), 2)
        s = a.settings
        for btn in self.buttons:
            if btn in (self.skill_minus, self.skill_plus):
                continue
            if btn in self.grade_buttons and s["mode"] != "grade":
                continue
            btn.draw(surf, tx, mouse)
        if s["mode"] == "grade":
            g = s["target"]
            tx.draw(surf, f"Ранг {g}: {GRADE_TEXT[g]}", 28, GRADE_COLOURS[g], (660, 280))
            tx.draw(surf, "Бот підлаштовує точність, щоб отримати саме цей ранг", 24, MUTED,
                    (660, 312))
        else:
            self.skill_minus.draw(surf, tx, mouse)
            self.skill_plus.draw(surf, tx, mouse)
            k = s["skill"]
            bar = pygame.Rect(740, 220, 420, 24)
            pygame.draw.rect(surf, PANEL, bar, border_radius=12)
            fill = bar.copy()
            fill.width = int(bar.width * k / 10)
            pygame.draw.rect(surf, mix((255, 90, 90), (90, 230, 120), (k - 1) / 9), fill,
                             border_radius=12)
            tx.draw(surf, f"Скіл {k}/10 — {SKILL_TEXT[k - 1]}", 30, WHITE, (950, 262), "midtop")
            tx.draw(surf, "Чесний режим: реакція, швидкість руки й точність як у людини —",
                    22, MUTED, (660, 300))
            tx.draw(surf, "ранг залежить від складності карти", 22, MUTED, (660, 320))
        tx.draw(surf, "Моди:", 26, MUTED, (660, 336))
        mods = sorted(s["mods"])
        tx.draw(surf, ", ".join(MOD_TEXT[m] for m in mods) if mods else "без модів", 24, MUTED,
                (660, 422))
        if s["mode"] == "grade" and s["target"] == "F" and "NF" in s["mods"]:
            tx.draw(surf, "NF не діє з ціллю F", 22, (255, 140, 120), (1000, 422))
        tx.draw(surf, "Esc — меню/вихід   R — заново   P — пауза   Space — пропуск   F11 — повний екран",
                22, MUTED, (W // 2, H - 14), "center")


# --------------------------------------------------------------------------
# Playback
# --------------------------------------------------------------------------

class Sprites:
    def __init__(self, bm, text):
        self.r = bm.radius * SCALE
        self.colours = bm.colours
        self.circles = [self._circle(c) for c in bm.colours]
        self.plain = self._circle((180, 180, 190))
        self.approach = [self._ring(c) for c in bm.colours]
        self.numbers = {}
        self.text = text
        self.cursor = self._cursor()
        self.trail = self._dot(int(self.r * 0.32), (255, 200, 120))
        self.follow = self._ring((255, 255, 255), base=int(self.r * FOLLOW_R * 2), width=0.05)
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
        size = int(self.r * 1.3)
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
            f = self.text.font(max(12, int(self.r * 1.15)))
            surf = self.numbers[n] = f.render(str(n), True, WHITE)
        return surf


FOLLOW_R = 2.4


def blit_centered(surf, img, pos, alpha=255, scale=1.0):
    if scale != 1.0:
        w, h = img.get_size()
        img = pygame.transform.smoothscale(img, (max(1, int(w * scale)), max(1, int(h * scale))))
    if alpha < 255:
        img.set_alpha(int(max(0, alpha)))
    surf.blit(img, img.get_rect(center=(int(pos[0]), int(pos[1]))))
    if alpha < 255:
        img.set_alpha(255)


class PlayScene:
    def __init__(self, app, bm):
        self.app = app
        self.bm = bm
        s = app.settings
        target = s["target"]
        if s["mode"] == "grade" and target == "F":
            bm.mods.discard("NF")
        self.play = Play(bm, s["mode"], target, s["skill"], seed=random.randrange(1 << 30))
        self.sprites = Sprites(bm, app.text)
        self.slider_cache = {}
        self.overlay = pygame.Surface((W, H), pygame.SRCALPHA)
        self.judges = [e for e in self.play.events if e.kind == "judge"]
        self.judge_times = [e.time for e in self.judges]
        self.sound_events = [e for e in self.play.events
                             if e.value and (e.kind == "judge" and bm.objects[e.obj].kind != "slider"
                                             or e.kind == "part")]
        self.sound_idx = 0
        self.hp_shown = 1.0
        self.paused = False
        self.pause_real = 0.0
        self.failed_real = None
        self.finished = False
        self.background = self._load_background()
        self.music = None
        self.music_sound = None
        self.music_array = None
        self.channel = None
        self.music_note = None
        self._load_music()
        first = bm.objects[0].time
        lead = max(bm.preempt + 800, 1500)
        self.start_game = min(0.0, first - lead)
        self.skip_to = first - lead if first - lead > 3000 else None
        self.music_started = False
        self.base_game = self.start_game
        self.base_real = time.perf_counter()
        self.auto_skip_at = self.base_real + 3.0

    # --- assets -------------------------------------------------------------
    def _load_background(self):
        data = self.bm.background_bytes()
        surf = pygame.Surface((W, H))
        surf.fill((8, 8, 14))
        if data:
            try:
                img = pygame.image.load(as_file(data, self.bm.info.background))
                iw, ih = img.get_size()
                k = max(W / iw, H / ih)
                img = pygame.transform.smoothscale(img.convert(), (int(iw * k) + 1, int(ih * k) + 1))
                surf.blit(img, img.get_rect(center=(W // 2, H // 2)))
            except Exception:
                pass
        dim = pygame.Surface((W, H), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 200))
        surf.blit(dim, (0, 0))
        return surf

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
                freq = pygame.mixer.get_init()[0]
                start = int(pos * freq / self.bm.rate)
                if start < len(self.music_array):
                    import numpy as np
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
        idx = 0
        evs = self.sound_events
        while idx < len(evs) and evs[idx].time < game_t:
            idx += 1
        self.sound_idx = idx

    def toggle_pause(self):
        if self.failed_real or self.finished:
            return
        if self.paused:
            self.base_real += time.perf_counter() - self.pause_real
            self.paused = False
            try:
                pygame.mixer.music.unpause()
                if self.channel:
                    self.channel.unpause()
            except Exception:
                pass
        else:
            self.pause_real = time.perf_counter()
            self.paused = True
            try:
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
        # hitsounds
        evs = self.sound_events
        limit = self.play.fail_time if self.play.failed else float("inf")
        while self.sound_idx < len(evs) and evs[self.sound_idx].time <= min(t, limit):
            e = evs[self.sound_idx]
            self.sound_idx += 1
            if self.app.settings["hitsounds"] and t - e.time < 80:
                snd = self.app.tick_sound if e.sub == "tick" else self.app.hit_sound
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
        self.app.scene = ResultScene(self.app, self)

    # --- drawing -----------------------------------------------------------------
    def draw(self, surf):
        t = self.now()
        if self.play.failed and t > self.play.fail_time:
            t = self.play.fail_time
        surf.blit(self.background, (0, 0))
        self.overlay.fill((0, 0, 0, 0))
        self.draw_objects(surf, t)
        self.draw_judgements(surf, t)
        self.draw_cursor(surf, t)
        self.draw_hud(surf, t)
        if self.failed_real:
            k = min(1.0, (time.perf_counter() - self.failed_real) / 1.2)
            shade = pygame.Surface((W, H), pygame.SRCALPHA)
            shade.fill((60, 0, 0, int(150 * k)))
            surf.blit(shade, (0, 0))
            self.app.text.draw(surf, "ПРОВАЛ", int(80 + 40 * k), (255, 90, 90), (W // 2, H // 2),
                               "center")
        if self.paused:
            shade = pygame.Surface((W, H), pygame.SRCALPHA)
            shade.fill((0, 0, 0, 150))
            surf.blit(shade, (0, 0))
            self.app.text.draw(surf, "ПАУЗА  (P — продовжити)", 56, WHITE, (W // 2, H // 2), "center")

    def slider_surface(self, i, obj):
        cached = self.slider_cache.get(i)
        if cached:
            return cached
        R = self.sprites.r
        length = obj.path.length
        step = max(2.5 / SCALE, length / 1200)
        pts = []
        d = 0.0
        while d <= length:
            pts.append(to_screen(obj.path_pos(d / length)))
            d += step
        pts.append(to_screen(obj.path_pos(1.0)))
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

    def visible_range(self, t):
        objs = self.bm.objects
        pre = self.bm.preempt
        out = []
        for i, o in enumerate(objs):
            if o.time - pre > t:
                break
            if o.end_time + 800 < t:
                continue
            out.append(i)
        return out

    def draw_objects(self, surf, t):
        bm = self.bm
        sp = self.sprites
        objs = bm.objects
        res = self.play.results
        vis = self.visible_range(t)
        for i in reversed(vis):
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
                # slider end, reverse arrows, ticks
                end_p = to_screen(o.path_pos(1.0))
                blit_centered(surf, sp.circles[o.colour_index], end_p, a * 0.8)
                for p in o.parts:
                    if p.kind == "tick" and p.time > t:
                        pygame.draw.circle(surf, WHITE, to_screen(o.path_pos(p.progress)),
                                           max(2, sp.r * 0.13))
                if o.slides > 1 and t < o.end_time:
                    span = int(max(0, t - o.time) / o.span_duration) if t > o.time else 0
                    if span < o.slides - 1:
                        at_end = span % 2 == 0
                        self.draw_arrow(surf, o, at_end, a)
                    if span < o.slides - 2:
                        self.draw_arrow(surf, o, not (span % 2 == 0), a)
                head_done = r.head_hit and t >= r.head_time
                head_gone = t >= getattr(r, "head_judge_time", o.time)
                if not head_gone or (head_done and t < r.head_time + 220):
                    self.draw_circle(surf, t, o, r, i, fade, r.head_time if r.head_hit else None,
                                     o.time + bm.w50)
                # ball
                if o.time <= t <= o.end_time:
                    bpos = to_screen(o.ball(t))
                    blit_centered(surf, sp.ball, bpos)
                    if r.release is not None and r.head_time <= t <= r.release:
                        blit_centered(surf, sp.follow, bpos, 200)
                continue
            # circle
            if t > r.judge_time + 240:
                continue
            self.draw_circle(surf, t, o, r, i, fade, r.judge_time if r.hit else None, r.judge_time)

    def draw_arrow(self, surf, o, at_end, alpha):
        if at_end:
            p = o.path_pos(1.0)
            q = o.path_pos(max(0.0, 1.0 - 4 / o.path.length))
        else:
            p = o.path_pos(0.0)
            q = o.path_pos(min(1.0, 4 / o.path.length))
        ang = math.atan2(q[1] - p[1], q[0] - p[0])
        c = to_screen(p)
        R = self.sprites.r * 0.5
        pts = [(c[0] + math.cos(ang + a) * R * k, c[1] + math.sin(ang + a) * R * k)
               for a, k in ((0, 1.0), (2.4, 0.9), (-2.4, 0.9))]
        pygame.draw.polygon(surf, WHITE, pts)

    def draw_circle(self, surf, t, o, r, i, fade, hit_time, miss_time):
        bm = self.bm
        sp = self.sprites
        pos = to_screen(o.pos)
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
        # approach circle
        if t < o.time and (hit_time is None or t < hit_time):
            f = (o.time - t) / bm.preempt
            size = sp.r * 2 * (1 + 3 * f) * 1.05
            img = sp.approach[o.colour_index]
            img2 = pygame.transform.smoothscale(img, (int(size), int(size)))
            blit_centered(surf, img2, pos, min(255, alpha * 0.9))

    def draw_spinner(self, surf, t, o, r):
        tx = self.app.text
        if t < o.time - 300:
            return
        a = min(1.0, (t - (o.time - 300)) / 300)
        if t > o.end_time:
            a *= max(0.0, 1 - (t - o.end_time) / 300)
        if a <= 0:
            return
        c = (W // 2, int(OY + 192 * SCALE))
        big = 250
        ov = self.overlay
        pygame.draw.circle(ov, (20, 20, 40, int(170 * a)), c, big)
        pygame.draw.circle(ov, (255, 255, 255, int(220 * a)), c, big, 4)
        start, stop, omega, required = r.spin
        tt = min(max(t, start), stop)
        spun = omega * (tt - start)
        rot = spun / (2 * math.pi)
        prog = min(1.0, rot / required) if required else 1.0
        for k in range(8):
            ang = spun + k * math.pi / 4
            p1 = (c[0] + math.cos(ang) * 40, c[1] + math.sin(ang) * 40)
            p2 = (c[0] + math.cos(ang) * (big - 14), c[1] + math.sin(ang) * (big - 14))
            pygame.draw.line(ov, (255, 140, 200, int(160 * a)), p1, p2, 3)
        # remaining time ring
        if o.time <= t <= o.end_time:
            rem = 1 - (t - o.time) / (o.end_time - o.time)
            pygame.draw.circle(ov, (120, 200, 255, int(220 * a)), c, max(6, int(big * rem)), 3)
        rect = pygame.Rect(0, 0, big * 2 + 30, big * 2 + 30)
        rect.center = c
        if prog > 0:
            pygame.draw.arc(ov, (120, 255, 150, int(255 * a)), rect, math.pi / 2,
                            math.pi / 2 + 2 * math.pi * prog, 8)
        surf.blit(ov, (0, 0))
        self.overlay.fill((0, 0, 0, 0))
        rpm = omega * 60000 / (2 * math.pi) if start <= t <= stop else 0
        label = "ГОТОВО!" if prog >= 1 else "КРУТИ!"
        tx.draw(surf, label, 52, WHITE, (c[0], c[1] - 40), "center", 255 * a)
        tx.draw(surf, f"{rot:.1f} / {required} обертів", 30, WHITE, (c[0], c[1] + 10), "center",
                255 * a)
        tx.draw(surf, f"RPM {rpm:.0f}", 30, MUTED, (c[0], c[1] + big + 30), "center", 255 * a)

    def draw_judgements(self, surf, t):
        import bisect
        tx = self.app.text
        lo = bisect.bisect_left(self.judge_times, t - 700)
        hi = bisect.bisect_right(self.judge_times, t)
        for e in self.judges[lo:hi]:
            age = t - e.time
            a = 255 * (1 - age / 700)
            pos = to_screen(e.pos)
            if self.bm.objects[e.obj].kind == "spinner":
                pos = (W // 2, int(OY + 192 * SCALE) + 90)
            col = JUDGE_COLOURS[e.value]
            if e.value == 0:
                s = 14 + age * 0.02
                y = pos[1] + age * 0.04
                pygame.draw.line(surf, col, (pos[0] - s, y - s), (pos[0] + s, y + s), 6)
                pygame.draw.line(surf, col, (pos[0] - s, y + s), (pos[0] + s, y - s), 6)
            elif e.value == 300:
                if age < 300:
                    tx.draw(surf, "300", 26, col, pos, "center", 100 * (1 - age / 300))
            else:
                tx.draw(surf, str(e.value), 40, col, (pos[0], pos[1] - age * 0.02), "center", a)

    def draw_cursor(self, surf, t):
        sp = self.sprites
        cur = self.play.cursor
        if self.app.settings["trail"]:
            n = 26
            for k in range(n, 0, -1):
                p = to_screen(cur.at(t - k * 5 * self.bm.rate))
                blit_centered(surf, sp.trail, p, 140 * (1 - k / n) ** 1.5, 1 - 0.5 * k / n)
        blit_centered(surf, sp.cursor, to_screen(cur.at(t)))

    def draw_hud(self, surf, t):
        tx = self.app.text
        play = self.play
        snap = play.snapshot_at(t)
        bm = self.bm
        # HP bar
        self.hp_shown += (snap.hp - self.hp_shown) * 0.15
        pygame.draw.rect(surf, (0, 0, 0), (20, 16, 420, 18), border_radius=9)
        hp_col = mix((255, 70, 70), (120, 240, 140), min(1, self.hp_shown * 1.5))
        pygame.draw.rect(surf, hp_col, (22, 18, int(416 * self.hp_shown), 14), border_radius=7)
        # progress
        first = bm.objects[0].time
        last = bm.objects[-1].end_time
        prog = min(1.0, max(0.0, (t - first) / max(1, last - first)))
        pygame.draw.rect(surf, (60, 60, 80), (20, 40, 420, 5), border_radius=3)
        pygame.draw.rect(surf, (200, 200, 230), (20, 40, int(420 * prog), 5), border_radius=3)
        mode = f"Ціль: {play.target}" if play.mode == "grade" else f"Скіл {int(play.skill)}/10"
        mods = " +" + "".join(sorted(bm.mods)) if bm.mods else ""
        tx.draw(surf, f"BOT Claude  •  {mode}{mods}", 26, ACCENT, (20, 54))
        # score / acc
        tx.draw(surf, f"{snap.score:08d}", 58, WHITE, (W - 20, 10), "topright")
        acc = accuracy(*snap.counts)
        tx.draw(surf, f"{acc * 100:.2f}%", 36, WHITE, (W - 20, 58), "topright")
        g = grade_of(*snap.counts)
        tx.draw(surf, g, 36, GRADE_COLOURS[g], (W - 140, 58), "topright")
        # combo
        tx.draw(surf, f"{snap.combo}x", 72, WHITE, (20, H - 14), "bottomleft")
        # keys
        down = play.keys.keys_down(t)
        for k in range(2):
            rect = pygame.Rect(W - 76, H // 2 - 60 + k * 66, 58, 58)
            on = down[k]
            pygame.draw.rect(surf, ACCENT if on else (40, 36, 60), rect, border_radius=8)
            pygame.draw.rect(surf, WHITE, rect, 2, border_radius=8)
            cnt = play.keys.count_before(t, k)
            tx.draw(surf, f"K{k + 1}" if cnt == 0 else str(cnt), 26, WHITE, rect.center, "center")
        # counts
        n300, n100, n50, nm = snap.counts
        tx.draw(surf, f"100: {n100}   50: {n50}   X: {nm}", 26, MUTED, (W - 20, 96), "topright")
        # hit error bar
        self.draw_error_bar(surf, t)
        # title
        info = bm.info
        tx.draw(surf, f"{info.artist} - {info.title} [{info.version}]"[:70], 22, MUTED,
                (W - 20, H - 10), "bottomright")
        if self.music_note:
            tx.draw(surf, f"Музика: {self.music_note}", 22, MUTED, (W - 20, H - 32), "bottomright")
        if self.skip_to is not None and t < self.skip_to:
            tx.draw(surf, "SPACE — пропустити вступ", 32, WHITE, (W - 40, H - 90), "bottomright")

    def draw_error_bar(self, surf, t):
        import bisect
        bm = self.bm
        cx, y = W // 2, H - 24
        k = 1.4
        w50 = bm.w50 * k
        for w, col in ((bm.w50, (230, 170, 60)), (bm.w100, (100, 210, 90)), (bm.w300, (80, 170, 255))):
            pygame.draw.rect(surf, col, (cx - w * k, y - 3, 2 * w * k, 6))
        pygame.draw.rect(surf, WHITE, (cx - 1, y - 12, 3, 24))
        errs = self.play.hit_errors
        times = self._err_times if hasattr(self, "_err_times") else None
        if times is None:
            self._err_times = times = [e[0] for e in errs]
        lo = bisect.bisect_left(times, t - 6000)
        hi = bisect.bisect_right(times, t)
        for et, e in errs[lo:hi]:
            a = 1 - (t - et) / 6000
            x = cx + max(-w50, min(w50, e * k))
            col = mix((20, 20, 30), WHITE, a)
            pygame.draw.line(surf, col, (x, y - 10), (x, y + 10), 2)


# --------------------------------------------------------------------------
# Results
# --------------------------------------------------------------------------

class ResultScene:
    def __init__(self, app, scene):
        self.app = app
        self.scene = scene
        self.play = scene.play
        self.bm = scene.bm
        self.t0 = time.perf_counter()
        self.buttons = [
            Button((W - 520, H - 110, 230, 64), "Ще раз (R)", app.start_play, colour=ACCENT),
            Button((W - 270, H - 110, 230, 64), "Меню (Esc)", app.go_menu),
        ]

    def handle(self, ev):
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            for b in self.buttons:
                if b.click(ev.pos):
                    return
        elif ev.type == pygame.KEYDOWN:
            if ev.key == pygame.K_r:
                self.app.start_play()
            elif ev.key in (pygame.K_ESCAPE, pygame.K_RETURN):
                self.app.go_menu()

    def update(self):
        pass

    def draw(self, surf):
        tx = self.app.text
        play = self.play
        bm = self.bm
        surf.blit(self.scene.background, (0, 0))
        k = min(1.0, (time.perf_counter() - self.t0) / 0.6)
        info = bm.info
        tx.draw(surf, f"{info.artist} - {info.title}"[:60], 40, WHITE, (40, 30))
        tx.draw(surf, f"[{info.version}]  мапер: {info.creator}"[:70], 28, ACCENT, (40, 74))
        mods = ", ".join(sorted(bm.mods)) or "без модів"
        mode = f"ціль — ранг {play.target}" if play.mode == "grade" else \
            f"скіл {int(play.skill)}/10 ({SKILL_TEXT[int(play.skill) - 1]})"
        tx.draw(surf, f"Бот Claude: {mode}  •  моди: {mods}", 26, MUTED, (40, 108))

        panel = pygame.Rect(40, 150, 640, 440)
        pygame.draw.rect(surf, (20, 16, 34), panel, border_radius=16)
        n300, n100, n50, nm = play.final.counts
        rows = [("300", n300, JUDGE_COLOURS[300]), ("100", n100, JUDGE_COLOURS[100]),
                ("50", n50, JUDGE_COLOURS[50]), ("Промах", nm, JUDGE_COLOURS[0])]
        for r, (name, v, col) in enumerate(rows):
            x = 70 + (r % 2) * 310
            y = 180 + (r // 2) * 90
            tx.draw(surf, name, 34, col, (x, y))
            tx.draw(surf, f"{v}x", 56, WHITE, (x + 130, y - 6))
        tx.draw(surf, "Очки", 30, MUTED, (70, 370))
        tx.draw(surf, f"{play.final.score:,}".replace(",", " "), 52, WHITE, (70, 400))
        tx.draw(surf, "Макс. комбо", 30, MUTED, (380, 370))
        tx.draw(surf, f"{play.final.max_combo}x / {bm.max_combo()}x", 46, WHITE, (380, 404))
        tx.draw(surf, "Точність", 30, MUTED, (70, 470))
        tx.draw(surf, f"{play.accuracy * 100:.2f}%", 52, WHITE, (70, 500))
        tx.draw(surf, "Unstable Rate", 30, MUTED, (380, 470))
        tx.draw(surf, f"{play.unstable_rate:.1f}", 46, WHITE, (380, 504))

        g = play.grade
        col = GRADE_COLOURS[g]
        tx.draw(surf, g, 300, col, (960, 340 + 30 * (1 - k)), "center", 255 * k)
        if play.failed:
            tx.draw(surf, "Бот втратив усе HP — карту провалено", 30, (255, 120, 120),
                    (960, 520), "center")
        elif play.mode == "grade":
            ok = g == play.target
            msg = "Ціль виконано!" if ok else f"Ціль була {play.target}"
            tx.draw(surf, msg, 34, (130, 240, 140) if ok else (255, 190, 90), (960, 520), "center")
        mouse = pygame.mouse.get_pos()
        for b in self.buttons:
            b.draw(surf, tx, mouse)


def selftest():
    """Used by the build to check that the packaged .exe really starts."""
    app = App()
    app.settings["target"] = "A"
    app.start_play()
    scene = app.scene
    if not isinstance(scene, PlayScene):
        raise RuntimeError(app.error)
    scene.seek(scene.bm.objects[10].time)
    for _ in range(120):
        pygame.event.pump()
        app.scene.update()
        app.scene.draw(app.screen)
        pygame.display.flip()
    scene.finish()
    app.scene.draw(app.screen)
    import importlib
    importlib.import_module("tkinter")  # the file picker must be bundled
    pygame.quit()
    return 0


def _log_path(name):
    base = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else
                           os.path.abspath(sys.argv[0]))
    return os.path.join(base, name)


def main():
    import traceback
    if "--selftest" in sys.argv:
        try:
            code = selftest()
        except Exception:
            with open(_log_path("selftest.log"), "w", encoding="utf-8") as f:
                f.write(traceback.format_exc())
            code = 1
        sys.exit(code)
    try:
        App().run()
    except Exception:
        log = _log_path("osu-bot-crash.log")
        try:
            with open(log, "w", encoding="utf-8") as f:
                f.write(traceback.format_exc())
        except OSError:
            log = "(не вдалося записати лог)"
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("osu! bot", f"Програма впала з помилкою.\nДеталі: {log}")
            root.destroy()
        except Exception:
            pass
        raise
