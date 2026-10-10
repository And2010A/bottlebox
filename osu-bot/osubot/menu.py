"""Main menu."""

import math
import os
import time

import pygame

from .beatmap import MODE_NAMES, PLAYABLE_MODES
from .catch import GRADES
from .results import SKILL_TEXT
from .ui import (ACCENT, BG, GRADE_COLOURS, MUTED, PANEL, PANEL_HI, WHITE, Button, blurred,
                 load_image, make_icon, mix, rect, view)

GRADE_TEXT = {
    "SS": "100% точність — ідеально, як Auto",
    "S": "понад 90% «300», жодного промаху",
    "A": "понад 80% «300», без промахів",
    "B": "понад 70% «300», без промахів",
    "C": "понад 60% «300», трохи промахів",
    "D": "багато помилок, але карту пройдено",
    "F": "провал — бот втрачає все HP",
}
GRADE_TEXT_CATCH = {
    "SS": "100% — жодного пропущеного фрукта",
    "S": "спіймано понад 98%",
    "A": "спіймано понад 94%",
    "B": "спіймано понад 90%",
    "C": "спіймано понад 85%",
    "D": "спіймано менше 85%",
    "F": "провал — бот втрачає все HP",
}
MOD_TEXT = {"EZ": "Easy", "HT": "Half Time", "HR": "Hard Rock", "DT": "Double Time",
            "NF": "No Fail"}
DIM_STEPS = [35, 55, 70, 85]


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


class MenuScene:
    def __init__(self, app):
        self.app = app
        self.scroll = 0
        self.t0 = time.perf_counter()
        self.preview = None
        self.preview_key = None
        self.bg_key = None
        self.bg = None
        self.avatar = None
        self._layout()
        self.on_resize()

    def on_resize(self):
        self.avatar = make_icon(max(16, int(view.s(80))))
        self.bg_key = None

    def _layout(self):
        self.buttons = []

        def b(*args, **kw):
            btn = Button(*args, **kw)
            self.buttons.append(btn)
            return btn

        b((40, 136, 360, 56), "Вибрати карту (.osu / .osz)", self.pick_file, colour=ACCENT, size=30)
        b((410, 136, 150, 56), "Демо-карта", self.pick_demo)

        self.rs_osu = b((660, 130, 285, 46), "osu!", lambda: self.set_ruleset("osu"), size=30)
        self.rs_catch = b((955, 130, 285, 46), "osu!catch", lambda: self.set_ruleset("catch"), size=30)
        self.mode_grade = b((660, 186, 285, 44), "Ціль: ранг", lambda: self.set_mode("grade"))
        self.mode_skill = b((955, 186, 285, 44), "Скіл гравця", lambda: self.set_mode("skill"))
        self.grade_buttons = []
        for k, g in enumerate(GRADES):
            btn = b((660 + k * 83, 242, 75, 58), g, lambda g=g: self.set_target(g),
                    colour=mix(GRADE_COLOURS[g], BG, 0.55), size=40,
                    sel_colour=mix(GRADE_COLOURS[g], BG, 0.1))
            btn.grade = g
            self.grade_buttons.append(btn)
        self.skill_minus = b((660, 242, 58, 58), "-", lambda: self.add_skill(-1), size=44)
        self.skill_plus = b((1182, 242, 58, 58), "+", lambda: self.add_skill(1), size=44)

        self.mod_buttons = []
        for k, m in enumerate(["EZ", "HT", "HR", "DT", "NF"]):
            btn = b((660 + k * 117, 394, 108, 48), m, lambda m=m: self.toggle_mod(m), size=32)
            btn.mod = m
            self.mod_buttons.append(btn)

        self.hs_button = b((660, 462, 137, 44), "", self.toggle_hs, size=23)
        self.trail_button = b((808, 462, 137, 44), "", self.toggle_trail, size=23)
        self.video_button = b((956, 462, 137, 44), "", self.toggle_video, size=23)
        self.dim_button = b((1104, 462, 136, 44), "", self.cycle_dim, size=23)
        self.play_button = b((660, 540, 580, 84), "ГРАТИ  (Enter)", self.app.start_play,
                             colour=(70, 190, 120), size=46, sel_colour=(70, 190, 120))
        self.diff_buttons = []
        self._sync()

    def _sync(self):
        a = self.app
        s = a.settings
        info = a.entries[a.selected][0] if a.entries else None
        catch_only = info is not None and info.mode == 2
        ruleset = a.ruleset()
        self.rs_osu.selected = ruleset == "osu"
        self.rs_catch.selected = ruleset == "catch"
        self.rs_osu.enabled = not catch_only
        self.mode_grade.selected = s["mode"] == "grade"
        self.mode_skill.selected = s["mode"] == "skill"
        for btn in self.grade_buttons:
            btn.selected = s["target"] == btn.grade
            btn.visible = s["mode"] == "grade"
        self.skill_minus.visible = self.skill_plus.visible = s["mode"] == "skill"
        for btn in self.mod_buttons:
            btn.selected = btn.mod in s["mods"]
        self.hs_button.label = "Звуки: " + ("так" if s["hitsounds"] else "ні")
        self.trail_button.label = "Слід: " + ("так" if s["trail"] else "ні")
        self.video_button.label = "Відео: " + ("так" if s["video"] else "ні")
        self.video_button.selected = s["video"]
        self.trail_button.enabled = ruleset == "osu"
        self.dim_button.label = f"Фон: {s['dim']}%"
        self.hs_button.selected = s["hitsounds"]
        self.trail_button.selected = s["trail"] and ruleset == "osu"
        self.play_button.enabled = info is not None and info.mode in PLAYABLE_MODES
        self.diff_buttons = []
        entries = a.entries if len(a.entries) > 1 else []
        for i, (inf, _, _) in enumerate(entries):
            y = 338 + (i - self.scroll) * 44
            if 338 <= y <= 338 + 44 * 5:
                label = inf.version or "(без назви)"
                if inf.mode == 2:
                    label += "  • catch"
                elif inf.mode != 0:
                    label += f"  ({MODE_NAMES.get(inf.mode, '?')} — не підтримується)"
                btn = Button((40, y, 520, 40), label[:52], lambda i=i: self.select(i), size=26)
                btn.selected = i == a.selected
                btn.enabled = inf.mode in PLAYABLE_MODES
                self.diff_buttons.append(btn)

    # --- actions ---------------------------------------------------------------
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

    def set_ruleset(self, r):
        self.app.settings["ruleset"] = r
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
            mods.discard({"EZ": "HR", "HR": "EZ", "DT": "HT", "HT": "DT"}.get(m))
        self._sync()

    def toggle_hs(self):
        s = self.app.settings
        s["hitsounds"] = not s["hitsounds"]
        self._sync()

    def toggle_trail(self):
        s = self.app.settings
        s["trail"] = not s["trail"]
        self._sync()

    def toggle_video(self):
        s = self.app.settings
        s["video"] = not s["video"]
        self._sync()

    def cycle_dim(self):
        s = self.app.settings
        i = DIM_STEPS.index(s["dim"]) if s["dim"] in DIM_STEPS else 0
        s["dim"] = DIM_STEPS[(i + 1) % len(DIM_STEPS)]
        self._sync()

    def handle(self, ev):
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            pos = view.to_logical(ev.pos)
            for btn in self.buttons + self.diff_buttons:
                if btn.click(pos):
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
        a = self.app
        key = (id(a.entries), a.selected, frozenset(a.settings["mods"]))
        if key != self.preview_key:
            self.preview_key = key
            self.scroll = min(self.scroll, max(0, len(a.entries) - 6))
            self._sync()
            try:
                self.preview = a.build_beatmap() if self.play_button.enabled else None
            except Exception as e:
                self.preview = None
                a.error = f"Помилка карти: {e}"
        bg_key = (id(a.entries), a.selected, view.win_w, view.win_h)
        if bg_key != self.bg_key:
            self.bg_key = bg_key
            self.bg = None
            if a.entries:
                info, src, _ = a.entries[a.selected]
                data = src.read(info.background) if (src and info.background) else None
                img = load_image(data, info.background)
                if img is not None:
                    self.bg = blurred(img, view.win_w, view.win_h, 12)
                    shade = pygame.Surface((view.win_w, view.win_h))
                    shade.fill((14, 8, 26))
                    shade.set_alpha(165)
                    self.bg.blit(shade, (0, 0))

    def draw(self, surf):
        a = self.app
        tx = a.text
        if self.bg is not None:
            surf.blit(self.bg, (0, 0))
        else:
            surf.blit(a.bg, (0, 0))
        t = time.perf_counter() - self.t0
        for k in range(6):
            r = view.s(60 + 40 * k + 20 * math.sin(t * 0.8 + k))
            pygame.draw.circle(surf, mix((90, 60, 130), BG, 0.3 + k * 0.1), view.p(1190, 660), r,
                               max(1, int(view.s(2))))
        bob = math.sin(t * 2.2) * view.s(3)
        surf.blit(self.avatar, (view.p(40, 22)[0], view.p(40, 22)[1] + bob))
        tx.draw(surf, "osu!", 72, ACCENT, (134, 10), weight="black")
        tx.draw(surf, "by Claude", 30, WHITE, (137, 80))
        mouse = view.to_logical(pygame.mouse.get_pos())

        if a.error:
            tx.draw(surf, a.error[:80], 24, (255, 120, 120), (40, 200))
        else:
            tx.draw(surf, "або перетягни файл .osu / .osz прямо у вікно", 24, MUTED, (40, 200))
        if a.map_name:
            tx.draw(surf, a.map_name[:60], 24, MUTED, (40, 224))
        if a.entries:
            info = a.entries[a.selected][0]
            tx.draw(surf, f"{info.artist} — {info.title}"[:46], 34, WHITE, (40, 248), weight="black")
            tx.draw(surf, f"[{info.version}]  мапер: {info.creator}"[:60], 26, ACCENT, (40, 286))
        if len(a.entries) > 1:
            tx.draw(surf, f"Складності ({len(a.entries)}) — колесо миші для прокрутки",
                    22, MUTED, (40, 314))
        for btn in self.diff_buttons:
            btn.draw(surf, tx, mouse)
        if self.preview:
            self.draw_stats(surf, multi=len(a.entries) > 1)

        rect(surf, PANEL_HI, (620, 130, 2, 500))
        s = a.settings
        for btn in self.buttons:
            btn.draw(surf, tx, mouse)
        ruleset = a.ruleset()
        if s["mode"] == "grade":
            g = s["target"]
            texts = GRADE_TEXT_CATCH if ruleset == "catch" else GRADE_TEXT
            tx.draw(surf, f"Ранг {g}: {texts[g]}", 28, GRADE_COLOURS[g], (660, 310))
            tx.draw(surf, "Бот підлаштовує точність, щоб отримати саме цей ранг", 22, MUTED,
                    (660, 342))
        else:
            k = s["skill"]
            rect(surf, PANEL, (730, 258, 440, 26), radius=13)
            rect(surf, mix((255, 90, 90), (90, 230, 120), (k - 1) / 9), (730, 258, 440 * k / 10, 26),
                 radius=13)
            tx.draw(surf, f"Скіл {k}/10 — {SKILL_TEXT[k - 1]}", 28, WHITE, (950, 306), "midtop")
            tx.draw(surf, "Чесний режим: помилки як у людини, ранг залежить від карти", 22, MUTED,
                    (660, 342))
        tx.draw(surf, "Моди:", 24, MUTED, (660, 368))
        mods = sorted(s["mods"])
        tx.draw(surf, ", ".join(MOD_TEXT[m] for m in mods) if mods else "без модів", 24, WHITE,
                (730, 368))
        if s["mode"] == "grade" and s["target"] == "F" and "NF" in s["mods"]:
            tx.draw(surf, "NF не діє з ціллю F", 22, (255, 140, 120), (1240, 368), "topright")
        notes = []
        if self.preview is not None and a.entries[a.selected][0].mode == 2:
            notes.append("карта osu!catch — бот ловить фрукти")
        if a.entries and a.entries[a.selected][0].video:
            notes.append("у карті є відео-фон" + ("" if s["video"] else " (вимкнено)"))
        if notes:
            tx.draw(surf, "  •  ".join(notes), 22, MUTED, (660, 632))
        tx.draw(surf, "У грі: Esc / P — пауза   R — заново   Space — пропуск вступу   F11 — повний екран",
                22, MUTED, (640, 706), "center")

    def draw_stats(self, surf, multi):
        tx = self.app.text
        bm = self.preview
        lo, hi = bm.bpm_range()
        bpm = f"{lo:.0f}" if abs(hi - lo) < 1 else f"{lo:.0f}-{hi:.0f}"
        secs = bm.length_ms / 1000 / bm.rate
        stats = [("CS", bm.cs), ("AR", bm.ar), ("OD", bm.od), ("HP", bm.hp)]
        y = 604 if multi else 340
        x = 40
        for name, v in stats:
            rect(surf, PANEL, (x, y, 120, 52), radius=8)
            tx.draw(surf, name, 22, MUTED, (x + 10, y + 6))
            tx.draw(surf, f"{v:.1f}", 34, WHITE, (x + 110, y + 27), "midright", weight="black")
            x += 130
        length = f"{int(secs // 60)}:{int(secs % 60):02d}"
        if multi:
            tx.draw(surf, f"BPM {bpm}  •  {length}  •  {len(bm.objects)} об'єктів", 24, WHITE,
                    (40, 664))
        else:
            lines = [f"BPM: {bpm}", f"Довжина: {length}", f"Об'єктів: {len(bm.objects)}"]
            if self.app.ruleset() == "osu":
                lines.append(f"Макс. комбо: {bm.max_combo()}x")
            for k, line in enumerate(lines):
                tx.draw(surf, line, 30, WHITE, (40, 420 + k * 36))
