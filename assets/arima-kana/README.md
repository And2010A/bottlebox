# Arima Kana — "Genius Actress" decoration + banner

Built from Kana's own character, not from the Ruby set.

| Motif | Why it's Kana |
| --- | --- |
| Ivory beret with a crimson ribbon | her signature beret |
| Stopwatch hitting **10秒** + a falling tear | "the genius child actress who can cry in 10 seconds" (10秒で泣ける天才子役) |
| Clapperboard "ARIMA KANA · SCENE 10 · TAKE 1" + film strip | child-star actress, TV dramas |
| Velvet curtains, spotlight, mic, marquee sign | stage actress (Tsurugi in the *Tokyo Blade* play) |
| White penlights, sea of pink / yellow / white lights | white is her B-Komachi colour; the S1 finale where Aqua raises a white penlight for her |
| Grumpy bell pepper with an anger mark | she secretly hates peppers, yet her childhood hit was *Pīman Taisō* (Bell Pepper Exercise) |
| "Hmph!" bubble | tsundere |

## Files

| File | What | Size |
| --- | --- | --- |
| `kana-decoration.apng` | avatar decoration, animated (2 s loop: stopwatch runs to 10 s, tear falls, clapper snaps, film scrolls) | 288×288, transparent |
| `kana-decoration.png` | avatar decoration, still | 288×288, transparent |
| `kana-banner.gif` | banner, animated (bulbs chase, penlights wave, spotlight dust) | 896×168 |
| `kana-banner.png` / `kana-banner@2x.png` | banner, still | 448×84 / 896×168 |
| `*.svg` | vector source of the still frame | |
| `preview.png` | mock profile with the decoration on the icon | |

## Rebuild

```
python3 source/build.py                 # needs Pillow + Node with Playwright (Chromium)
python3 source/preview.py <avatar.png>  # regenerates preview.png
```
