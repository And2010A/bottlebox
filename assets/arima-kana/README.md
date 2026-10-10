# Arima Kana — decoration + banner

## Avatar decoration
Kept sparse like Discord's own decorations: two pieces on a diagonal, both in the outer ring.

- **Beret** (top-left): Kana's signature ivory beret with a crimson ribbon band, worn on her head.
- **Satin ribbon + bow** (bottom-right): one crimson ribbon hugging the rim, in her hair colour.

Animation (2 s loop): a light glint sweeps across the beret, three sparkles twinkle, the bow tails sway.

## Banner
The stage she grew up on: velvet curtains, her name in lights (★ 10秒で泣ける天才役者 ★, "the genius actress
who cries in 10 seconds"), a spotlight on the mic, and a crowd waving B-Komachi penlights. White, her colour,
is up front.

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
