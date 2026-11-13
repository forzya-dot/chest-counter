"""Счётчик сундуков: +1, отмена, завершение матча."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from .storage import Storage


@dataclass(frozen=True)
class Snapshot:
    """Три числа, которые показывает главное окно."""

    current: int   # в текущем матче
    today: int     # за сегодня (завершённые сегодня матчи + текущий)
    all_time: int  # за всё время (все завершённые матчи + текущий)


class ChestCounter:
    def __init__(
        self,
        storage: Storage,
        clock: Callable[[], datetime] = datetime.now,
        save_empty_matches: bool = False,
    ):
        self._storage = storage
        self._clock = clock  # подменяется в тестах
        self._save_empty = save_empty_matches
        # Восстанавливаем счётчик после перезапуска или сбоя.
        self._current = storage.get_current()

    @property
    def current(self) -> int:
        return self._current

    def add(self) -> int:
        """+1 сундук. Возвращает новый счёт матча."""
        self._current += 1
        self._storage.set_current(self._current)
        return self._current

    def undo(self) -> bool:
        """-1 сундук, но не ниже нуля. Возвращает False, если отменять нечего."""
        if self._current <= 0:
            return False
        self._current -= 1
        self._storage.set_current(self._current)
        return True

    def end_match(self) -> int:
        """Сохраняет матч в статистику и обнуляет счётчик. Возвращает счёт матча.

        Матч без сундуков по умолчанию не записывается: так случайное двойное
        нажатие F10 не портит среднее.
        """
        chests = self._current
        save = chests > 0 or self._save_empty
        self._storage.finish_match(chests, self._clock(), save=save)
        self._current = 0
        return chests

    def snapshot(self) -> Snapshot:
        today = self._storage.chests_on(self._clock().date())
        total = self._storage.chests_total()
        return Snapshot(self._current, today + self._current, total + self._current)
