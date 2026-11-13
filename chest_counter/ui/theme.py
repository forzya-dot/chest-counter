"""Цвета и шрифты тёмной темы."""

import tkinter as tk

BG = "#14161a"          # фон окна
CARD = "#1e2128"        # фон карточек и вторичных кнопок
CARD_HOVER = "#2a2e37"
TEXT = "#e8eaed"
MUTED = "#8b919c"
ACCENT = "#f5b942"      # «золото»: главная цифра и главная кнопка
ACCENT_HOVER = "#ffcc66"
ACCENT_TEXT = "#1a1300"
WARNING = "#ff8a65"

FONT = "Segoe UI"  # есть в любой Windows 10/11


def font(size: int, bold: bool = False) -> tuple:
    return (FONT, size, "bold") if bold else (FONT, size, "normal")


def make_button(parent, text, command, primary=False) -> tk.Button:
    """Плоская кнопка с подсветкой при наведении."""
    bg, hover, fg = (ACCENT, ACCENT_HOVER, ACCENT_TEXT) if primary else (CARD, CARD_HOVER, TEXT)
    button = tk.Button(
        parent,
        text=text,
        command=command,
        font=font(14 if primary else 11, bold=primary),
        bg=bg,
        fg=fg,
        activebackground=hover,
        activeforeground=fg,
        relief="flat",
        bd=0,
        highlightthickness=0,
        cursor="hand2",
        takefocus=0,
        pady=12 if primary else 9,
    )
    button.bind("<Enter>", lambda _e: button.configure(bg=hover))
    button.bind("<Leave>", lambda _e: button.configure(bg=bg))
    return button
