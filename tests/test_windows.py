"""Тесты Windows-слоя. На Mac/Linux пропускаются, в GitHub Actions выполняются.

Здесь проверяется то, что нельзя проверить без Windows: настоящая регистрация
горячих клавиш, определение занятой клавиши, реестр, загрузку системных DLL.
"""

import queue
import sys

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


def test_autostart_refresh_fixes_moved_exe(monkeypatch):
    import winreg

    from chest_counter.win import autostart

    monkeypatch.setattr(autostart, "_VALUE_NAME", "ChestCounterPytest")
    try:
        autostart.refresh()  # автозапуск выключен — ничего не делает
        assert not autostart.is_enabled()

        # Имитируем запись, оставшуюся от старого расположения программы.
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER, autostart._RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(key, "ChestCounterPytest", 0, winreg.REG_SZ, '"C:\\old\\app.exe" --minimized')
        autostart.refresh()
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, autostart._RUN_KEY) as key:
            stored, _kind = winreg.QueryValueEx(key, "ChestCounterPytest")
        assert stored == autostart._command()
    finally:
        autostart.set_enabled(False)


def test_system_dlls_are_loaded_from_system32():
    import ctypes
    import os
    from ctypes import wintypes

    from chest_counter.win._dll import system_dll

    kernel32 = system_dll("kernel32")
    kernel32.GetModuleFileNameW.argtypes = [wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD]
    system32 = os.path.join(os.environ["SystemRoot"], "System32").lower()
    for name in ("user32", "kernel32", "shcore"):
        buffer = ctypes.create_unicode_buffer(1024)
        assert kernel32.GetModuleFileNameW(system_dll(name)._handle, buffer, 1024)
        assert buffer.value.lower().startswith(system32), buffer.value


def test_modifiers_state_is_readable():
    from chest_counter.win.keyboard import modifiers_down

    state = modifiers_down()
    assert len(state) == 3 and all(isinstance(flag, bool) for flag in state)
