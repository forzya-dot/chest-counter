"""Безопасная загрузка системных библиотек Windows.

Если загружать DLL просто по имени, Windows сначала ищет её в папке самой
программы. Тогда поддельный файл user32.dll или shcore.dll, подложенный рядом
с ChestCounter.exe (например, в «Загрузках»), мог бы выполниться вместо
настоящего. Флаг LOAD_LIBRARY_SEARCH_SYSTEM32 разрешает искать только
в системной папке Windows.
"""

from __future__ import annotations

import ctypes

LOAD_LIBRARY_SEARCH_SYSTEM32 = 0x00000800


def system_dll(name: str) -> ctypes.WinDLL:
    return ctypes.WinDLL(name, use_last_error=True, winmode=LOAD_LIBRARY_SEARCH_SYSTEM32)
