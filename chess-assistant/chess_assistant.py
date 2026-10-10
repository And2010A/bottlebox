"""Chess Assistant: бачить шахову дошку на екрані, рахує хід Stockfish і робить його мишкою.

Клавіші (змінюються в config.json):
  F8  — калібрування: двічі, спершу курсор у лівому верхньому куті дошки, потім у правому нижньому
        (на дошці має стояти початкова позиція)
  F9  — проаналізувати дошку і зробити хід мишкою
  F10 — тільки підказка: сказати і показати хід, мишку не чіпати
  F7  — перевернути дошку (якщо програма сплутала, ким ви граєте)
  F12 — вихід
"""

import ctypes
import json
import os
import subprocess
import sys
import threading
import time
import traceback


def _make_dpi_aware():
    # Без цього на Windows з масштабуванням 125%/150% координати мишки і скріншота не збігаються.
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


_make_dpi_aware()

import chess  # noqa: E402
import chess.engine  # noqa: E402
import mss  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402
from pynput import keyboard, mouse  # noqa: E402

import board_vision as bv  # noqa: E402

APP_DIR = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "config.json")
CALIBRATION_PATH = os.path.join(APP_DIR, "calibration.npz")
DEBUG_IMAGE_PATH = os.path.join(APP_DIR, "debug_board.png")

DEFAULT_CONFIG = {
    "hotkey_calibrate": "f8",
    "hotkey_move": "f9",
    "hotkey_hint": "f10",
    "hotkey_flip": "f7",
    "hotkey_quit": "f12",
    "stockfish_path": "",
    "think_time_sec": 1.0,
    "threads": 2,
    "hash_mb": 128,
    "skill_level": 20,
    "speak": True,
    "return_mouse": True,
    "click_delay_sec": 0.08,
}

PIECE_NAMES_EN = {
    chess.PAWN: "pawn", chess.KNIGHT: "knight", chess.BISHOP: "bishop",
    chess.ROOK: "rook", chess.QUEEN: "queen", chess.KING: "king",
}
PIECE_NAMES_UA = {
    chess.PAWN: "пішак", chess.KNIGHT: "кінь", chess.BISHOP: "слон",
    chess.ROOK: "тура", chess.QUEEN: "ферзь", chess.KING: "король",
}
# Порядок фігур у меню перетворення пішака на lichess і chess.com (від поля перетворення вниз).
PROMOTION_ORDER = [chess.QUEEN, chess.KNIGHT, chess.ROOK, chess.BISHOP]


def log(msg=""):
    print(msg, flush=True)


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception as e:
            log(f"[!] Не вдалося прочитати config.json ({e}), використовую налаштування за замовчуванням.")
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except OSError:
        pass
    return cfg


def find_stockfish(cfg):
    if cfg.get("stockfish_path"):
        path = cfg["stockfish_path"]
        return path if os.path.isabs(path) else os.path.join(APP_DIR, path)
    exe = "stockfish.exe" if sys.platform == "win32" else "stockfish"
    direct = os.path.join(APP_DIR, exe)
    if os.path.exists(direct):
        return direct
    for root, _dirs, files in os.walk(APP_DIR):
        for name in sorted(files):
            low = name.lower()
            if low.startswith("stockfish") and (low.endswith(".exe") or sys.platform != "win32"):
                return os.path.join(root, name)
    return None


def speak(text):
    """Озвучує текст стандартним голосом Windows (без додаткових бібліотек)."""
    if sys.platform != "win32":
        return
    script = ("Add-Type -AssemblyName System.Speech; "
              "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
              f"$s.Rate = 1; $s.Speak('{text}')")
    try:
        subprocess.Popen(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", script],
                         creationflags=0x08000000)  # CREATE_NO_WINDOW
    except Exception:
        pass


def describe_move(board, move):
    """(текст для консолі, текст для озвучення)."""
    piece = board.piece_at(move.from_square)
    san = board.san(move)
    frm, to = chess.square_name(move.from_square), chess.square_name(move.to_square)
    ua = f"{san}  ({PIECE_NAMES_UA[piece.piece_type]} {frm} → {to})"
    if board.is_castling(move):
        en = "castle king side" if chess.square_file(move.to_square) > 4 else "castle queen side"
    else:
        en = f"{PIECE_NAMES_EN[piece.piece_type]} {frm} {'takes ' if board.is_capture(move) else ''}{to}"
        if move.promotion:
            en += f" promote to {PIECE_NAMES_EN[move.promotion]}"
    if san.endswith("#"):
        en += ", checkmate"
    elif san.endswith("+"):
        en += ", check"
    return ua, en


def format_score(score):
    if score is None:
        return "?"
    if score.is_mate():
        m = score.mate()
        return f"мат за {abs(m)} {'(ви ставите)' if m > 0 else '(вам ставлять)'}"
    return f"{score.score() / 100:+.2f}"


class Assistant:
    def __init__(self):
        self.cfg = load_config()
        self.cal = None
        self.engine = None
        self.game = None           # chess.Board з історією поточної партії
        self.corner = None         # перший кут під час калібрування
        self.busy = threading.Lock()
        self.mouse = mouse.Controller()
        self.listener = None
        if os.path.exists(CALIBRATION_PATH):
            try:
                self.cal = bv.Calibration.load(CALIBRATION_PATH)
                log("Завантажено збережене калібрування дошки.")
            except Exception as e:
                log(f"[!] Не вдалося завантажити калібрування ({e}). Зробіть його заново.")

    # ---------- рушій ----------

    def get_engine(self):
        if self.engine is not None:
            return self.engine
        path = find_stockfish(self.cfg)
        if not path or not os.path.exists(path):
            raise RuntimeError(
                "Не знайдено Stockfish. Покладіть stockfish.exe поруч з програмою "
                "або вкажіть шлях у config.json (stockfish_path).")
        kwargs = {"creationflags": 0x08000000} if sys.platform == "win32" else {}
        self.engine = chess.engine.SimpleEngine.popen_uci(path, **kwargs)
        opts = {"Threads": self.cfg["threads"], "Hash": self.cfg["hash_mb"], "Skill Level": self.cfg["skill_level"]}
        self.engine.configure({k: v for k, v in opts.items() if k in self.engine.options})
        log(f"Stockfish запущено: {self.engine.id.get('name', path)}")
        return self.engine

    # ---------- екран ----------

    @staticmethod
    def grab(left, top, width, height):
        """Скріншот області екрана -> (RGB-масив, left, top); область обрізається межами екранів."""
        with mss.mss() as sct:
            v = sct.monitors[0]  # усі монітори разом
            l, t = max(int(left), v["left"]), max(int(top), v["top"])
            r = min(int(left + width), v["left"] + v["width"])
            b = min(int(top + height), v["top"] + v["height"])
            shot = sct.grab({"left": l, "top": t, "width": max(1, r - l), "height": max(1, b - t)})
            return np.asarray(shot)[:, :, 2::-1], l, t  # BGRA -> RGB

    def square_center(self, square):
        left, top, w, h = self.cal.region
        r, c = bv.square_to_screen(square, self.cal.white_bottom)
        return left + (c + 0.5) * w / 8, top + (r + 0.5) * h / 8

    def save_debug(self, img, grid):
        try:
            im = Image.fromarray(np.ascontiguousarray(img)).convert("RGB")
            d = ImageDraw.Draw(im)
            h, w = img.shape[:2]
            for i in range(9):
                d.line([(i * w / 8, 0), (i * w / 8, h)], fill=(255, 0, 0))
                d.line([(0, i * h / 8), (w, i * h / 8)], fill=(255, 0, 0))
            for r in range(8):
                for c in range(8):
                    if grid and grid[r][c]:
                        x, y = (c + 0.1) * w / 8, (r + 0.1) * h / 8
                        d.rectangle([x - 1, y - 1, x + 9, y + 11], fill=(255, 255, 255))
                        d.text((x, y), grid[r][c], fill=(255, 0, 0))
            im.save(DEBUG_IMAGE_PATH)
            log(f"    Що бачить програма: {DEBUG_IMAGE_PATH}")
        except Exception:
            pass

    # ---------- калібрування ----------

    def calibrate_step(self):
        x, y = self.mouse.position
        if self.corner is None:
            self.corner = (x, y)
            log(f"Лівий верхній кут: ({x:.0f}, {y:.0f}). Тепер наведіть курсор на ПРАВИЙ НИЖНІЙ кут "
                f"дошки і натисніть {self.cfg['hotkey_calibrate'].upper()}.")
            return
        (x0, y0), self.corner = self.corner, None
        left, top = min(x0, x), min(y0, y)
        w, h = abs(x - x0), abs(y - y0)
        if w < 80 or h < 80:
            log("[!] Дошка надто маленька або кути вказані неправильно. Почніть калібрування заново.")
            return
        # Знімаємо трохи більшу область і уточнюємо межі дошки автоматично.
        m = int(max(w, h) * 0.08)
        area, al, at = self.grab(left - m, top - m, w + 2 * m, h + 2 * m)
        rl, rt, rw, rh = bv.refine_region(area, (left - al, top - at, w, h))
        region = (al + rl, at + rt, rw, rh)
        img, _, _ = self.grab(*region)
        cal, err = bv.Calibration.from_start_position(region, img)
        if cal is None:
            log(f"[!] {err}")
            self.save_debug(img, None)
            return
        self.cal = cal
        self.game = None
        cal.save(CALIBRATION_PATH)
        side = "білими" if cal.white_bottom else "чорними"
        log(f"Готово! Дошка: {region[2]}x{region[3]} px у ({region[0]}, {region[1]}). Ви граєте {side}.")
        log(f"Тепер на кожному своєму ході натискайте {self.cfg['hotkey_move'].upper()}.")

    def flip(self):
        if not self.cal:
            log("[!] Спершу зробіть калібрування.")
            return
        self.cal.white_bottom = not self.cal.white_bottom
        self.cal.save(CALIBRATION_PATH)
        self.game = None
        log(f"Дошку перевернуто: тепер ви граєте {'білими' if self.cal.white_bottom else 'чорними'}.")

    # ---------- позиція ----------

    def read_position(self):
        """Знімає дошку з екрана і повертає chess.Board, де хід за вами."""
        img, _, _ = self.grab(*self.cal.region)
        grid = self.cal.recognize(img)
        wb = bv.guess_white_bottom(grid, self.cal.white_bottom)
        if wb != self.cal.white_bottom:
            self.cal.white_bottom = wb
            self.cal.save(CALIBRATION_PATH)
            self.game = None
            log(f"Схоже, дошка перевернута — тепер ви граєте {'білими' if wb else 'чорними'}.")
        placement = bv.grid_to_board_fen(grid, wb)
        me = chess.WHITE if wb else chess.BLACK

        flat = [p for row in grid for p in row if p]
        if flat.count("K") != 1 or flat.count("k") != 1:
            self.save_debug(img, grid)
            raise RuntimeError(f"Не вдалося розпізнати дошку (знайдено: {placement}). "
                               "Можливо, дошку закриває інше вікно або її зсунули — зробіть калібрування заново.")

        board = self.match_history(placement, me)
        if board is None:
            board = chess.Board(None)
            board.set_board_fen(placement)
            board.turn = me
            board.set_castling_fen("KQkq")
            board.castling_rights = board.clean_castling_rights()
            self.game = None
        if not board.is_valid():
            self.save_debug(img, grid)
            if board.was_into_check():
                raise RuntimeError("Король суперника під шахом — схоже, зараз не ваш хід (або дошка розпізнана з помилкою).")
            raise RuntimeError(f"Розпізнана позиція некоректна: {board.fen()}")
        return board

    def match_history(self, placement, me):
        """Шукає ходи (1-2 напівходи), які ведуть від попередньої позиції до поточної.

        Так зберігаються права на рокіровку, взяття на проході і повторення позицій.
        """
        if self.game is None:
            return None
        g = self.game
        if g.board_fen() == placement and g.turn == me:
            return g.copy()
        for m1 in g.legal_moves:
            g.push(m1)
            try:
                if g.turn == me and g.board_fen() == placement:
                    return g.copy()
                if g.turn != me:
                    for m2 in g.legal_moves:
                        g.push(m2)
                        hit = g.board_fen() == placement
                        if hit:
                            found = g.copy()
                        g.pop()
                        if hit:
                            return found
            finally:
                g.pop()
        return None

    # ---------- хід ----------

    def click(self, x, y):
        self.mouse.position = (int(round(x)), int(round(y)))
        time.sleep(self.cfg["click_delay_sec"])
        self.mouse.click(mouse.Button.left)
        time.sleep(self.cfg["click_delay_sec"])

    def play_on_screen(self, move):
        start = self.mouse.position
        self.click(*self.square_center(move.from_square))
        tx, ty = self.square_center(move.to_square)
        self.click(tx, ty)
        if move.promotion:
            time.sleep(0.25)
            step = self.cal.region[3] / 8
            self.click(tx, ty + PROMOTION_ORDER.index(move.promotion) * step)
        if self.cfg["return_mouse"]:
            self.mouse.position = start

    def analyse(self, do_move):
        if not self.cal:
            log(f"[!] Спершу калібрування: курсор у лівий верхній кут дошки і {self.cfg['hotkey_calibrate'].upper()}.")
            return
        board = self.read_position()
        if board.is_game_over():
            log(f"Партію завершено: {board.result()}.")
            return
        engine = self.get_engine()
        t0 = time.time()
        result = engine.play(board, chess.engine.Limit(time=float(self.cfg["think_time_sec"])),
                             info=chess.engine.INFO_SCORE)
        move, info = result.move, result.info
        ua, en = describe_move(board, move)
        score = info.get("score")
        log(f"Хід: {ua}   оцінка: {format_score(score.pov(board.turn) if score else None)}   "
            f"глибина {info.get('depth', '?')}, {time.time() - t0:.1f} с")
        if self.cfg["speak"]:
            speak(en)
        if do_move:
            self.play_on_screen(move)
            board.push(move)
        self.game = board

    # ---------- клавіші ----------

    def run_task(self, fn, *args):
        if not self.busy.acquire(blocking=False):
            return

        def wrapper():
            try:
                fn(*args)
            except RuntimeError as e:
                log(f"[!] {e}")
            except Exception:
                log("[!] Помилка:\n" + traceback.format_exc())
            finally:
                self.busy.release()

        threading.Thread(target=wrapper, daemon=True).start()

    def key_name(self, key):
        if isinstance(key, keyboard.Key):
            return key.name
        if isinstance(key, keyboard.KeyCode) and key.char:
            return key.char.lower()
        return None

    def on_press(self, key):
        name = self.key_name(key)
        c = self.cfg
        if name == c["hotkey_calibrate"]:
            self.run_task(self.calibrate_step)
        elif name == c["hotkey_move"]:
            self.run_task(self.analyse, True)
        elif name == c["hotkey_hint"]:
            self.run_task(self.analyse, False)
        elif name == c["hotkey_flip"]:
            self.run_task(self.flip)
        elif name == c["hotkey_quit"]:
            log("Вихід...")
            return False
        return None

    def run(self):
        c = {k: v.upper() for k, v in self.cfg.items() if k.startswith("hotkey_")}
        log("=" * 64)
        log(" Chess Assistant (Stockfish)")
        log("=" * 64)
        log(f" {c['hotkey_calibrate']}  — калібрування: відкрийте партію з ПОЧАТКОВОЮ позицією,")
        log(f"       наведіть курсор на лівий верхній кут дошки -> {c['hotkey_calibrate']},")
        log(f"       потім на правий нижній кут -> {c['hotkey_calibrate']}")
        log(f" {c['hotkey_move']}  — знайти найкращий хід і зробити його мишкою")
        log(f" {c['hotkey_hint']} — лише підказати хід (без мишки)")
        log(f" {c['hotkey_flip']}  — перевернути дошку (якщо сплутано білі/чорні)")
        log(f" {c['hotkey_quit']} — вихід")
        log("=" * 64)
        if not find_stockfish(self.cfg):
            log("[!] Stockfish не знайдено поруч з програмою — покладіть stockfish.exe в цю папку.")
        with keyboard.Listener(on_press=self.on_press) as self.listener:
            self.listener.join()
        if self.engine:
            self.engine.quit()


def main():
    if sys.platform == "win32":
        try:
            ctypes.windll.kernel32.SetConsoleTitleW("Chess Assistant")
        except Exception:
            pass
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    try:
        Assistant().run()
    except KeyboardInterrupt:
        pass
    except Exception:
        log("[!] Критична помилка:\n" + traceback.format_exc())
        input("Натисніть Enter, щоб закрити...")


if __name__ == "__main__":
    main()
