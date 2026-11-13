"""Разбор строки вида "Ctrl+F9" в модификаторы и код клавиши для RegisterHotKey.

Здесь нет вызовов WinAPI — только таблицы и разбор текста.
"""

from __future__ import annotations

from dataclasses import dataclass

# Флаги модификаторов RegisterHotKey.
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008

_MODIFIERS = {
    "ctrl": (MOD_CONTROL, "Ctrl"),
    "control": (MOD_CONTROL, "Ctrl"),
    "alt": (MOD_ALT, "Alt"),
    "shift": (MOD_SHIFT, "Shift"),
    "win": (MOD_WIN, "Win"),
}

# Виртуальные коды клавиш (VK_*).
_KEYS: dict[str, tuple[int, str]] = {
    "space": (0x20, "Space"),
    "tab": (0x09, "Tab"),
    "pause": (0x13, "Pause"),
    "pageup": (0x21, "PageUp"),
    "pagedown": (0x22, "PageDown"),
    "end": (0x23, "End"),
    "home": (0x24, "Home"),
    "left": (0x25, "Left"),
    "up": (0x26, "Up"),
    "right": (0x27, "Right"),
    "down": (0x28, "Down"),
    "insert": (0x2D, "Insert"),
    "delete": (0x2E, "Delete"),
    "scrolllock": (0x91, "ScrollLock"),
}
_KEYS.update({f"f{n}": (0x70 + n - 1, f"F{n}") for n in range(1, 25)})          # F1..F24
_KEYS.update({f"num{n}": (0x60 + n, f"Num{n}") for n in range(10)})              # цифровой блок
_KEYS.update({str(n): (0x30 + n, str(n)) for n in range(10)})                    # 0..9
_KEYS.update({chr(c).lower(): (c, chr(c)) for c in range(ord("A"), ord("Z") + 1)})  # A..Z


# Обратная таблица: код клавиши -> её название.
_VK_TO_LABEL = {vk: label for vk, label in _KEYS.values()}

VK_ESCAPE = 0x1B

# Клавиши-модификаторы и переключатели: сами по себе горячей клавишей быть не могут.
MODIFIER_VKS = frozenset(
    {0x10, 0x11, 0x12, 0x14, 0x5B, 0x5C, 0x90, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5}
)

# Клавиши, которые можно назначать без Ctrl/Alt: ими не печатают текст.
_SAFE_ALONE = frozenset(
    [0x70 + n for n in range(24)]      # F1..F24
    + [0x60 + n for n in range(10)]    # цифровой блок
    + [0x13, 0x91]                     # Pause, ScrollLock
)


class HotkeyError(ValueError):
    """Строку с горячей клавишей не удалось разобрать."""


@dataclass(frozen=True)
class Hotkey:
    modifiers: int
    vk: int
    label: str  # аккуратная запись для показа пользователю, например "Ctrl+F9"


def parse_hotkey(text: str) -> Hotkey:
    parts = [p.strip().lower() for p in str(text).split("+")]
    if not parts or any(not p for p in parts):
        raise HotkeyError(f"Пустая или неверная запись клавиши: {text!r}")

    modifiers = 0
    labels: list[str] = []
    for name in parts[:-1]:
        if name not in _MODIFIERS:
            raise HotkeyError(f"Неизвестный модификатор «{name}» в {text!r}")
        flag, label = _MODIFIERS[name]
        if not modifiers & flag:
            modifiers |= flag
            labels.append(label)

    key = parts[-1]
    if key not in _KEYS:
        raise HotkeyError(f"Неизвестная клавиша «{key}» в {text!r}")
    vk, key_label = _KEYS[key]

    # Порядок как принято в Windows: Ctrl+Alt+Shift+Win+клавиша.
    order = ["Ctrl", "Alt", "Shift", "Win"]
    labels.sort(key=order.index)
    return Hotkey(modifiers, vk, "+".join(labels + [key_label]))


def hotkey_from_vk(vk: int, ctrl: bool = False, alt: bool = False, shift: bool = False) -> Hotkey | None:
    """Собирает горячую клавишу из кода нажатой клавиши и зажатых модификаторов.

    Используется окном настройки: пользователь нажимает комбинацию, а мы её запоминаем.
    None — такую клавишу программа не поддерживает.
    """
    label = _VK_TO_LABEL.get(int(vk))
    if label is None:
        return None
    parts = [name for name, pressed in (("Ctrl", ctrl), ("Alt", alt), ("Shift", shift)) if pressed]
    return parse_hotkey("+".join(parts + [label]))


def binding_problem(hotkey: Hotkey) -> str | None:
    """Почему клавишу не стоит назначать (или None, если всё в порядке).

    Зарегистрированная горячая клавиша перестаёт доходить до остальных программ.
    Если назначить просто букву или пробел, ими нельзя будет ни печатать, ни играть.
    """
    if hotkey.vk in _SAFE_ALONE:
        return None
    if hotkey.modifiers & (MOD_CONTROL | MOD_ALT | MOD_WIN):
        return None
    return (
        f"«{hotkey.label}» без Ctrl или Alt назначить нельзя: эта клавиша перестала бы "
        "работать в игре и других программах. Добавьте Ctrl или Alt либо выберите F1–F24."
    )


def has_duplicates(bindings: dict[str, Hotkey]) -> bool:
    """True, если одна и та же комбинация назначена на несколько действий."""
    combos = [(hotkey.modifiers, hotkey.vk) for hotkey in bindings.values()]
    return len(set(combos)) < len(combos)
