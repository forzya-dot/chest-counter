"""Подготовка картинки оверлея (только Pillow, без окон и без Windows).

Что здесь делается:
- загрузка PNG и масштабирование под размер из config.json;
- рисование числа рядом с картинкой;
- подготовка прозрачности для окна Windows;
- расчёт положения на экране и прозрачности в каждый момент показа.

Про прозрачность. Окно tkinter в Windows умеет делать прозрачным один
«ключевой» цвет (-transparentcolor): пиксель либо виден, либо нет. Поэтому
полупрозрачные края PNG мы приводим к двум состояниям по порогу, а прозрачные
места закрашиваем ключевым цветом. Плавное исчезновение делается отдельно —
прозрачностью всего окна.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont

# Ключевой цвет: всё, что закрашено им, в окне оверлея становится прозрачным.
# Почти чёрный, чтобы даже при сбое не было яркой рамки.
KEY_COLOR = (1, 0, 2)
KEY_COLOR_HEX = "#010002"

ANCHORS = (
    "top-left", "top-center", "top-right",
    "center",
    "bottom-left", "bottom-center", "bottom-right",
)

_ALLOWED_FORMATS = ("PNG", "JPEG", "GIF", "BMP", "WEBP")

# Жирные шрифты: первые два есть в Windows, остальные — для Mac/Linux при разработке.
_FONT_CANDIDATES = ("segoeuib.ttf", "arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf")


def placeholder_image(size: int = 256) -> Image.Image:
    """Заглушка на случай, если файл картинки не найден или испорчен: простой сундук."""
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    s = size / 16
    outline = max(2, size // 40)
    draw.rounded_rectangle([1 * s, 4 * s, 15 * s, 14 * s], radius=1.5 * s,
                           fill=(139, 90, 43, 255), outline=(60, 35, 10, 255), width=outline)
    draw.rectangle([1 * s, 7.5 * s, 15 * s, 9 * s], fill=(245, 185, 66, 255))
    draw.rectangle([7 * s, 7 * s, 9 * s, 10.5 * s], fill=(245, 185, 66, 255),
                   outline=(60, 35, 10, 255), width=max(1, outline // 2))
    return image


def load_image(path: Path | str | None) -> Image.Image:
    """Загружает картинку; если не получилось — возвращает заглушку."""
    if path:
        try:
            # formats: открываем только обычные картинки, а не любой из десятков
            # форматов Pillow. Слишком большие файлы Pillow отвергает сам
            # (DecompressionBombError) — тогда тоже показываем заглушку.
            with Image.open(path, formats=_ALLOWED_FORMATS) as image:
                return image.convert("RGBA")
        except Exception:
            pass
    return placeholder_image()


def fit_image(image: Image.Image, size: int) -> Image.Image:
    """Масштабирует так, чтобы большая сторона стала равна size (пропорции сохраняются)."""
    size = max(16, min(int(size), 2000))
    scale = size / max(image.size)
    new_size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    return image.convert("RGBA").resize(new_size, Image.LANCZOS)


def _load_font(pixel_size: int) -> ImageFont.ImageFont:
    for name in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(name, pixel_size)
        except OSError:
            continue
    return ImageFont.load_default(size=pixel_size)  # встроенный шрифт Pillow


def compose(picture: Image.Image, count: int | None) -> Image.Image:
    """Собирает кадр оверлея: картинка слева, число справа.

    picture — уже отмасштабированная картинка. count=None — без числа.
    Число белое с чёрной обводкой, чтобы читалось на любом фоне игры.
    """
    if count is None:
        return picture.copy()

    text = str(count)
    font = _load_font(max(12, round(picture.height * 0.5)))
    stroke = max(2, picture.height // 28)
    gap = max(4, picture.height // 10)

    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    left, top, right, bottom = probe.textbbox((0, 0), text, font=font, stroke_width=stroke)
    text_w, text_h = right - left, bottom - top

    width = picture.width + gap + text_w
    height = max(picture.height, text_h)
    frame = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    frame.alpha_composite(picture, (0, (height - picture.height) // 2))
    ImageDraw.Draw(frame).text(
        (picture.width + gap - left, (height - text_h) // 2 - top),
        text, font=font, fill=(255, 255, 255, 255),
        stroke_width=stroke, stroke_fill=(0, 0, 0, 255),
    )
    return frame


def flatten_for_colorkey(frame: Image.Image, threshold: int = 128) -> Image.Image:
    """RGBA -> RGB, где прозрачные места закрашены ключевым цветом."""
    frame = frame.convert("RGBA")
    rgb = frame.convert("RGB")
    key_layer = Image.new("RGB", frame.size, KEY_COLOR)

    # Если в самой картинке случайно есть ключевой цвет, заменяем его чёрным
    # (на глаз неотличимо), иначе в рисунке появились бы «дырки».
    difference = ImageChops.difference(rgb, key_layer).convert("L")
    same_as_key = difference.point(lambda v: 255 if v == 0 else 0)
    rgb.paste((0, 0, 0), mask=same_as_key)

    visible = frame.getchannel("A").point(lambda a: 255 if a >= threshold else 0)
    return Image.composite(rgb, key_layer, visible)


def compute_position(
    screen_w: int, screen_h: int, win_w: int, win_h: int,
    anchor: str, offset_x: int, offset_y: int,
) -> tuple[int, int]:
    """Левый верхний угол окна оверлея по углу экрана и отступам.

    Окно никогда не выходит за пределы экрана.
    """
    if anchor not in ANCHORS:
        anchor = "top-right"

    if anchor.endswith("left"):
        x = offset_x
    elif anchor.endswith("right"):
        x = screen_w - win_w - offset_x
    else:  # center, top-center, bottom-center
        x = (screen_w - win_w) // 2 + offset_x

    if anchor.startswith("top"):
        y = offset_y
    elif anchor.startswith("bottom"):
        y = screen_h - win_h - offset_y
    else:
        y = (screen_h - win_h) // 2 + offset_y

    x = max(0, min(int(x), max(0, screen_w - win_w)))
    y = max(0, min(int(y), max(0, screen_h - win_h)))
    return x, y


def alpha_at(elapsed_ms: float, duration_ms: float, fade_ms: float) -> float | None:
    """Непрозрачность окна через elapsed_ms после показа.

    Сначала 1.0, в последние fade_ms плавно падает до 0.
    None — время вышло, окно пора прятать.
    """
    duration_ms = max(100.0, float(duration_ms))
    fade_ms = max(0.0, min(float(fade_ms), duration_ms))
    if elapsed_ms >= duration_ms:
        return None
    fade_start = duration_ms - fade_ms
    if elapsed_ms <= fade_start or fade_ms == 0:
        return 1.0
    return max(0.0, 1.0 - (elapsed_ms - fade_start) / fade_ms)
