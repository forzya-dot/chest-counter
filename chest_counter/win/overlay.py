"""Окно с картинкой поверх всех окон.

Это обычное собственное окно нашей программы — в процесс игры оно никак
не вмешивается. Ему выставлены расширенные стили Windows:

- WS_EX_LAYERED     — окно с прозрачностью (нужно для плавного исчезновения);
- WS_EX_TRANSPARENT — клики мыши проходят сквозь окно в игру;
- WS_EX_NOACTIVATE  — окно не забирает фокус у игры;
- WS_EX_TOOLWINDOW  — окна нет на панели задач и в Alt+Tab;
- topmost           — поверх остальных окон.

Показываем и прячем окно напрямую через ShowWindow(SW_SHOWNOACTIVATE),
чтобы гарантированно не активировать его.
"""

from __future__ import annotations

import ctypes
import time
import tkinter as tk
from ctypes import wintypes
from typing import Any

from PIL import Image, ImageTk

from ..core import overlay_image

GWL_EXSTYLE = -20
WS_EX_TOPMOST = 0x00000008
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000
OVERLAY_EX_STYLE = (
    WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST
)

GA_ROOT = 2
SW_HIDE = 0
SW_SHOWNOACTIVATE = 4
HWND_TOPMOST = wintypes.HWND(-1)
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010

FRAME_MS = 30  # шаг анимации исчезновения

_user32 = ctypes.WinDLL("user32", use_last_error=True)

# В 64-битном Python нужны *LongPtr-функции; в 32-битном их нет.
_get_ex_style = getattr(_user32, "GetWindowLongPtrW", None) or _user32.GetWindowLongW
_set_ex_style = getattr(_user32, "SetWindowLongPtrW", None) or _user32.SetWindowLongW
_get_ex_style.argtypes = [wintypes.HWND, ctypes.c_int]
_get_ex_style.restype = ctypes.c_ssize_t
_set_ex_style.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
_set_ex_style.restype = ctypes.c_ssize_t
_user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
_user32.GetAncestor.restype = wintypes.HWND
_user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.ShowWindow.restype = wintypes.BOOL
_user32.SetWindowPos.argtypes = [
    wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT,
]
_user32.SetWindowPos.restype = wintypes.BOOL
_user32.IsWindowVisible.argtypes = [wintypes.HWND]
_user32.IsWindowVisible.restype = wintypes.BOOL


class Overlay:
    def __init__(self, root: tk.Tk, settings: dict[str, Any], picture: Image.Image):
        """settings — раздел "overlay" из config.json, picture — исходная картинка."""
        self._settings = settings
        # Масштабируем один раз, а не при каждом показе.
        self._picture = overlay_image.fit_image(picture, settings["size"])
        self._photo: ImageTk.PhotoImage | None = None
        self._timer: str | None = None
        self._shown_at = 0.0

        self._win = tk.Toplevel(root)
        self._win.overrideredirect(True)  # без рамки и заголовка
        self._win.configure(bg=overlay_image.KEY_COLOR_HEX)
        self._win.attributes("-topmost", True)
        self._win.attributes("-transparentcolor", overlay_image.KEY_COLOR_HEX)
        self._win.attributes("-alpha", 0.0)
        self._label = tk.Label(self._win, bg=overlay_image.KEY_COLOR_HEX, bd=0, highlightthickness=0)
        self._label.pack()
        self._win.update_idletasks()

        self._apply_styles()
        _user32.ShowWindow(self._hwnd(), SW_HIDE)

    # --- служебное ---------------------------------------------------------

    def _hwnd(self) -> int:
        """Дескриптор окна верхнего уровня.

        winfo_id() — это внутреннее окно Tk, а стили ставятся на его «обёртку».
        Tk может пересоздать обёртку, поэтому ищем её каждый раз заново.
        """
        return _user32.GetAncestor(self._win.winfo_id(), GA_ROOT)

    def _apply_styles(self) -> None:
        """Добавляет наши стили. Вызывается повторно: Tk может их сбрасывать."""
        hwnd = self._hwnd()
        current = _get_ex_style(hwnd, GWL_EXSTYLE)
        wanted = current | OVERLAY_EX_STYLE
        if wanted != current:
            _set_ex_style(hwnd, GWL_EXSTYLE, wanted)

    def ex_style(self) -> int:
        """Текущие расширенные стили окна (для тестов)."""
        return int(_get_ex_style(self._hwnd(), GWL_EXSTYLE))

    def on_screen(self) -> bool:
        """Видно ли окно с точки зрения Windows (для тестов)."""
        return bool(_user32.IsWindowVisible(self._hwnd()))

    def _set_alpha(self, alpha: float) -> None:
        self._win.attributes("-alpha", alpha)
        self._apply_styles()

    # --- показ -------------------------------------------------------------

    def show(self, count: int) -> None:
        """Показывает картинку с текущим счётом; повторный вызов перезапускает показ."""
        frame = overlay_image.compose(
            self._picture, count if self._settings["show_count"] else None
        )
        # Ссылку на PhotoImage нужно хранить, иначе Tk её удалит и картинка пропадёт.
        self._photo = ImageTk.PhotoImage(overlay_image.flatten_for_colorkey(frame), master=self._win)
        self._label.configure(image=self._photo)

        x, y = overlay_image.compute_position(
            self._win.winfo_screenwidth(), self._win.winfo_screenheight(),
            frame.width, frame.height,
            self._settings["anchor"], self._settings["offset_x"], self._settings["offset_y"],
        )
        self._win.geometry(f"{frame.width}x{frame.height}+{x}+{y}")
        self._set_alpha(1.0)
        hwnd = self._hwnd()
        _user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
        _user32.SetWindowPos(
            hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
        )

        self._shown_at = time.monotonic()
        if self._timer is not None:
            self._win.after_cancel(self._timer)
        self._timer = self._win.after(FRAME_MS, self._tick)

    def _tick(self) -> None:
        elapsed_ms = (time.monotonic() - self._shown_at) * 1000
        alpha = overlay_image.alpha_at(
            elapsed_ms, self._settings["duration_ms"], self._settings["fade_ms"]
        )
        if alpha is None:
            self.hide()
            return
        self._set_alpha(alpha)
        self._timer = self._win.after(FRAME_MS, self._tick)

    def hide(self) -> None:
        if self._timer is not None:
            self._win.after_cancel(self._timer)
            self._timer = None
        self._set_alpha(0.0)
        _user32.ShowWindow(self._hwnd(), SW_HIDE)

    @property
    def visible(self) -> bool:
        return self._timer is not None
