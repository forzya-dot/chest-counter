"""Готовит картинку для значка программы: убирает белый фон и обрезает пустые поля.

Запуск:  python tools/prepare_image.py исходник.png assets/chest.png
(рядом появится и значок программы assets/icon.ico)

Фон убирается «заливкой» от углов и от центра картинки: прозрачным становится
только белое поле, соединённое с этими точками. Белые участки внутри рисунка
(обведённые чёрным контуром) остаются белыми — так рисунок виден на любом фоне.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

THRESHOLD = 120   # насколько цвет может отличаться от белого, чтобы считаться фоном
MAX_SIDE = 512    # больше для значка не нужно, а .exe будет легче


def remove_background(image: Image.Image) -> Image.Image:
    image = image.convert("RGBA")
    w, h = image.size
    seeds = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1), (w // 2, h // 2)]
    for seed in seeds:
        r, g, b, a = image.getpixel(seed)
        if a and min(r, g, b) > 200:  # заливаем только от белых точек
            ImageDraw.floodfill(image, seed, (255, 255, 255, 0), thresh=THRESHOLD)
    box = image.getchannel("A").getbbox()
    if box:
        image = image.crop(box)
    image.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    return image


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    result = remove_background(Image.open(sys.argv[1]))
    result.save(sys.argv[2], optimize=True)
    print("Готово:", sys.argv[2])

    # Заодно делаем квадратный значок для .exe рядом с картинкой.
    side = max(result.size)
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    square.alpha_composite(result, ((side - result.width) // 2, (side - result.height) // 2))
    icon_path = Path(sys.argv[2]).with_name("icon.ico")
    square.save(icon_path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (256, 256)])
    print("Готово:", icon_path)
