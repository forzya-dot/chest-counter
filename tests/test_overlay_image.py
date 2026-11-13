import pytest
from PIL import Image

from chest_counter.core import overlay_image as oi
from chest_counter.core.paths import resource_path


def test_bundled_image_exists_and_has_transparency():
    image = Image.open(resource_path("assets/chest.png"))
    assert image.mode == "RGBA"
    lo, hi = image.getchannel("A").getextrema()
    assert lo == 0 and hi == 255  # есть и прозрачные, и непрозрачные пиксели


def test_load_image_falls_back_to_placeholder(tmp_path):
    broken = tmp_path / "broken.png"
    broken.write_bytes(b"not a png")
    for path in (None, "", tmp_path / "missing.png", broken):
        image = oi.load_image(path)
        assert image.mode == "RGBA"
        assert image.size == (256, 256)


def test_fit_image_keeps_aspect_ratio():
    wide = Image.new("RGBA", (400, 200))
    assert oi.fit_image(wide, 100).size == (100, 50)
    tall = Image.new("RGBA", (50, 200))
    assert oi.fit_image(tall, 100).size == (25, 100)  # маленькие картинки увеличиваются


def test_fit_image_clamps_silly_sizes():
    image = Image.new("RGBA", (100, 100))
    assert oi.fit_image(image, 0).size == (16, 16)
    assert oi.fit_image(image, -5).size == (16, 16)


def test_compose_without_count_is_just_the_picture():
    picture = oi.fit_image(oi.placeholder_image(), 120)
    assert oi.compose(picture, None).size == picture.size


def test_compose_adds_number_to_the_right():
    picture = oi.fit_image(oi.placeholder_image(), 120)
    frame = oi.compose(picture, 7)
    assert frame.width > picture.width
    assert frame.height >= picture.height
    # Справа от картинки что-то нарисовано (число).
    right_part = frame.crop((picture.width, 0, frame.width, frame.height))
    assert right_part.getchannel("A").getbbox() is not None


def test_compose_grows_with_more_digits():
    picture = oi.fit_image(oi.placeholder_image(), 120)
    assert oi.compose(picture, 123).width > oi.compose(picture, 1).width


def test_flatten_replaces_transparent_pixels_with_key_color():
    frame = Image.new("RGBA", (3, 1))
    frame.putpixel((0, 0), (255, 0, 0, 255))   # непрозрачный
    frame.putpixel((1, 0), (0, 255, 0, 40))    # почти прозрачный -> ключевой цвет
    frame.putpixel((2, 0), (0, 0, 255, 200))   # почти непрозрачный -> остаётся
    flat = oi.flatten_for_colorkey(frame)
    assert flat.mode == "RGB"
    assert flat.getpixel((0, 0)) == (255, 0, 0)
    assert flat.getpixel((1, 0)) == oi.KEY_COLOR
    assert flat.getpixel((2, 0)) == (0, 0, 255)


def test_flatten_does_not_punch_holes_where_art_matches_key_color():
    frame = Image.new("RGBA", (1, 1), oi.KEY_COLOR + (255,))
    assert oi.flatten_for_colorkey(frame).getpixel((0, 0)) == (0, 0, 0)


def test_key_color_hex_matches_tuple():
    assert oi.KEY_COLOR_HEX == "#%02x%02x%02x" % oi.KEY_COLOR


@pytest.mark.parametrize(
    "anchor, expected",
    [
        ("top-left", (40, 120)),
        ("top-right", (1920 - 200 - 40, 120)),
        ("bottom-left", (40, 1080 - 100 - 120)),
        ("bottom-right", (1920 - 200 - 40, 1080 - 100 - 120)),
        ("top-center", ((1920 - 200) // 2 + 40, 120)),
        ("center", ((1920 - 200) // 2 + 40, (1080 - 100) // 2 + 120)),
        ("непонятно", (1920 - 200 - 40, 120)),  # неизвестный угол -> top-right
    ],
)
def test_compute_position(anchor, expected):
    assert oi.compute_position(1920, 1080, 200, 100, anchor, 40, 120) == expected


def test_position_is_clamped_to_screen():
    assert oi.compute_position(1920, 1080, 200, 100, "top-left", -500, -500) == (0, 0)
    assert oi.compute_position(1920, 1080, 200, 100, "top-left", 5000, 5000) == (1720, 980)
    # Окно больше экрана — прижимаем к левому верхнему углу.
    assert oi.compute_position(100, 100, 200, 300, "bottom-right", 10, 10) == (0, 0)


def test_alpha_timeline():
    assert oi.alpha_at(0, 1500, 400) == 1.0
    assert oi.alpha_at(1100, 1500, 400) == 1.0          # затухание ещё не началось
    assert oi.alpha_at(1300, 1500, 400) == pytest.approx(0.5)
    assert 0 < oi.alpha_at(1499, 1500, 400) < 0.01
    assert oi.alpha_at(1500, 1500, 400) is None         # пора прятать
    assert oi.alpha_at(9999, 1500, 400) is None


def test_alpha_with_odd_settings():
    assert oi.alpha_at(100, 1000, 0) == 1.0             # без затухания
    assert oi.alpha_at(500, 1000, 5000) == pytest.approx(0.5)  # затухание длиннее показа
    assert oi.alpha_at(50, -10, 0) == 1.0               # длительность не меньше 100 мс
    assert oi.alpha_at(150, -10, 0) is None
