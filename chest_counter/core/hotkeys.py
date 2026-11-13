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
