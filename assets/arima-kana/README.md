# Arima Kana — "White Penlight" decoration + banner

## Avatar decoration
Two pieces on the diagonal, outer ring only, like Discord's own decorations.

- **Moving white penlight** (left side): the penlight starts at the top with no trail, slides down the left
  rim to the bottom-left and leaves a glowing trail behind it. It lies along the route the whole way, handle
  in front, and the trail comes out of its glowing end. White is Kana's B-Komachi colour (the S1 finale where
  Aqua raises a white penlight for her). Crimson handle, gold ring, a little heart on the tube.
- **Idol stars** (top-right): one soft white star with a crimson edge, two small ones and a tiny heart.

Animation (3 s loop): the penlight appears at the top, travels down and draws the trail, sparkles when it
reaches the end, then penlight and trail fade out and it starts again. The stars breathe and twinkle.

## Banner
A long-exposure night-concert shot: penlight light trails (white, pink, crimson) streaking across a
crimson-to-midnight sky, soft bokeh, and the same idol star on the right. Light pulses run along the trails.

## Files

| File | What | Size |
| --- | --- | --- |
| `kana-decoration.apng` | decoration, animated | 288×288, transparent |
| `kana-decoration.png` | decoration, still | 288×288, transparent |
| `kana-banner.gif` | banner, animated | 896×168 |
| `kana-banner.png` / `kana-banner@2x.png` | banner, still | 448×84 / 896×168 |
| `*.svg` | vector source of the still frame | |
| `preview.png` | mock profile with the decoration on the icon | |

## Rebuild

```
python3 source/build.py                 # needs Pillow + Node with Playwright (Chromium)
python3 source/preview.py <avatar.png>  # regenerates preview.png
```
