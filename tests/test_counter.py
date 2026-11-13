from datetime import datetime

from chest_counter.core.counter import ChestCounter, Snapshot
from chest_counter.core.storage import Storage


def test_starts_at_zero(storage, clock):
    counter = ChestCounter(storage, clock)
    assert counter.snapshot() == Snapshot(0, 0, 0)


def test_add_increments(storage, clock):
    counter = ChestCounter(storage, clock)
    assert counter.add() == 1
    assert counter.add() == 2
    assert counter.snapshot() == Snapshot(2, 2, 2)


def test_undo_decrements_but_not_below_zero(storage, clock):
    counter = ChestCounter(storage, clock)
    counter.add()
    assert counter.undo() is True
    assert counter.current == 0
    assert counter.undo() is False
    assert counter.current == 0
    assert storage.get_current() == 0


def test_end_match_saves_and_resets(storage, clock):
    counter = ChestCounter(storage, clock)
    for _ in range(3):
        counter.add()
    assert counter.end_match() == 3
    assert counter.current == 0
    assert storage.all_matches() == [("2026-05-01", "20:30:00", 3)]
    # Сундуки завершённого матча остаются в «сегодня» и «за всё время».
    assert counter.snapshot() == Snapshot(0, 3, 3)


def test_empty_match_is_not_saved_by_default(storage, clock):
    counter = ChestCounter(storage, clock)
    assert counter.end_match() == 0
    assert storage.all_matches() == []


def test_empty_match_saved_when_enabled(storage, clock):
    counter = ChestCounter(storage, clock, save_empty_matches=True)
    counter.end_match()
    assert storage.all_matches() == [("2026-05-01", "20:30:00", 0)]


def test_today_counts_only_today(storage, clock):
    counter = ChestCounter(storage, clock)
    counter.add()
    counter.add()
    counter.end_match()

    clock.now = datetime(2026, 5, 2, 10, 0, 0)  # наступил следующий день
    counter.add()
    assert counter.snapshot() == Snapshot(current=1, today=1, all_time=3)


def test_current_match_survives_restart(db_path, clock):
    """Имитация сбоя: базу не закрываем, просто открываем заново."""
    first = Storage(db_path)
    counter = ChestCounter(first, clock)
    counter.add()
    counter.add()
    counter.add()
    counter.undo()

    second = Storage(db_path)
    restored = ChestCounter(second, clock)
    assert restored.current == 2
    second.close()
    first.close()


def test_counter_is_zero_after_restart_following_end_match(db_path, clock):
    first = Storage(db_path)
    counter = ChestCounter(first, clock)
    counter.add()
    counter.end_match()
    first.close()

    second = Storage(db_path)
    assert ChestCounter(second, clock).snapshot() == Snapshot(0, 1, 1)
    second.close()
