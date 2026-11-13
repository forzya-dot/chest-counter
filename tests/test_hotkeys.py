import pytest

from chest_counter.core.autostart import build_command
from chest_counter.core.config import DEFAULT_CONFIG
from chest_counter.core.hotkeys import (
    MOD_ALT,
    MOD_CONTROL,
    MOD_SHIFT,
    MODIFIER_VKS,
    Hotkey,
    HotkeyError,
    binding_warning,
    has_duplicates,
    hotkey_from_vk,
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


# --- переназначение клавиш ---------------------------------------------------


def test_hotkey_from_vk_plain_and_with_modifiers():
    assert hotkey_from_vk(0x78) == parse_hotkey("F9")
    assert hotkey_from_vk(0x78, ctrl=True) == parse_hotkey("Ctrl+F9")
    assert hotkey_from_vk(ord("K"), ctrl=True, alt=True, shift=True).label == "Ctrl+Alt+Shift+K"
    assert hotkey_from_vk(0x65).label == "Num5"


def test_hotkey_from_vk_roundtrips_through_config_text():
    """То, что записано в config.json, должно читаться обратно в ту же клавишу."""
    for vk in (0x70, 0x87, 0x30, 0x5A, 0x60, 0x20, 0x2D):
        hotkey = hotkey_from_vk(vk, ctrl=True, shift=True)
        assert parse_hotkey(hotkey.label) == hotkey


def test_hotkey_from_vk_unknown_key():
    assert hotkey_from_vk(0xFF) is None
    assert hotkey_from_vk(0x1B) is None  # Esc — это отмена, а не клавиша
    for vk in MODIFIER_VKS:
        assert hotkey_from_vk(vk) is None


@pytest.mark.parametrize(
    "text", ["F9", "F24", "Num0", "NumPlus", "Pause", "Ctrl+K", "Alt+1", "Ctrl+Shift+Space"]
)
def test_safe_bindings_need_no_warning(text):
    assert binding_warning(parse_hotkey(text)) is None


@pytest.mark.parametrize("text", ["K", "1", "Space", "Shift+K", "Tab", "Left", "Delete", "Enter", "["])
def test_typing_keys_get_a_warning_question(text):
    """Это предупреждение, а не запрет: текст заканчивается вопросом."""
    warning = binding_warning(parse_hotkey(text))
    assert warning and "Ctrl" in warning and warning.rstrip().endswith("?")


def test_punctuation_and_numpad_operations_are_supported():
    assert hotkey_from_vk(0xDB).label == "["
    assert hotkey_from_vk(0xDC).label == "\\"
    assert hotkey_from_vk(0xC0, ctrl=True).label == "Ctrl+`"
    assert hotkey_from_vk(0x6B).label == "NumPlus"
    assert hotkey_from_vk(0x0D).label == "Enter"
    # Каждая поддерживаемая клавиша должна читаться обратно из config.json.
    from chest_counter.core.hotkeys import _VK_TO_LABEL

    for vk, label in _VK_TO_LABEL.items():
        assert "+" not in label, label
        assert parse_hotkey(label).vk == vk
        assert parse_hotkey("Ctrl+Alt+" + label).vk == vk


def test_has_duplicates():
    keys = {"add": parse_hotkey("F9"), "undo": parse_hotkey("Ctrl+F9"), "end_match": parse_hotkey("F10")}
    assert not has_duplicates(keys)
    keys["end_match"] = parse_hotkey("f9")
    assert has_duplicates(keys)
