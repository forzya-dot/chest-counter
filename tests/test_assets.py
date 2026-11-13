from PIL import Image

from chest_counter.app import _load_icon
from chest_counter.core.paths import resource_path


def test_bundled_picture_exists():
    image = Image.open(resource_path("assets/chest.png"))
    assert image.format == "PNG" and image.mode == "RGBA"


def test_icon_is_square_and_not_empty():
    icon = _load_icon(64)
    assert icon.size == (64, 64)
    assert icon.getchannel("A").getbbox() is not None
