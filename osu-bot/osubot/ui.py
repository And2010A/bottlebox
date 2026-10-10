"""Shared drawing helpers.

Layout code works in a logical 1280x720 canvas; `view` maps it onto the real
window, so everything is rendered at native resolution (sharp text at any
window size) instead of being upscaled.
"""

import math
import os

import pygame

from .beatmap import as_file

W, H = 1280, 720

WHITE = (255, 255, 255)
BG = (18, 14, 30)
PANEL = (34, 28, 54)
PANEL_HI = (52, 44, 82)
ACCENT = (255, 102, 170)
MUTED = (170, 160, 200)

GRADE_COLOURS = {
    "SS": (255, 222, 90), "S": (255, 190, 60), "A": (120, 225, 95), "B": (85, 165, 255),
    "C": (200, 115, 255), "D": (255, 85, 85), "F": (150, 150, 165),
}

FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")


def mix(c, d, f):
    return tuple(int(c[i] + (d[i] - c[i]) * f) for i in range(3))


class View:
    def __init__(self):
        self.update(W, H)

    def update(self, w, h):
        self.win_w, self.win_h = w, h
        self.u = min(w / W, h / H)
        self.lx = (w - W * self.u) / 2
        self.ly = (h - H * self.u) / 2
        # osu! playfield (512x384) inside the logical canvas
        self.pf_scale = H * self.u * 0.8 / 384
        self.pf_ox = self.lx + (W * self.u - 512 * self.pf_scale) / 2
        self.pf_oy = self.ly + (H * self.u - 384 * self.pf_scale) / 2 + 10 * self.u

    def p(self, x, y):
        return (self.lx + x * self.u, self.ly + y * self.u)

    def r(self, rect):
        x, y, w, h = rect
        return pygame.Rect(round(self.lx + x * self.u), round(self.ly + y * self.u),
                           max(1, round(w * self.u)), max(1, round(h * self.u)))

    def s(self, v):
        return v * self.u

    def to_logical(self, pos):
        return ((pos[0] - self.lx) / self.u, (pos[1] - self.ly) / self.u)

    def pf(self, p):
        return (self.pf_ox + p[0] * self.pf_scale, self.pf_oy + p[1] * self.pf_scale)


view = View()


def rect(surf, colour, r, width=0, radius=0):
    pygame.draw.rect(surf, colour, view.r(r), max(0, round(width * view.u)) if width else 0,
                     border_radius=max(0, round(radius * view.u)))


class Text:
    """Text rendering; sizes are given in the old default-font units of the layout."""

    FILES = {"bold": "Nunito-Bold.ttf", "black": "Nunito-Black.ttf"}

    def __init__(self):
        self.fonts = {}
        self.cache = {}

    def font(self, size, weight="bold"):
        px = max(8, round(size * 0.68 * view.u))
        key = (px, weight)
        f = self.fonts.get(key)
        if f is None:
            path = os.path.join(FONT_DIR, self.FILES[weight])
            try:
                f = pygame.font.Font(path, px)
            except (OSError, FileNotFoundError):
                f = pygame.font.Font(None, round(px / 0.6875))
            self.fonts[key] = f
        return f

    def font_px(self, px, weight="bold"):
        """A font with an exact pixel size (for playfield elements)."""
        return self.font(px / (0.68 * view.u), weight)

    def render(self, s, size, colour=WHITE, weight="bold"):
        key = (s, size, colour, weight, view.u)
        surf = self.cache.get(key)
        if surf is None:
            if len(self.cache) > 1000:
                self.cache.clear()
            surf = self.cache[key] = self.font(size, weight).render(str(s), True, colour)
        return surf

    def draw(self, target, s, size, colour, pos, anchor="topleft", alpha=255, weight="bold",
             screen=False):
        """Draw text at a logical position (or a screen position if screen=True)."""
        surf = self.render(s, size, colour, weight)
        p = pos if screen else view.p(*pos)
        r = surf.get_rect(**{anchor: (round(p[0]), round(p[1]))})
        if alpha < 255:
            surf.set_alpha(int(max(alpha, 0)))
            target.blit(surf, r)
            surf.set_alpha(255)
        else:
            target.blit(surf, r)
        return r


class Button:
    def __init__(self, r, label, on_click, colour=PANEL_HI, size=28, sel_colour=ACCENT):
        self.rect = pygame.Rect(r)  # logical
        self.label = label
        self.on_click = on_click
        self.colour = colour
        self.sel_colour = sel_colour
        self.size = size
        self.selected = False
        self.enabled = True
        self.visible = True

    def draw(self, surf, text, mouse):
        if not self.visible:
            return
        hover = self.enabled and self.rect.collidepoint(mouse)
        col = self.sel_colour if self.selected else self.colour
        if hover:
            col = mix(col, WHITE, 0.15)
        if not self.enabled:
            col = mix(col, BG, 0.6)
        rect(surf, col, self.rect, radius=10)
        if self.selected:
            rect(surf, WHITE, self.rect, 2, radius=10)
        fg = WHITE if self.enabled else MUTED
        text.draw(surf, self.label, self.size, fg, self.rect.center, "center")

    def click(self, pos):
        if self.visible and self.enabled and self.rect.collidepoint(pos):
            self.on_click()
            return True
        return False


def blit_centered(surf, img, pos, alpha=255, scale=1.0):
    if scale != 1.0:
        w, h = img.get_size()
        img = pygame.transform.smoothscale(img, (max(1, int(w * scale)), max(1, int(h * scale))))
    if alpha < 255:
        img.set_alpha(int(max(0, alpha)))
    surf.blit(img, img.get_rect(center=(int(pos[0]), int(pos[1]))))
    if alpha < 255:
        img.set_alpha(255)


def make_icon(size):
    """The bot's avatar: an osu!-style hit circle with a little robot face."""
    big = size * 4
    s = pygame.Surface((big, big), pygame.SRCALPHA)
    c = big // 2
    R = big * 0.47
    for k in range(24):
        f = k / 23
        pygame.draw.circle(s, mix((150, 40, 110), (255, 120, 185), f) + (255,), (c, c),
                           R * (1 - 0.55 * f))
    pygame.draw.circle(s, (255, 255, 255, 255), (c, c), R, max(2, int(big * 0.07)))
    # face
    eye_w, eye_h = big * 0.11, big * 0.17
    for dx in (-1, 1):
        e = pygame.Rect(0, 0, eye_w, eye_h)
        e.center = (c + dx * big * 0.13, c - big * 0.05)
        pygame.draw.ellipse(s, (255, 255, 255, 255), e)
    mouth = pygame.Rect(0, 0, big * 0.34, big * 0.2)
    mouth.center = (c, c + big * 0.1)
    pygame.draw.arc(s, (255, 255, 255, 255), mouth, math.pi * 1.1, math.pi * 1.9,
                    max(2, int(big * 0.04)))
    return pygame.transform.smoothscale(s, (size, size))


def load_image(data, name):
    if not data:
        return None
    try:
        return pygame.image.load(as_file(data, name or "bg.jpg"), name or "bg.jpg").convert()
    except Exception:
        return None


def cover(img, w, h):
    """Scale an image to cover a w x h area (cropping the overflow)."""
    out = pygame.Surface((w, h))
    out.fill((8, 8, 14))
    if img is None:
        return out
    iw, ih = img.get_size()
    k = max(w / iw, h / ih)
    scaled = pygame.transform.smoothscale(img, (int(iw * k) + 1, int(ih * k) + 1))
    out.blit(scaled, scaled.get_rect(center=(w // 2, h // 2)))
    return out


def blurred(img, w, h, amount=10):
    small = cover(img, max(1, w // amount), max(1, h // amount))
    return pygame.transform.smoothscale(small, (w, h))


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
