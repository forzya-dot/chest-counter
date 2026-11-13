"""Окно «Горячие клавиши»: проверяем обработку нажатий без настоящей клавиатуры."""

import sys
import tkinter as tk
from types import SimpleNamespace

import pytest

from chest_counter.core.hotkeys import parse_hotkey
from chest_counter.ui import hotkeys_window
from chest_counter.ui.hotkeys_window import HotkeysWindow


class FakeApp:
    """Заменяет App: запоминает вызовы и хранит клавиши."""

    def __init__(self):
        self.bindings = {
            "add": parse_hotkey("F9"),
            "undo": parse_hotkey("Ctrl+F9"),
            "end_match": parse_hotkey("F10"),
        }
        self.suspended = False
        self.error = None      # что вернуть из change()
        self.modifiers = (False, False, False)

    def change(self, action, hotkey):
        if self.error:
            return self.error
        self.bindings[action] = hotkey
        self.suspended = False  # настоящий App при успехе сам включает клавиши
        return None

    def suspend(self):
        self.suspended = True

    def resume(self):
        self.suspended = False


@pytest.fixture
def setup(monkeypatch):
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("нет графического экрана")
    root.withdraw()
    # Проверяем Windows-ветку обработки: там код клавиши — это виртуальный код.
    monkeypatch.setattr(hotkeys_window.sys, "platform", "win32")
    app = FakeApp()
    window = HotkeysWindow(
        root, lambda: app.bindings, app.change, lambda: None, app.suspend, app.resume,
        modifiers_down=lambda: app.modifiers,
    )
    yield app, window
    root.destroy()


def press(window, vk):
    return window._on_key(SimpleNamespace(keycode=vk, keysym="", state=0))


def test_key_outside_capture_is_ignored(setup):
    app, window = setup
    assert press(window, 0x75) is None
    assert app.bindings["add"].label == "F9"


def test_capture_assigns_pressed_combination(setup):
    app, window = setup
    window.start_capture("add")
    assert app.suspended  # глобальные клавиши отключены, пока ждём нажатия

    app.modifiers = (True, False, False)
    assert press(window, 0x11) == "break"      # сам Ctrl — ждём дальше
    assert window._capturing == "add"
    assert press(window, 0x75) == "break"      # F6 при зажатом Ctrl

    assert app.bindings["add"].label == "Ctrl+F6"
    assert window._capturing is None
    assert not app.suspended
    assert window._labels["add"].cget("text") == "Ctrl+F6"


def test_escape_cancels_and_restores_hotkeys(setup):
    app, window = setup
    window.start_capture("undo")
    press(window, 0x1B)
    assert window._capturing is None
    assert not app.suspended
    assert app.bindings["undo"].label == "Ctrl+F9"


def test_unsupported_key_keeps_waiting(setup):
    app, window = setup
    window.start_capture("add")
    press(window, 0xFF)
    assert window._capturing == "add"
    assert app.suspended


def test_rejected_key_shows_error_and_restores_hotkeys(setup):
    app, window = setup
    app.error = "Клавиша занята"
    window.start_capture("end_match")
    press(window, 0x76)
    assert app.bindings["end_match"].label == "F10"
    assert not app.suspended
    assert window._message.cget("text") == "Клавиша занята"
    assert window._labels["end_match"].cget("text") == "F10"


def test_closing_window_during_capture_restores_hotkeys(setup):
    app, window = setup
    window.start_capture("add")
    window.close()
    assert not app.suspended
    assert not window.alive()


def test_module_uses_real_platform_by_default():
    assert hotkeys_window.sys is sys
