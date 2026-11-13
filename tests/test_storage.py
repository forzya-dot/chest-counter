import csv
from datetime import date, datetime

import pytest

from chest_counter.core.storage import DayStats, Summary


def _fill(storage):
    storage.finish_match(4, datetime(2026, 5, 1, 18, 0, 0))
    storage.finish_match(10, datetime(2026, 5, 1, 19, 0, 0))
    storage.finish_match(7, datetime(2026, 5, 2, 9, 15, 30))


def test_empty_database(storage):
    assert storage.get_current() == 0
    assert storage.daily_stats() == []
    assert storage.summary() == Summary(0, 0, 0.0, 0)
    assert storage.chests_total() == 0


def test_set_and_get_current(storage):
    storage.set_current(5)
    storage.set_current(6)
    assert storage.get_current() == 6


def test_finish_match_resets_current(storage):
    storage.set_current(9)
    storage.finish_match(9, datetime(2026, 5, 1, 12, 0, 0))
    assert storage.get_current() == 0


def test_finish_match_without_saving_still_resets(storage):
    storage.set_current(2)
    storage.finish_match(2, datetime(2026, 5, 1, 12, 0, 0), save=False)
    assert storage.get_current() == 0
    assert storage.all_matches() == []


def test_sums(storage):
    _fill(storage)
    assert storage.chests_on(date(2026, 5, 1)) == 14
    assert storage.chests_on(date(2026, 5, 2)) == 7
    assert storage.chests_on(date(2026, 5, 3)) == 0
    assert storage.chests_total() == 21


def test_daily_stats_newest_first(storage):
    _fill(storage)
    assert storage.daily_stats() == [
        DayStats("2026-05-02", 1, 7, 7.0, 7),
        DayStats("2026-05-01", 2, 14, 7.0, 10),
    ]


def test_summary(storage):
    _fill(storage)
    summary = storage.summary()
    assert (summary.matches, summary.chests, summary.record) == (3, 21, 10)
    assert summary.average == pytest.approx(7.0)


def test_export_csv(storage, tmp_path):
    _fill(storage)
    target = tmp_path / "out.csv"
    assert storage.export_csv(target) == 3

    # BOM нужен, чтобы Excel правильно показал кириллицу.
    assert target.read_bytes().startswith(b"\xef\xbb\xbf")
    with open(target, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f, delimiter=";"))
    assert rows == [
        ["Дата", "Время", "Сундуков"],
        ["2026-05-01", "18:00:00", "4"],
        ["2026-05-01", "19:00:00", "10"],
        ["2026-05-02", "09:15:30", "7"],
    ]


def test_export_csv_empty(storage, tmp_path):
    target = tmp_path / "empty.csv"
    assert storage.export_csv(target) == 0
    assert target.exists()
