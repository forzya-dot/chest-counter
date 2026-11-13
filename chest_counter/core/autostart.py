"""Строка команды для автозапуска (сама запись в реестр — в win/autostart.py)."""

from __future__ import annotations

# С этим флагом программа стартует сразу в трей, без окна.
MINIMIZED_FLAG = "--minimized"


def build_command(executable: str, script: str | None = None) -> str:
    """Команда запуска.

    Собранный .exe: "C:\\...\\ChestCounter.exe" --minimized
    Из исходников:  "C:\\...\\pythonw.exe" "C:\\...\\main.py" --minimized
    """
    parts = [f'"{executable}"']
    if script:
        parts.append(f'"{script}"')
    parts.append(MINIMIZED_FLAG)
    return " ".join(parts)
