"""Чтение и запись config.json.

Правила:
- файла нет -> создаём с настройками по умолчанию;
- файл испорчен (не JSON) -> сохраняем его как config.json.bak и создаём заново;
- в файле не хватает ключей или значение не того типа -> берём значение по умолчанию.
"""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from typing import Any

DEFAULT_CONFIG: dict[str, Any] = {
    # Формат: "F9", "Ctrl+F9", "Ctrl+Shift+K" и т.п.
    "hotkeys": {
        "add": "F9",
        "undo": "Ctrl+F9",
        "end_match": "F10",
    },
    "sound": {
        "enabled": True,
    },
    "overlay": {
        "enabled": True,
        # Пусто = картинка, встроенная в программу. Можно указать путь к своему PNG.
        "image": "",
        # Размер картинки в пикселях (по большей стороне).
        "size": 160,
        # Сколько всего картинка видна и сколько из этого времени она плавно исчезает.
        "duration_ms": 1500,
        "fade_ms": 400,
        # Угол экрана: top-left, top-center, top-right, center,
        # bottom-left, bottom-center, bottom-right.
        "anchor": "top-right",
        # Отступы от выбранного края экрана в пикселях.
        "offset_x": 40,
        "offset_y": 120,
        # Показывать ли число рядом с картинкой.
        "show_count": True,
    },
    # Записывать ли в статистику матч, в котором не открыто ни одного сундука.
    "save_empty_matches": False,
}


def _merge(defaults: Any, user: Any) -> Any:
    """Накладывает пользовательские значения на значения по умолчанию с проверкой типов."""
    if isinstance(defaults, dict):
        if not isinstance(user, dict):
            return copy.deepcopy(defaults)
        return {key: _merge(value, user.get(key)) for key, value in defaults.items()}
    if isinstance(defaults, bool):
        return user if isinstance(user, bool) else defaults
    if isinstance(defaults, (int, float)):
        # bool — подкласс int, но true/false вместо числа нам не подходит.
        # Python-разборщик JSON пропускает NaN и Infinity — такие числа нам не нужны.
        if isinstance(user, (int, float)) and not isinstance(user, bool) and math.isfinite(user):
            return user
        return defaults
    if isinstance(defaults, str):
        return user if isinstance(user, str) else defaults
    return copy.deepcopy(defaults)


def save_config(path: Path, config: dict[str, Any]) -> None:
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _try_save(path: Path, config: dict[str, Any]) -> None:
    """Запись «по возможности»: если диск недоступен, работаем с настройками в памяти."""
    try:
        save_config(path, config)
    except OSError:
        pass


def load_config(path: Path) -> dict[str, Any]:
    """Возвращает полный конфиг; при необходимости создаёт или чинит файл."""
    if not path.exists():
        config = copy.deepcopy(DEFAULT_CONFIG)
        _try_save(path, config)
        return config

    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        # Не теряем то, что написал пользователь: кладём рядом как .bak.
        try:
            path.replace(path.with_name(path.name + ".bak"))
        except OSError:
            pass
        config = copy.deepcopy(DEFAULT_CONFIG)
        _try_save(path, config)
        return config

    config = _merge(DEFAULT_CONFIG, raw)
    if config != raw:
        # Дописываем недостающие ключи, чтобы их было видно в файле.
        _try_save(path, config)
    return config
