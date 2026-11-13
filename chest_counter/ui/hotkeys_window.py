"""Окно «Горячие клавиши»: переназначение клавиш без правки config.json.

Как это работает: пользователь нажимает «Изменить», затем нужную комбинацию.
На время ожидания глобальные горячие клавиши отключаются — иначе Windows
перехватила бы нажатие (например, F9) раньше, чем оно дойдёт до этого окна.

Окно само ничего не регистрирует и не сохраняет: оно вызывает функции,
переданные из App, и показывает результат.
"""

from __future__ import annotations

import sys
import tkinter as tk
from tkinter import messagebox
from typing import Callable

from ..core.hotkeys import (
    MODIFIER_VKS,
    VK_ESCAPE,
    Hotkey,
    HotkeyError,
    binding_warning,
    hotkey_from_vk,
    parse_hotkey,
)
from . import theme

ACTIONS = (
    ("add", "+1 сундук"),
    ("undo", "Отменить последний"),
    ("end_match", "Завершить матч"),
)

HINT = (
    "Нажмите «Изменить», затем нужную клавишу. Подходят F1–F24, буквы, цифры, "
    "цифровой блок и другие клавиши — сами по себе или с Ctrl, Alt, Shift."
)
WAITING = "Нажмите клавишу или сочетание…  (Esc — отмена)"
NO_MOUSE = (
    "Кнопки мыши назначить нельзя: Windows умеет делать горячими только клавиши "
    "клавиатуры. Нажмите клавишу или Esc для отмены."
)
UNSUPPORTED = (
    "Эту клавишу Windows не позволяет сделать горячей. "
    "Нажмите другую или Esc для отмены."
)


class HotkeysWindow:
    def __init__(
        self,
        root: tk.Tk,
        get_bindings: Callable[[], dict[str, Hotkey]],
        change: Callable[[str, Hotkey], str | None],
        reset: Callable[[], str | None],
        suspend: Callable[[], None],
        resume: Callable[[], None],
        modifiers_down: Callable[[], tuple[bool, bool, bool]] | None = None,
        confirm: Callable[[str], bool] | None = None,
    ):
        """
        get_bindings   — текущие клавиши;
        change         — назначить клавишу действию; возвращает текст ошибки или None;
        reset          — вернуть клавиши по умолчанию; возвращает текст ошибки или None;
        suspend/resume — временно отключить и снова включить глобальные клавиши;
        modifiers_down — (Ctrl, Alt, Shift) зажаты ли сейчас (в Windows — через WinAPI);
        confirm        — задать вопрос «да/нет»; по умолчанию обычное окно с вопросом.
        """
        self._confirm = confirm or self._ask
        self._get_bindings = get_bindings
        self._change = change
        self._reset = reset
        self._suspend = suspend
        self._resume = resume
        self._modifiers_down = modifiers_down
        self._capturing: str | None = None  # действие, для которого ждём нажатия

        self.window = tk.Toplevel(root)
        self.window.title("Горячие клавиши")
        self.window.configure(bg=theme.BG)
        self.window.resizable(False, False)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<KeyPress>", self._on_key)
        self.window.bind("<FocusOut>", self._on_focus_out)
        # Правая, средняя и боковые кнопки мыши: объясняем, что их назначить нельзя.
        for number in (2, 3, 4, 5):
            try:
                self.window.bind(f"<Button-{number}>", self._on_mouse_button)
            except tk.TclError:
                pass  # в этой версии Tk такой кнопки нет

        body = tk.Frame(self.window, bg=theme.BG, padx=20, pady=16)
        body.pack(fill="both", expand=True)

        rows = tk.Frame(body, bg=theme.BG)
        rows.pack(fill="x")
        rows.columnconfigure(0, weight=1)
        self._labels: dict[str, tk.Label] = {}
        self._buttons: dict[str, tk.Button] = {}
        for row, (action, title) in enumerate(ACTIONS):
            tk.Label(
                rows, text=title, font=theme.font(11), bg=theme.BG, fg=theme.TEXT, anchor="w",
            ).grid(row=row, column=0, sticky="w", pady=5)
            label = tk.Label(
                rows, text="", font=theme.font(12, bold=True), bg=theme.CARD, fg=theme.ACCENT,
                width=16, pady=6,
            )
            label.grid(row=row, column=1, padx=12, pady=5)
            button = theme.make_button(rows, "Изменить", lambda a=action: self.start_capture(a))
            button.configure(padx=14)
            button.grid(row=row, column=2, pady=5)
            self._labels[action] = label
            self._buttons[action] = button

        self._message = tk.Label(
            body, text=HINT, font=theme.font(9), bg=theme.BG, fg=theme.MUTED,
            wraplength=400, justify="left", anchor="w", height=4,
        )
        self._message.pack(fill="x", pady=(10, 6))

        tk.Label(
            body,
            text="Назначенные клавиши перестают доходить до игры и других программ, "
                 "пока счётчик запущен. Выбирайте те, что в игре не используются.",
            font=theme.font(9), bg=theme.BG, fg=theme.MUTED, wraplength=400, justify="left", anchor="w",
        ).pack(fill="x", pady=(0, 12))

        bottom = tk.Frame(body, bg=theme.BG)
        bottom.pack(fill="x")
        default_button = theme.make_button(bottom, "По умолчанию", self.reset_defaults)
        default_button.configure(padx=14)
        default_button.pack(side="left")
        close_button = theme.make_button(bottom, "Закрыть", self.close)
        close_button.configure(padx=14)
        close_button.pack(side="right")

        self.refresh()

    # --- состояние окна ------------------------------------------------------

    def alive(self) -> bool:
        return bool(self.window.winfo_exists())

    def show(self) -> None:
        self.window.deiconify()
        self.window.lift()
        self.window.focus_force()

    def refresh(self) -> None:
        for action, hotkey in self._get_bindings().items():
            if action in self._labels:
                self._labels[action].configure(text=hotkey.label, fg=theme.ACCENT)

    def _ask(self, text: str) -> bool:
        return bool(messagebox.askyesno("Горячие клавиши", text, parent=self.window, icon="warning"))

    def _on_mouse_button(self, _event) -> None:
        if self._capturing is not None:
            self._say(NO_MOUSE, warning=True)

    def _say(self, text: str, warning: bool = False) -> None:
        self._message.configure(text=text, fg=theme.WARNING if warning else theme.MUTED)

    def close(self) -> None:
        self.cancel_capture()
        self.window.destroy()

    # --- ожидание нажатия ----------------------------------------------------

    def start_capture(self, action: str) -> None:
        self.cancel_capture()
        self._capturing = action
        self._suspend()  # иначе Windows «съест» уже назначенные клавиши
        self._labels[action].configure(text="…", fg=theme.TEXT)
        self._say(WAITING)
        self.window.focus_force()

    def cancel_capture(self) -> None:
        if self._capturing is None:
            return
        self._capturing = None
        self._resume()
        self.refresh()
        self._say(HINT)

    def _on_focus_out(self, _event) -> None:
        # FocusOut приходит и при переходе фокуса внутри самого окна, поэтому
        # чуть позже проверяем, действительно ли пользователь ушёл в другое окно.
        if self._capturing is not None:
            self.window.after(150, self._cancel_if_focus_left)

    def _cancel_if_focus_left(self) -> None:
        if self._capturing is None or not self.alive():
            return
        try:
            focused = self.window.focus_displayof()
        except (KeyError, tk.TclError):
            focused = None
        if focused is None or focused.winfo_toplevel() is not self.window:
            # Не оставляем глобальные клавиши отключёнными, пока окно не в фокусе.
            self.cancel_capture()

    def _on_key(self, event) -> str | None:
        if self._capturing is None:
            return None
        if sys.platform == "win32":
            # В Windows keycode — это и есть виртуальный код клавиши.
            vk = int(event.keycode)
            if vk in MODIFIER_VKS:
                return "break"  # ждём основную клавишу сочетания
            if vk == VK_ESCAPE:
                self.cancel_capture()
                return "break"
            ctrl, alt, shift = (
                self._modifiers_down() if self._modifiers_down else (False, False, False)
            )
            hotkey = hotkey_from_vk(vk, ctrl, alt, shift)
        else:
            hotkey = self._hotkey_from_keysym(event)
            if hotkey == "ignore":
                return "break"
            if hotkey == "cancel":
                self.cancel_capture()
                return "break"
        self.finish_capture(hotkey)
        return "break"

    @staticmethod
    def _hotkey_from_keysym(event):
        """Запасной способ для Mac/Linux (только для разработки)."""
        keysym = event.keysym
        if keysym == "Escape":
            return "cancel"
        if keysym.split("_")[0] in ("Shift", "Control", "Alt", "Meta", "Super", "Caps", "Num"):
            return "ignore"
        parts = [name for name, bit in (("Ctrl", 0x4), ("Shift", 0x1)) if event.state & bit]
        try:
            return parse_hotkey("+".join(parts + [keysym]))
        except HotkeyError:
            return None

    def finish_capture(self, hotkey: Hotkey | None) -> None:
        """Пробует назначить нажатую комбинацию действию, для которого шло ожидание."""
        action = self._capturing
        if action is None:
            return
        if hotkey is None:
            self._say(UNSUPPORTED, warning=True)
            return  # продолжаем ждать

        # Дальше ожидание закончено. Сбрасываем его до вопроса: окно с вопросом
        # забирает фокус, а потеря фокуса во время ожидания означает отмену.
        self._capturing = None
        warning = binding_warning(hotkey)
        if warning and not self._confirm(warning):
            self._resume()
            self.refresh()
            self._say("Клавиша не изменена.")
            return
        error = self._change(action, hotkey)
        if error:
            self._resume()  # клавиши остались прежними — включаем их обратно
            self.refresh()
            self._say(error, warning=True)
        else:
            self.refresh()
            self._say(f"Готово: {dict(ACTIONS)[action]} — {hotkey.label}.")

    def reset_defaults(self) -> None:
        self.cancel_capture()
        error = self._reset()
        self.refresh()
        if error:
            self._say(error, warning=True)
        else:
            self._say("Клавиши по умолчанию возвращены.")
