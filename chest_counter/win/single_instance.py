"""Защита от запуска второй копии.

Вторая копия не смогла бы зарегистрировать те же горячие клавиши,
поэтому просто не даём ей стартовать.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

ERROR_ALREADY_EXISTS = 183

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
_kernel32.CreateMutexW.restype = wintypes.HANDLE

_handle = None  # держим ссылку, пока программа работает


def acquire(name: str = "Local\\ChestCounter_SingleInstance") -> bool:
    """True — мы первая копия. False — программа уже запущена."""
    global _handle
    _handle = _kernel32.CreateMutexW(None, False, name)
    return ctypes.get_last_error() != ERROR_ALREADY_EXISTS
