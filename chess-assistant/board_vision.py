"""Розпізнавання шахової дошки на скріншоті.

Ідея: під час калібрування на екрані стоїть початкова позиція, тому ми точно
знаємо, яка фігура в якій клітинці, і просто «вирізаємо» зразки фігур саме
того сайту і тієї теми, якими ви користуєтесь. Далі кожну клітинку порівнюємо
з цими зразками. Колір фону клітинки (світла, темна, підсвічена останнім ходом)
визначаємо окремо для кожної клітинки, тому підсвітки не заважають.
"""

import numpy as np
from PIL import Image

import chess

PATCH = 32       # розмір нормалізованої клітинки, px
SHIFT = 2        # допустимий зсув фігури відносно зразка, px (неточні кути дошки)
INSET = 0.06     # відступ від краю клітинки (частка її розміру)
RING = 3         # товщина рамки, з якої беремо колір фону, px
BG_TOL = 22.0    # піксель, ближчий за це до кольору фону, вважається фоном
EMPTY_FG = 0.04  # клітинка з меншою часткою «нефонових» пікселів — порожня

START_BOARD = chess.Board()


def to_rgb(img):
    """PIL Image або масив HxWx3/4 -> масив HxWx3 uint8."""
    arr = np.asarray(img)
    if arr.ndim == 3 and arr.shape[2] == 4:
        arr = arr[:, :, :3]
    return np.ascontiguousarray(arr, dtype=np.uint8)


def split_squares(board_rgb):
    """Розрізає зображення дошки на 64 клітинки: масив (8, 8, PATCH, PATCH, 3).

    Індекси — екранні: [рядок зверху вниз][стовпчик зліва направо].
    """
    board_rgb = to_rgb(board_rgb)
    h, w = board_rgb.shape[:2]
    out = np.empty((8, 8, PATCH, PATCH, 3), np.float32)
    for r in range(8):
        y0 = int(round((r + INSET) * h / 8))
        y1 = max(y0 + 1, int(round((r + 1 - INSET) * h / 8)))
        for c in range(8):
            x0 = int(round((c + INSET) * w / 8))
            x1 = max(x0 + 1, int(round((c + 1 - INSET) * w / 8)))
            crop = Image.fromarray(board_rgb[y0:y1, x0:x1])
            out[r, c] = np.asarray(crop.resize((PATCH, PATCH), Image.BILINEAR), np.float32)
    return out


def background(patch):
    """Колір фону клітинки — медіана пікселів по її краях."""
    ring = np.concatenate([
        patch[:RING].reshape(-1, 3),
        patch[-RING:].reshape(-1, 3),
        patch[RING:-RING, :RING].reshape(-1, 3),
        patch[RING:-RING, -RING:].reshape(-1, 3),
    ])
    return np.median(ring, axis=0)


def foreground_mask(patch, bg):
    return np.linalg.norm(patch - bg, axis=2) > BG_TOL


def _center(a):
    m = PATCH // 6
    return a[m:-m, m:-m]


def foreground_share(patch):
    """Частка «нефонових» пікселів у центрі клітинки (кути з підписами a-h/1-8 не враховуються)."""
    return float(_center(foreground_mask(patch, background(patch))).mean())


def _refine_axis(profile, start, size):
    """Шукає (початок, розмір клітинки), за яких межі клітинок лягають на пік профілю."""
    sq = size / 8
    reach = max(3.0, sq * 0.25)
    best = (-1.0, start, sq)
    n = len(profile)
    for s in np.arange(sq * 0.94, sq * 1.06, 0.05):
        for x0 in np.arange(start - reach, start + reach + 0.5, 0.5):
            idx = np.rint(x0 + s * np.arange(9)).astype(int)
            if idx[0] < 1 or idx[-1] >= n:
                continue
            # внутрішні межі (між світлими і темними полями) важливіші за зовнішню рамку
            score = profile[idx[1:8]].sum() + 0.5 * (profile[idx[0]] + profile[idx[8]])
            if score > best[0]:
                best = (score, x0, s)
    return best[1], best[2] * 8


def refine_region(image_rgb, rough):
    """Уточнює прямокутник дошки (left, top, width, height) у координатах image_rgb.

    Користувач показує кути мишкою приблизно; тут ми «примагнічуємо» сітку
    до справжніх меж між світлими і темними полями.
    """
    img = to_rgb(image_rgb).astype(np.float32)
    left, top, w, h = (float(v) for v in rough)
    y0, y1 = int(max(0, top + h * 0.05)), int(min(img.shape[0], top + h * 0.95))
    x0, x1 = int(max(0, left + w * 0.05)), int(min(img.shape[1], left + w * 0.95))
    col_profile = np.zeros(img.shape[1], np.float32)
    col_profile[1:] = np.abs(np.diff(img[y0:y1], axis=1)).sum(axis=2).mean(axis=0)
    row_profile = np.zeros(img.shape[0], np.float32)
    row_profile[1:] = np.abs(np.diff(img[:, x0:x1], axis=0)).sum(axis=2).mean(axis=1)
    new_left, new_w = _refine_axis(col_profile, left, w)
    new_top, new_h = _refine_axis(row_profile, top, h)
    return int(round(new_left)), int(round(new_top)), int(round(new_w)), int(round(new_h))


def screen_to_square(row, col, white_bottom):
    """Екранна клітинка -> поле python-chess."""
    if white_bottom:
        return chess.square(col, 7 - row)
    return chess.square(7 - col, row)


def square_to_screen(square, white_bottom):
    """Поле python-chess -> (рядок, стовпчик) на екрані."""
    f, r = chess.square_file(square), chess.square_rank(square)
    if white_bottom:
        return 7 - r, f
    return r, 7 - f


class Calibration:
    """Положення дошки на екрані + зразки фігур."""

    def __init__(self, region, templates, masks, labels, white_bottom):
        self.region = tuple(int(v) for v in region)  # left, top, width, height
        self.templates = np.asarray(templates, np.float32)  # (K, PATCH, PATCH, 3)
        self.masks = np.asarray(masks, bool)                  # (K, PATCH, PATCH)
        self.labels = [str(s) for s in labels]                # символи 'P', 'n', ...
        self.white_bottom = bool(white_bottom)

    # ---------- створення ----------

    @classmethod
    def from_start_position(cls, region, board_rgb):
        """Будує калібрування зі скріншоту початкової позиції.

        Повертає (Calibration, None) або (None, текст помилки).
        """
        patches = split_squares(board_rgb)
        shares = np.array([[foreground_share(patches[r, c]) for c in range(8)] for r in range(8)])

        piece_rows = shares[[0, 1, 6, 7]]
        empty_rows = shares[2:6]
        if piece_rows.min() < 0.08 or empty_rows.max() > EMPTY_FG:
            return None, ("На дошці не видно початкової позиції. Перевірте, що кути дошки "
                          "вказані точно і фігури стоять як на початку партії.")

        # Хто знизу: білі фігури світліші за чорні.
        def lum(rows):
            vals = []
            for r in rows:
                for c in range(8):
                    p = patches[r, c]
                    m = foreground_mask(p, background(p))
                    vals.append(p[m].mean() if m.any() else 0.0)
            return float(np.mean(vals))

        white_bottom = lum([6, 7]) > lum([0, 1])

        templates, masks, labels, seen = [], [], [], set()
        for r in (0, 1, 6, 7):
            for c in range(8):
                piece = START_BOARD.piece_at(screen_to_square(r, c, white_bottom))
                key = (piece.symbol(), (r + c) % 2)  # по одному зразку на світлому і темному полі
                if key in seen:
                    continue
                seen.add(key)
                p = patches[r, c]
                templates.append(p)
                masks.append(foreground_mask(p, background(p)))
                labels.append(piece.symbol())

        return cls(region, templates, masks, labels, white_bottom), None

    # ---------- розпізнавання ----------

    def classify(self, patch):
        """Повертає (символ фігури або None, похибка)."""
        bg = background(patch)
        empty_err = float(np.abs(patch - bg).mean())
        # Кожен зразок «перемальовуємо» на фон поточної клітинки і порівнюємо
        # з клітинкою, зсунутою на кілька пікселів у кожен бік.
        rendered = np.where(self.masks[..., None], self.templates, bg)
        padded = np.empty((PATCH + 2 * SHIFT, PATCH + 2 * SHIFT, 3), np.float32)
        padded[:] = bg
        padded[SHIFT:SHIFT + PATCH, SHIFT:SHIFT + PATCH] = patch
        shifted = np.stack([padded[dy:dy + PATCH, dx:dx + PATCH]
                            for dy in range(2 * SHIFT + 1) for dx in range(2 * SHIFT + 1)])
        errs = np.abs(rendered[:, None] - shifted[None]).mean(axis=(2, 3, 4)).min(axis=1)
        k = int(np.argmin(errs))
        if foreground_share(patch) < EMPTY_FG or empty_err <= errs[k]:
            return None, empty_err
        return self.labels[k], float(errs[k])

    def recognize(self, board_rgb):
        """Повертає сітку 8x8 (екранні координати) із символами фігур або None."""
        patches = split_squares(board_rgb)
        return [[self.classify(patches[r, c])[0] for c in range(8)] for r in range(8)]

    # ---------- збереження ----------

    def save(self, path):
        np.savez_compressed(
            path, region=np.array(self.region), templates=self.templates, masks=self.masks,
            labels=np.array(self.labels), white_bottom=np.array(self.white_bottom))

    @classmethod
    def load(cls, path):
        d = np.load(path, allow_pickle=False)
        return cls(d["region"], d["templates"], d["masks"], d["labels"], bool(d["white_bottom"]))


def guess_white_bottom(grid, default):
    """Вгадує орієнтацію дошки за пішаками: білі пішаки майже завжди нижче за чорні."""
    white = [r for r in range(8) for c in range(8) if grid[r][c] == "P"]
    black = [r for r in range(8) for c in range(8) if grid[r][c] == "p"]
    # В ендшпілі прохідні пішаки можуть «розминутися», тож рішення приймаємо лише за явної картини.
    if min(len(white), len(black)) < 3:
        return default
    diff = np.mean(white) - np.mean(black)  # >0: білі пішаки нижче на екрані
    if abs(diff) < 2.0:
        return default
    return bool(diff > 0)


def grid_to_board_fen(grid, white_bottom):
    """Сітка з екранними координатами -> розстановка у форматі FEN."""
    board = chess.BaseBoard(None)
    for r in range(8):
        for c in range(8):
            if grid[r][c]:
                board.set_piece_at(screen_to_square(r, c, white_bottom), chess.Piece.from_symbol(grid[r][c]))
    return board.board_fen()
