import pytest

from chest_counter.core.autostart import build_command
from chest_counter.core.config import DEFAULT_CONFIG
from chest_counter.core.hotkeys import (
    MOD_ALT,
    MOD_CONTROL,
    MOD_SHIFT,
    Hotkey,
    HotkeyError,
    parse_hotkey,
)


def test_plain_function_key():
    assert parse_hotkey("F9") == Hotkey(0, 0x78, "F9")
    assert parse_hotkey("F10") == Hotkey(0, 0x79, "F10")


def test_with_modifier():
    assert parse_hotkey("Ctrl+F9") == Hotkey(MOD_CONTROL, 0x78, "Ctrl+F9")


def test_case_spaces_and_order_are_normalised():
    hotkey = parse_hotkey(" shift + ALT+control + k ")
    assert hotkey.modifiers == MOD_CONTROL | MOD_ALT | MOD_SHIFT
    assert hotkey.vk == ord("K")
    assert hotkey.label == "Ctrl+Alt+Shift+K"


def test_digits_and_numpad():
    assert parse_hotkey("5").vk == 0x35
    assert parse_hotkey("Num5").vk == 0x65


@pytest.mark.parametrize("bad", ["", "Ctrl+", "+F9", "Ctrl", "Foo+F9", "F25", "Ctrl+Жук"])
def test_bad_strings_raise(bad):
    with pytest.raises(HotkeyError):
        parse_hotkey(bad)


def test_default_config_hotkeys_are_valid_and_distinct():
    parsed = [parse_hotkey(v) for v in DEFAULT_CONFIG["hotkeys"].values()]
    assert len({(h.modifiers, h.vk) for h in parsed}) == 3


def test_autostart_command_for_exe():
    assert (
        build_command(r"C:\Program Files\ChestCounter.exe")
        == r'"C:\Program Files\ChestCounter.exe" --minimized'
    )


def test_autostart_command_for_script():
    assert (
        build_command(r"C:\Py\pythonw.exe", r"C:\src\main.py")
        == r'"C:\Py\pythonw.exe" "C:\src\main.py" --minimized'
    )
