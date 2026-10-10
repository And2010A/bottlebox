"""Composites the decoration over an avatar (and the banner above it) for a quick look."""
import os, sys
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.dirname(HERE)
avatar_path = sys.argv[1]

av = Image.open(avatar_path).convert("RGBA").resize((240, 240), Image.LANCZOS)
mask = Image.new("L", (240, 240), 0)
ImageDraw.Draw(mask).ellipse((0, 0, 239, 239), fill=255)
deco = Image.open(os.path.join(OUT, "kana-decoration.png"))
ban = Image.open(os.path.join(OUT, "kana-banner@2x.png")).convert("RGBA")

W = 896
card = Image.new("RGBA", (W, 168 + 260), "#232428")
card.alpha_composite(ban, (0, 0))
ring = Image.new("RGBA", (288, 288), (0, 0, 0, 0))
ImageDraw.Draw(ring).ellipse((14, 14, 274, 274), fill="#232428")
card.alpha_composite(ring, (20, 168 - 150))
card.alpha_composite(Image.composite(av, Image.new("RGBA", av.size, (0, 0, 0, 0)), mask), (44, 168 - 126))
card.alpha_composite(deco, (20, 168 - 150))
card.save(os.path.join(OUT, "preview.png"))
