# Arima Kana — avatar decoration + banner

Made to match the Kana icon (pink frilly collar, doodled hearts, white phone with a red bow)
and the same sticker style as the Ruby set (dark plum outlines, halftone dots, 4-point sparkles).

| File | What | Size |
| --- | --- | --- |
| `kana-decoration.png` | avatar decoration, static | 288×288, transparent |
| `kana-decoration.apng` | avatar decoration, animated (2 s loop) | 288×288, transparent |
| `kana-banner.png` / `kana-banner@2x.png` | profile banner, static | 448×84 / 896×168 |
| `kana-banner.gif` | profile banner, animated (2 s loop) | 448×84 |
| `*.svg` | editable vector of frame 0 | |
| `preview.png` | how it looks on a profile | |

## Motifs

- **Crimson satin ribbon + bow:** her red hair, and the ribbon in the icon
- **Pink scalloped lace:** the frilly collar from the icon
- **White hearts with a blue rim:** the hearts doodled around her in the icon
- **White phone with a red bow:** the phone case she's holding
- **Blue→pink starry sparkle:** her sparkling eyes
- **Green pepper + music notes:** *Pīman Taisō*, her hit song as a child star
- **Little teardrop:** "the genius child actress who can cry in 10 seconds"

## Rebuild

```
python3 source/build.py                 # needs Pillow + Node with Playwright (Chromium)
python3 source/preview.py <avatar.png>  # regenerates preview.png
```
Colours, positions and animation timing are all at the top of `source/build.py`.
