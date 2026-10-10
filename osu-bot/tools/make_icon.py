"""Render the bot avatar to icon.png (PyInstaller turns it into the .exe icon)."""

import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

from osubot.ui import make_icon  # noqa: E402

pygame.init()
out = sys.argv[1] if len(sys.argv) > 1 else "icon.png"
pygame.image.save(make_icon(256), out)
print("saved", out)
