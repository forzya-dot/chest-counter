"""Глобальные горячие клавиши через WinAPI RegisterHotKey.

Это штатный механизм Windows: система сама присылает нам сообщение WM_HOTKEY,
когда нажата зарегистрированная комбинация. Никаких клавиатурных хуков,
инъекций и обращения к другим процессам здесь нет.

RegisterHotKey привязывает клавиши к потоку, который их зарегистрировал,
и сообщения приходят в очередь этого же потока. Поэтому регистрация и цикл
сообщений живут в одном отдельном потоке.
"""

from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes
from dataclasses import dataclass
from typing import Callable

from ..core.hotkeys import Hotkey
from ._dll import system_dll

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
MOD_NOREPEAT = 0x4000  # удержание клавиши не даёт повторных срабатываний
ERROR_HOTKEY_ALREADY_REGISTERED = 1409

_user32 = system_dll("user32")
_kernel32 = system_dll("kernel32")

_user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
_user32.RegisterHotKey.restype = wintypes.BOOL
_user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.UnregisterHotKey.restype = wintypes.BOOL
_user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
_user32.GetMessageW.restype = ctypes.c_int  # -1 при ошибке, 0 при WM_QUIT
_user32.PeekMessageW.argtypes = [
    ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT,
]
_user32.PeekMessageW.restype = wintypes.BOOL
_user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
_user32.PostThreadMessageW.restype = wintypes.BOOL
_kernel32.GetCurrentThreadId.argtypes = []
_kernel32.GetCurrentThreadId.restype = wintypes.DWORD


@dataclass(frozen=True)
class FailedHotkey:
    action: str       # "add" / "undo" / "end_match"
    label: str        # "Ctrl+F9"
    error_code: int   # код GetLastError

    @property
    def already_taken(self) -> bool:
        return self.error_code == ERROR_HOTKEY_ALREADY_REGISTERED


class HotkeyListener:
    """Регистрирует клавиши и вызывает on_action(имя_действия) при нажатии.

    on_action вызывается из служебного потока — он должен только положить
    событие в очередь, а не трогать интерфейс.
    """

    def __init__(self, bindings: dict[str, Hotkey], on_action: Callable[[str], None]):
        self._bindings = dict(bindings)
        self._on_action = on_action
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self._ready = threading.Event()
        self.failed: list[FailedHotkey] = []

    def start(self) -> list[FailedHotkey]:
        """Запускает поток и возвращает клавиши, которые зарегистрировать не удалось."""
        self._thread = threading.Thread(target=self._run, name="hotkeys", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=5)
        return list(self.failed)

    def stop(self) -> None:
        if self._thread is None:
            return
        if self._thread_id:
            # WM_QUIT завершает цикл GetMessageW; клавиши снимаются в finally.
            _user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        self._thread.join(timeout=2)
        self._thread = None

    def _run(self) -> None:
        msg = wintypes.MSG()
        registered: dict[int, str] = {}
        try:
            self._thread_id = _kernel32.GetCurrentThreadId()
            # Первый вызов PeekMessage создаёт очередь сообщений потока.
            _user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)

            for hotkey_id, (action, hotkey) in enumerate(self._bindings.items(), start=1):
                ok = _user32.RegisterHotKey(None, hotkey_id, hotkey.modifiers | MOD_NOREPEAT, hotkey.vk)
                if ok:
                    registered[hotkey_id] = action
                else:
                    # Чаще всего 1409: комбинацию уже заняла другая программа.
                    self.failed.append(FailedHotkey(action, hotkey.label, ctypes.get_last_error()))
        finally:
            self._ready.set()

        try:
            while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY:
                    action = registered.get(int(msg.wParam))
                    if action:
                        self._on_action(action)
        finally:
            for hotkey_id in registered:
                _user32.UnregisterHotKey(None, hotkey_id)
