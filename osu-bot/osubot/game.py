"""Application shell: window, main loop, map loading, scene switching."""

import os
import random
import sys
import time

import pygame

from .beatmap import Beatmap, list_difficulties, parse_info
from .catch import CatchPlay
from .demo import demo_osu
from .menu import MenuScene
from .play import StdPlayScene
from .play_catch import CatchPlayScene
from .sim import Play
from .ui import Text, make_icon, make_tick_sound, mix, view


class App:
    def __init__(self):
        try:
            pygame.mixer.pre_init(44100, -16, 2, 512)
        except Exception:
            pass
        pygame.init()
        self.audio_ok = pygame.mixer.get_init() is not None
        pygame.display.set_caption("osu! by Claude")
        pygame.display.set_icon(make_icon(64))
        try:
            dw, dh = pygame.display.get_desktop_sizes()[0]
        except Exception:
            dw, dh = 1600, 900
        w = min(1600, int(dw * 0.85))
        h = round(w * 9 / 16)
        if h > dh * 0.85:
            h = int(dh * 0.85)
            w = round(h * 16 / 9)
        self.windowed_size = (max(640, w), max(360, h))
        self.fullscreen = False
        self.screen = pygame.display.set_mode(self.windowed_size, pygame.RESIZABLE)
        view.update(*self.screen.get_size())
        self.text = Text()
        self.clock = pygame.time.Clock()
        self.settings = {"mode": "grade", "target": "SS", "skill": 7, "mods": set(),
                         "hitsounds": True, "trail": True, "dim": 55, "ruleset": "osu",
                         "video": True}
        self.entries = []
        self.selected = 0
        self.map_name = None
        self.error = None
        self.hit_sound = make_tick_sound() if self.audio_ok else None
        self.tick_sound = make_tick_sound(2600, 0.03, 0.6, 0.25) if self.audio_ok else None
        self.bg = self._gradient()
        self.load_demo()
        if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
            self.load_file(sys.argv[1])
        self.scene = MenuScene(self)

    def _gradient(self):
        w, h = view.win_w, view.win_h
        s = pygame.Surface((w, h))
        for y in range(h):
            pygame.draw.line(s, mix((40, 22, 62), (10, 10, 22), y / h), (0, y), (w, y))
        return s

    # --- window ------------------------------------------------------------
    def on_resize(self):
        self.screen = pygame.display.get_surface()
        view.update(*self.screen.get_size())
        self.text.cache.clear()
        self.bg = self._gradient()
        if hasattr(self.scene, "on_resize"):
            self.scene.on_resize()

    def toggle_fullscreen(self):
        if self.fullscreen:
            self.screen = pygame.display.set_mode(self.windowed_size, pygame.RESIZABLE)
        else:
            self.windowed_size = self.screen.get_size()
            self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        self.fullscreen = not self.fullscreen
        self.on_resize()

    # --- map loading ---------------------------------------------------------
    def load_demo(self):
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
        playable = [i for i, e in enumerate(entries) if e[0].mode in (0, 2)]
        self.selected = playable[-1] if playable else 0
        self.map_name = os.path.basename(path)
        self.error = None if playable else \
            "У цьому файлі лише карти osu!taiko / osu!mania — їх бот не грає"

    def ruleset(self):
        if self.entries and self.entries[self.selected][0].mode == 2:
            return "catch"
        return self.settings["ruleset"]

    def build_beatmap(self):
        info, src, text = self.entries[self.selected]
        return Beatmap(text, self.settings["mods"], src)

    # --- scenes -----------------------------------------------------------------
    def go_menu(self):
        if hasattr(self.scene, "stop"):
            self.scene.stop()
        self.scene = MenuScene(self)

    def start_play(self):
        s = self.settings
        try:
            bm = self.build_beatmap()
            if s["mode"] == "grade" and s["target"] == "F":
                bm.mods.discard("NF")
            seed = random.randrange(1 << 30)
            if self.ruleset() == "catch":
                play = CatchPlay(bm, s["mode"], s["target"], s["skill"], seed=seed)
                scene_cls = CatchPlayScene
            else:
                play = Play(bm, s["mode"], s["target"], s["skill"], seed=seed)
                scene_cls = StdPlayScene
        except Exception as e:
            self.error = f"Помилка карти: {e}"
            if not isinstance(self.scene, MenuScene):
                self.go_menu()
            return
        if hasattr(self.scene, "stop"):
            self.scene.stop()
        try:
            self.scene = scene_cls(self, bm, play)
        except Exception as e:
            self.error = f"Не вдалося запустити карту: {e}"
            self.scene = MenuScene(self)

    # --- main loop -------------------------------------------------------------------
    def run(self):
        while True:
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    pygame.quit()
                    return
                if ev.type == pygame.VIDEORESIZE:
                    self.on_resize()
                    continue
                if ev.type == pygame.KEYDOWN and ev.key == pygame.K_F11:
                    self.toggle_fullscreen()
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


def selftest():
    """Used by the build to check that the packaged .exe really starts."""
    app = App()
    for ruleset in ("osu", "catch"):
        app.go_menu()
        app.scene.update()
        app.scene.draw(app.screen)
        app.settings["ruleset"] = ruleset
        app.settings["target"] = "A"
        app.start_play()
        scene = app.scene
        if isinstance(scene, MenuScene):
            raise RuntimeError(app.error)
        scene.seek(scene.first_time() + 2000)
        for _ in range(90):
            pygame.event.pump()
            app.scene.update()
            app.scene.draw(app.screen)
            pygame.display.flip()
        scene.finish()
        app.scene.draw(app.screen)
    # a beatmap with a background video, decoded by the bundled ffmpeg
    import subprocess
    import tempfile
    from .video import _popen_flags, ffmpeg_exe
    exe = ffmpeg_exe()
    if not exe:
        raise RuntimeError("ffmpeg is not bundled")
    folder = tempfile.mkdtemp(prefix="osu-bot-selftest-")
    subprocess.run([exe, "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    "testsrc=size=640x360:rate=30", "-t", "6", "-pix_fmt", "yuv420p",
                    os.path.join(folder, "video.mp4")], check=True, **_popen_flags())
    osu = os.path.join(folder, "map.osu")
    with open(osu, "w", encoding="utf-8") as f:
        f.write(demo_osu().replace("[Events]\n", '[Events]\nVideo,0,"video.mp4"\n'))
    app.load_file(osu)
    app.settings["ruleset"] = "osu"
    app.start_play()
    scene = app.scene
    if getattr(scene, "video", None) is None:
        raise RuntimeError(f"video not loaded: {getattr(scene, 'video_note', app.error)}")
    scene.seek(1500)
    deadline = time.perf_counter() + 5
    while scene.video.current is None and time.perf_counter() < deadline:
        pygame.event.pump()
        scene.update()
        scene.draw(app.screen)
        pygame.display.flip()
    if scene.video.current is None:
        raise RuntimeError("no video frames decoded")
    scene.stop()

    from .ui import FONT_DIR
    for name in Text.FILES.values():
        if not os.path.isfile(os.path.join(FONT_DIR, name)):
            raise RuntimeError(f"font {name} is not bundled")
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
            messagebox.showerror("osu! by Claude", f"Програма впала з помилкою.\nДеталі: {log}")
            root.destroy()
        except Exception:
            pass
        raise
