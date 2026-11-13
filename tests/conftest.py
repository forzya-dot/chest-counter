import sys
from datetime import datetime
from pathlib import Path

import pytest

# Чтобы тесты находили пакет chest_counter без установки.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chest_counter.core.storage import Storage  # noqa: E402


class FakeClock:
    """Часы, которые можно переводить вручную."""

    def __init__(self, now: datetime):
        self.now = now

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock():
    return FakeClock(datetime(2026, 5, 1, 20, 30, 0))


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "stats.db"


@pytest.fixture
def storage(db_path):
    s = Storage(db_path)
    yield s
    s.close()
