"""Хранение в SQLite: завершённые матчи и счётчик текущего матча.

Счётчик текущего матча лежит в той же базе и записывается (commit) после каждого
изменения, поэтому он переживает сбой программы или компьютера.
"""

from __future__ import annotations

import csv
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS matches (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    date   TEXT    NOT NULL,   -- ГГГГ-ММ-ДД
    time   TEXT    NOT NULL,   -- ЧЧ:ММ:СС
    chests INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_matches_date ON matches(date);
CREATE TABLE IF NOT EXISTS state (
    key   TEXT PRIMARY KEY,
    value INTEGER NOT NULL
);
"""


@dataclass(frozen=True)
class DayStats:
    date: str
    matches: int
    chests: int
    average: float
    best: int


@dataclass(frozen=True)
class Summary:
    matches: int
    chests: int
    average: float
    record: int


class Storage:
    def __init__(self, db_path: Path | str):
        self._conn = sqlite3.connect(str(db_path))
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # --- счётчик текущего матча -------------------------------------------

    def get_current(self) -> int:
        row = self._conn.execute("SELECT value FROM state WHERE key = 'current'").fetchone()
        return max(0, int(row[0])) if row else 0

    def set_current(self, value: int) -> None:
        with self._conn:  # commit при выходе из блока
            self._conn.execute(
                "INSERT INTO state(key, value) VALUES('current', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (int(value),),
            )

    # --- матчи -------------------------------------------------------------

    def finish_match(self, chests: int, when: datetime, save: bool = True) -> None:
        """Записывает матч и обнуляет текущий счётчик одной транзакцией."""
        with self._conn:
            if save:
                self._conn.execute(
                    "INSERT INTO matches(date, time, chests) VALUES(?, ?, ?)",
                    (when.strftime("%Y-%m-%d"), when.strftime("%H:%M:%S"), int(chests)),
                )
            self._conn.execute(
                "INSERT INTO state(key, value) VALUES('current', 0) "
                "ON CONFLICT(key) DO UPDATE SET value = 0"
            )

    def chests_on(self, day: date) -> int:
        row = self._conn.execute(
            "SELECT COALESCE(SUM(chests), 0) FROM matches WHERE date = ?",
            (day.strftime("%Y-%m-%d"),),
        ).fetchone()
        return int(row[0])

    def chests_total(self) -> int:
        row = self._conn.execute("SELECT COALESCE(SUM(chests), 0) FROM matches").fetchone()
        return int(row[0])

    def all_matches(self) -> list[tuple[str, str, int]]:
        return [
            (str(d), str(t), int(c))
            for d, t, c in self._conn.execute(
                "SELECT date, time, chests FROM matches ORDER BY date, time, id"
            )
        ]

    # --- статистика --------------------------------------------------------

    def daily_stats(self) -> list[DayStats]:
        """Статистика по дням, свежие дни сверху."""
        rows = self._conn.execute(
            "SELECT date, COUNT(*), SUM(chests), AVG(chests), MAX(chests) "
            "FROM matches GROUP BY date ORDER BY date DESC"
        )
        return [DayStats(str(d), int(n), int(s), float(a), int(m)) for d, n, s, a, m in rows]

    def summary(self) -> Summary:
        n, s, a, m = self._conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(chests), 0), COALESCE(AVG(chests), 0), "
            "COALESCE(MAX(chests), 0) FROM matches"
        ).fetchone()
        return Summary(int(n), int(s), float(a), int(m))

    # --- экспорт -----------------------------------------------------------

    def export_csv(self, path: Path | str) -> int:
        """Выгружает все матчи в CSV. Возвращает число строк.

        utf-8-sig и разделитель «;» — чтобы файл сразу правильно открывался
        в русском Excel.
        """
        rows = self.all_matches()
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(["Дата", "Время", "Сундуков"])
            writer.writerows(rows)
        return len(rows)
