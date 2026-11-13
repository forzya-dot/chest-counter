"""Тесты Windows-слоя. На Mac/Linux пропускаются, в GitHub Actions выполняются.

Здесь проверяется то, что нельзя проверить без Windows: настоящая регистрация
горячих клавиш, определение занятой клавиши, стили окна оверлея, реестр.
"""

import queue
import sys
import time

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="только для Windows")

# Редкая комбинация, чтобы не пересечься с чем-нибудь на машине, где идут тесты.
TEST_HOTKEY = "Ctrl+Alt+Shift+F22"


def _listener(events=None):
    from chest_counter.core.hotkeys import parse_hotkey
    from chest_counter.win.hotkeys import HotkeyListener

    sink = events.put if events is not None else (lambda _action: None)
    return HotkeyListener({"add": parse_hotkey(TEST_HOTKEY)}, sink)


def test_hotkey_registers_and_can_be_registered_again_after_stop():
    first = _listener()
    assert first.start() == []
    first.stop()

    second = _listener()
    assert second.start() == []  # stop() действительно освободил клавишу
    second.stop()


def test_busy_hotkey_is_reported_not_raised():
    owner = _listener()
    assert owner.start() == []
    try:
        late = _listener()
        failed = late.start()
        late.stop()
        assert len(failed) == 1
        assert failed[0].action == "add"
        assert failed[0].label == TEST_HOTKEY
        assert failed[0].already_taken
    finally:
        owner.stop()


def test_wm_hotkey_message_calls_the_action():
    """Имитируем сообщение WM_HOTKEY от Windows, не нажимая клавиш."""
    from chest_counter.win import hotkeys as win_hotkeys

    events = queue.Queue()
    listener = _listener(events)
    assert listener.start() == []
    try:
        ok = win_hotkeys._user32.PostThreadMessageW(
            listener._thread_id, win_hotkeys.WM_HOTKEY, 1, 0
        )
        assert ok
        assert events.get(timeout=3) == "add"
    finally:
        listener.stop()


def test_overlay_shows_without_focus_and_hides_itself():
    import tkinter as tk

    from chest_counter.core import overlay_image
    from chest_counter.core.config import DEFAULT_CONFIG
    from chest_counter.win import overlay as win_overlay

    settings = dict(DEFAULT_CONFIG["overlay"], duration_ms=300, fade_ms=150)
    root = tk.Tk()
    try:
        overlay = win_overlay.Overlay(root, settings, overlay_image.placeholder_image())
        root.update()
        assert not overlay.visible

        overlay.show(12)
        root.update()
        assert overlay.visible
        assert overlay.on_screen()
        style = overlay.ex_style()
        for flag in (
            win_overlay.WS_EX_LAYERED,
            win_overlay.WS_EX_TRANSPARENT,
            win_overlay.WS_EX_NOACTIVATE,
            win_overlay.WS_EX_TOPMOST,
        ):
            assert style & flag, hex(flag)

        deadline = time.monotonic() + 5
        while overlay.visible and time.monotonic() < deadline:
            root.update()
            time.sleep(0.02)
        assert not overlay.visible
        assert not overlay.on_screen()
    finally:
        root.destroy()


def test_autostart_roundtrip(monkeypatch):
    from chest_counter.win import autostart

    # Отдельное имя, чтобы не трогать настоящую запись автозапуска.
    monkeypatch.setattr(autostart, "_VALUE_NAME", "ChestCounterPytest")
    try:
        assert not autostart.is_enabled()
        autostart.set_enabled(True)
        assert autostart.is_enabled()
    finally:
        autostart.set_enabled(False)
    assert not autostart.is_enabled()
    autostart.set_enabled(False)  # повторное выключение не падает


def test_single_instance():
    from chest_counter.win import single_instance

    name = "Local\\ChestCounterPytest"
    assert single_instance.acquire(name) is True
    assert single_instance.acquire(name) is False


def test_sounds_differ_per_action():
    from chest_counter.win.sound import SIGNALS, Beeper

    assert set(SIGNALS) == {"add", "undo", "end_match"}
    assert len({tuple(v) for v in SIGNALS.values()}) == 3
    Beeper(enabled=True).play("add")  # не должно падать даже без звуковой карты
