"""Background videos (the `Video,offset,"file"` event of a beatmap).

Decoding happens in a separate ffmpeg process that already scales frames to
the window size; a reader thread queues the raw frames, so the game loop only
has to turn one ready frame into a surface now and then. That keeps the
gameplay free of stutters even for large videos.
"""

import collections
import os
import subprocess
import sys
import threading
import time

import pygame

FPS = 30
QUEUE = 4


def ffmpeg_exe():
    env = os.environ.get("IMAGEIO_FFMPEG_EXE")
    if env and os.path.isfile(env):
        return env
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _popen_flags():
    if sys.platform == "win32":
        return {"creationflags": 0x08000000}  # CREATE_NO_WINDOW
    return {}


class VideoPlayer:
    def __init__(self, path, offset_ms, size, rate=1.0):
        self.path = path
        self.offset = offset_ms
        self.size = (max(2, size[0] // 2 * 2), max(2, size[1] // 2 * 2))
        self.rate = rate
        self.exe = ffmpeg_exe()
        self.proc = None
        self.frames = collections.deque()
        self.cond = threading.Condition()
        self.gen = 0
        self.current = None
        self.current_index = -1
        self.ended = False
        self.failed = self.exe is None or not os.path.isfile(path)
        self.last_restart = 0.0
        self.base = 0

    # --- control (main thread) -------------------------------------------------
    def start(self, game_t):
        self.stop()
        if self.failed:
            return
        pos = max(0.0, (game_t - self.offset) / 1000)
        base = int(pos * FPS)
        w, h = self.size
        vf = (f"fps={FPS},scale={w}:{h}:force_original_aspect_ratio=increase:flags=fast_bilinear,"
              f"crop={w}:{h}")
        cmd = [self.exe, "-loglevel", "error", "-nostdin", "-ss", f"{base / FPS:.3f}",
               "-i", self.path, "-an", "-sn", "-vf", vf, "-f", "rawvideo", "-pix_fmt", "rgb24",
               "pipe:1"]
        try:
            self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                         stdin=subprocess.DEVNULL, bufsize=w * h * 3,
                                         **_popen_flags())
        except OSError:
            self.failed = True
            return
        self.ended = False
        self.base = base
        self.last_restart = time.perf_counter()
        with self.cond:
            self.gen += 1
            gen = self.gen
        threading.Thread(target=self._reader, args=(self.proc, gen, base), daemon=True).start()

    def stop(self):
        with self.cond:
            self.gen += 1
            self.frames.clear()
            self.cond.notify_all()
        proc, self.proc = self.proc, None
        if proc is not None:
            try:
                proc.kill()
                proc.stdout.close()
                proc.wait(timeout=1)
            except Exception:
                pass

    def resize(self, size, game_t):
        self.size = (max(2, size[0] // 2 * 2), max(2, size[1] // 2 * 2))
        self.current = None
        self.start(game_t)

    # --- decoding (reader thread) -------------------------------------------------
    def _reader(self, proc, gen, index):
        n = self.size[0] * self.size[1] * 3
        out = proc.stdout
        got_any = False
        while True:
            try:
                data = out.read(n)
            except (OSError, ValueError):
                break
            if not data or len(data) < n:
                break
            got_any = True
            # converting here (pygame releases the GIL) keeps it off the game loop
            img = pygame.image.frombuffer(data, self.size, "RGB")
            try:
                img = img.convert()
            except pygame.error:
                pass
            with self.cond:
                while len(self.frames) >= QUEUE and gen == self.gen:
                    self.cond.wait(0.2)
                if gen != self.gen:
                    return
                self.frames.append((index, img))
            index += 1
        with self.cond:
            if gen == self.gen:
                self.ended = True
                if not got_any and index == 0:
                    self.failed = True

    # --- frames (main thread) ----------------------------------------------------------
    def frame_for(self, game_t):
        """The video frame to show at game time t, or None before the video starts."""
        if self.failed or game_t < self.offset:
            return None
        want = int((game_t - self.offset) / 1000 * FPS)
        latest = None
        with self.cond:
            while self.frames and self.frames[0][0] <= want:
                latest = self.frames.popleft()
            newest = self.frames[-1][0] if self.frames else None
            self.cond.notify_all()
        if latest is not None:
            self.current_index, self.current = latest
        # far behind (slow disk/cpu or a jump in time): restart decoding at the right spot
        have = max(newest if newest is not None else -1, self.current_index, self.base)
        behind = want - have
        if not self.ended and behind > FPS * 2 and time.perf_counter() - self.last_restart > 3:
            self.start(game_t)
        return self.current
