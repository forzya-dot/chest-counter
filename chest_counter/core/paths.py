"""Где лежат данные программы и её встроенные ресурсы."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "ChestCounter"

# Переменная окружения для тестов и самопроверки: позволяет не трогать настоящие данные.
DATA_DIR_ENV = "CHESTCOUNTER_DATA_DIR"


def data_dir() -> Path:
    """Папка с config.json и базой. На Windows это %APPDATA%\\ChestCounter."""
    override = os.environ.get(DATA_DIR_ENV)
    if override:
        path = Path(override)
    elif sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        path = base / APP_NAME
    else:
        # На Mac/Linux программа нужна только для разработки.
        path = Path.home() / ".chestcounter"
    path.mkdir(parents=True, exist_ok=True)
    return path


def resource_path(relative: str) -> Path:
    """Путь к файлу, упакованному внутрь .exe (или лежащему рядом при запуске из исходников).

    PyInstaller в режиме --onefile распаковывает ресурсы во временную папку
    и кладёт её путь в sys._MEIPASS.
    """
    base = getattr(sys, "_MEIPASS", None)
    if base is None:
        base = Path(__file__).resolve().parents[2]
    return Path(base) / relative
