"""Запуск всей программы в режиме самопроверки (--self-test).

Программа открывает окно, делает +1, показывает статистику, завершает матч
и выходит. Работает и на Mac (без Windows-частей), и на Windows (со всеми).
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_self_test_run(tmp_path):
    env = dict(os.environ, CHESTCOUNTER_DATA_DIR=str(tmp_path))
    result = subprocess.run(
        [sys.executable, str(ROOT / "main.py"), "--self-test"],
        env=env, cwd=str(ROOT), timeout=60, capture_output=True, text=True,
    )
    log_text = (tmp_path / "app.log").read_text(encoding="utf-8") if (tmp_path / "app.log").exists() else ""
    assert result.returncode == 0, f"stderr:\n{result.stderr}\napp.log:\n{log_text}"
    assert "Самопроверка: OK" in log_text
    assert (tmp_path / "config.json").exists()
    assert (tmp_path / "stats.db").exists()
