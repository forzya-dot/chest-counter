"""Окно статистики: итоги и таблица по дням."""

from __future__ import annotations

import tkinter as tk
from datetime import datetime
from tkinter import ttk
from typing import Callable

from ..core.storage import Storage
from . import theme


def _ru_date(iso: str) -> str:
    """2026-05-01 -> 01.05.2026"""
    try:
        return datetime.strptime(iso, "%Y-%m-%d").strftime("%d.%m.%Y")
    except ValueError:
        return iso


def _num(value: float) -> str:
    """Среднее с одним знаком и запятой, как принято в русском: 7,5"""
    return f"{value:.1f}".replace(".", ",")


class StatsWindow:
    def __init__(self, root: tk.Tk, storage: Storage, on_export: Callable[[], None]):
        self._storage = storage
        self.window = tk.Toplevel(root)
        self.window.title("Статистика сундуков")
        self.window.configure(bg=theme.BG)
        self.window.geometry("560x460")
        self.window.minsize(480, 320)

        body = tk.Frame(self.window, bg=theme.BG, padx=18, pady=16)
        body.pack(fill="both", expand=True)

        # Четыре итоговые карточки.
        cards = tk.Frame(body, bg=theme.BG)
        cards.pack(fill="x")
        self._values: list[tk.Label] = []
        for column, title in enumerate(["Всего матчей", "Всего сундуков", "Среднее за матч", "Рекорд за матч"]):
            cards.columnconfigure(column, weight=1, uniform="cards")
            card = tk.Frame(cards, bg=theme.CARD, padx=8, pady=8)
            card.grid(row=0, column=column, sticky="ew", padx=3)
            tk.Label(card, text=title, font=theme.font(9), bg=theme.CARD, fg=theme.MUTED).pack()
            value = tk.Label(card, text="0", font=theme.font(18, bold=True), bg=theme.CARD, fg=theme.ACCENT)
            value.pack()
            self._values.append(value)

        # Таблица по дням. Тема clam позволяет перекрасить Treeview в тёмные цвета.
        style = ttk.Style(self.window)
        style.theme_use("clam")
        style.configure(
            "Dark.Treeview", background=theme.CARD, fieldbackground=theme.CARD,
            foreground=theme.TEXT, rowheight=26, borderwidth=0, font=theme.font(10),
        )
        style.configure(
            "Dark.Treeview.Heading", background=theme.BG, foreground=theme.MUTED,
            relief="flat", font=theme.font(9, bold=True),
        )
        style.map("Dark.Treeview", background=[("selected", theme.CARD_HOVER)],
                  foreground=[("selected", theme.TEXT)])
        style.map("Dark.Treeview.Heading", background=[("active", theme.BG)])

        table = tk.Frame(body, bg=theme.BG)
        table.pack(fill="both", expand=True, pady=(14, 12))
        columns = ("date", "matches", "chests", "average", "best")
        titles = ("Дата", "Матчей", "Сундуков", "Среднее", "Лучший матч")
        self._tree = ttk.Treeview(table, columns=columns, show="headings", style="Dark.Treeview")
        for name, title in zip(columns, titles):
            self._tree.heading(name, text=title)
            self._tree.column(name, anchor="center", width=90, stretch=True)
        scrollbar = ttk.Scrollbar(table, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=scrollbar.set)
        self._tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self._empty = tk.Label(
            body, text="Пока нет ни одного завершённого матча.",
            font=theme.font(10), bg=theme.BG, fg=theme.MUTED,
        )

        theme.make_button(body, "Экспорт в CSV", on_export).pack(side="right", ipadx=14)

        self.refresh()

    def alive(self) -> bool:
        return bool(self.window.winfo_exists())

    def show(self) -> None:
        self.window.deiconify()
        self.window.lift()
        self.window.focus_force()

    def refresh(self) -> None:
        summary = self._storage.summary()
        for label, text in zip(
            self._values,
            [str(summary.matches), str(summary.chests), _num(summary.average), str(summary.record)],
        ):
            label.configure(text=text)

        self._tree.delete(*self._tree.get_children())
        days = self._storage.daily_stats()
        for day in days:
            self._tree.insert(
                "", "end",
                values=(_ru_date(day.date), day.matches, day.chests, _num(day.average), day.best),
            )
        if days:
            self._empty.pack_forget()
        else:
            self._empty.pack(side="left")
