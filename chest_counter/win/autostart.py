"""Автозапуск с Windows через раздел реестра текущего пользователя.

HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run — права администратора не нужны.
"""

from __future__ import annotations

import sys
import winreg
from pathlib import Path

from ..core.autostart import build_command

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = "ChestCounter"


def _command() -> str:
    if getattr(sys, "frozen", False):
        # Собранный .exe: sys.executable — это он сам.
        return build_command(sys.executable)
    # Запуск из исходников (для разработки).
    script = Path(sys.argv[0]).resolve()
    return build_command(sys.executable, str(script))


def is_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            winreg.QueryValueEx(key, _VALUE_NAME)
        return True
    except OSError:
        return False


def set_enabled(enabled: bool) -> None:
    # CreateKeyEx, а не OpenKey: у нового пользователя раздела Run может ещё не быть.
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, _VALUE_NAME, 0, winreg.REG_SZ, _command())
        else:
            try:
                winreg.DeleteValue(key, _VALUE_NAME)
            except FileNotFoundError:
                pass
