"""Состояние клавиш-модификаторов (нужно окну настройки горячих клавиш).

GetKeyState только сообщает, зажаты ли Ctrl/Alt/Shift в момент обработки
нажатия в нашем собственном окне. Это не перехват клавиатуры.
"""

from __future__ import annotations

from ctypes import c_int, c_short

from ._dll import system_dll

VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12  # Alt

_user32 = system_dll("user32")
_user32.GetKeyState.argtypes = [c_int]
_user32.GetKeyState.restype = c_short


def _down(vk: int) -> bool:
    return bool(_user32.GetKeyState(vk) & 0x8000)


def modifiers_down() -> tuple[bool, bool, bool]:
    """(Ctrl, Alt, Shift) — зажаты ли сейчас."""
    return _down(VK_CONTROL), _down(VK_MENU), _down(VK_SHIFT)
