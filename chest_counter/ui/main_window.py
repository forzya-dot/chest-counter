"""Главное окно: крупный счёт матча, итоги и три кнопки."""

from __future__ import annotations

import tkinter as tk
from typing import Callable

from ..core.counter import Snapshot
from . import theme


class MainWindow:
    def __init__(
        self,
        root: tk.Tk,
        on_add: Callable[[], None],
        on_undo: Callable[[], None],
        on_end_match: Callable[[], None],
        hotkey_labels: dict[str, str],
    ):
        self.root = root
        root.title("Счётчик сундуков")
        root.configure(bg=theme.BG)
        root.resizable(False, False)

        body = tk.Frame(root, bg=theme.BG, padx=22, pady=18)
        body.pack(fill="both", expand=True)

        tk.Label(
            body, text="СУНДУКОВ В МАТЧЕ", font=theme.font(10, bold=True),
            bg=theme.BG, fg=theme.MUTED,
        ).pack()

        self._current = tk.Label(
            body, text="0", font=theme.font(76, bold=True), bg=theme.BG, fg=theme.ACCENT,
            width=4,  # место под трёхзначное число, чтобы окно не «прыгало»
        )
        self._current.pack(pady=(0, 6))

        # Две карточки: «Сегодня» и «За всё время».
        cards = tk.Frame(body, bg=theme.BG)
        cards.pack(fill="x")
        cards.columnconfigure(0, weight=1, uniform="cards")
        cards.columnconfigure(1, weight=1, uniform="cards")
        self._today = self._make_card(cards, "Сегодня", 0)
        self._all_time = self._make_card(cards, "За всё время", 1)

        theme.make_button(
            body, f"+1 сундук   ({hotkey_labels['add']})", on_add, primary=True
        ).pack(fill="x", pady=(16, 8))

        row = tk.Frame(body, bg=theme.BG)
        row.pack(fill="x")
        row.columnconfigure(0, weight=1, uniform="buttons")
        row.columnconfigure(1, weight=1, uniform="buttons")
        theme.make_button(row, "Отменить", on_undo).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        theme.make_button(row, "Завершить матч", on_end_match).grid(
            row=0, column=1, sticky="ew", padx=(4, 0)
        )

        tk.Label(
            body,
            text=f"{hotkey_labels['undo']} — отменить   ·   {hotkey_labels['end_match']} — завершить",
            font=theme.font(9), bg=theme.BG, fg=theme.MUTED,
        ).pack(pady=(12, 0))

        # Строка для сообщений (например, «клавиша F9 занята»). Пустая — не занимает места.
        self._status = tk.Label(
            body, text="", font=theme.font(9), bg=theme.BG, fg=theme.WARNING,
            wraplength=300, justify="center",
        )

    @staticmethod
    def _make_card(parent: tk.Frame, title: str, column: int) -> tk.Label:
        card = tk.Frame(parent, bg=theme.CARD, padx=10, pady=8)
        card.grid(row=0, column=column, sticky="ew", padx=(0, 4) if column == 0 else (4, 0))
        tk.Label(card, text=title, font=theme.font(9), bg=theme.CARD, fg=theme.MUTED).pack()
        value = tk.Label(card, text="0", font=theme.font(20, bold=True), bg=theme.CARD, fg=theme.TEXT)
        value.pack()
        return value

    def update(self, snapshot: Snapshot) -> None:
        self._current.configure(text=str(snapshot.current))
        self._today.configure(text=str(snapshot.today))
        self._all_time.configure(text=str(snapshot.all_time))

    def set_status(self, text: str) -> None:
        self._status.configure(text=text)
        if text:
            self._status.pack(pady=(10, 0))
        else:
            self._status.pack_forget()
