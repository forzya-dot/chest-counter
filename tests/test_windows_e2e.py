"""Сквозные тесты на настоящей Windows: с имитацией реальных нажатий клавиш.

Здесь запускается вся программа целиком, а клавиши «нажимаются» через
системную функцию keybd_event — Windows обрабатывает их так же, как нажатия
на клавиатуре. Так проверяется весь путь: нажатие -> окно настройки ->
регистрация новой клавиши -> срабатывание счётчика.

Если на машине нельзя имитировать нажатия (нет интерактивного рабочего стола),
тесты пропускаются, а не падают: сначала проверяется заведомо рабочая клавиша F9.
"""

import sys
import time

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="только для Windows")

VK_SHIFT, VK_CONTROL, VK_MENU, VK_ESCAPE = 0x10, 0x11, 0x12, 0x1B
VK_F7, VK_F9 = 0x76, 0x78
KEYEVENTF_KEYUP = 0x0002


def _user32():
    from ctypes import c_size_t, wintypes

    from chest_counter.win._dll import system_dll

    user32 = system_dll("user32")
    user32.keybd_event.argtypes = [wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, c_size_t]
    user32.keybd_event.restype = None
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetAncestor.restype = wintypes.HWND
    return user32


def press(*keys):
    """Нажимает клавиши по порядку и отпускает в обратном (как сочетание)."""
    user32 = _user32()
    for vk in keys:
        user32.keybd_event(vk, 0, 0, 0)
        time.sleep(0.03)
    for vk in reversed(keys):
        user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(0.03)


def pump(app, seconds, until=None):
    """Даёт программе поработать; возвращает True, как только выполнится условие."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.root.update()
        if until is not None and until():
            return True
        time.sleep(0.01)
    return until is None


def labels(app):
    return {action: hotkey.label for action, hotkey in app._hotkeys.items()}


@pytest.fixture
def make_app(tmp_path, monkeypatch):
    """Запускает программу на временной папке с данными; можно запускать повторно."""
    from tkinter import messagebox

    monkeypatch.setenv("CHESTCOUNTER_DATA_DIR", str(tmp_path))
    # Окна с кнопками «ОК» и «Да/Нет» в тесте нажимать некому.
    monkeypatch.setattr(messagebox, "showwarning", lambda *a, **k: None)
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)

    from chest_counter.app import App

    started = []

    def start():
        application = App()
        started.append(application)
        pump(application, 0.3)
        return application

    yield start
    for application in started:
        try:
            application.quit()
        except Exception:
            pass  # уже закрыта самим тестом


@pytest.fixture
def app(make_app):
    return make_app()


def require_working_key_simulation(app):
    """Проверка на заведомо рабочей клавише: F9 по умолчанию должна дать +1."""
    assert app._hotkey_failures == [], "клавиши по умолчанию не зарегистрировались"
    before = app.counter.current
    press(VK_F9)
    if not pump(app, 3, until=lambda: app.counter.current == before + 1):
        pytest.skip("на этой машине нельзя имитировать нажатия клавиш")


def test_rebound_hotkeys_count_on_real_key_presses(app):
    from chest_counter.core.hotkeys import parse_hotkey

    require_working_key_simulation(app)
    count = app.counter.current

    # Сочетание с модификаторами.
    assert app.change_hotkey("add", parse_hotkey("Ctrl+Alt+F7")) is None
    press(VK_CONTROL, VK_MENU, VK_F7)
    assert pump(app, 3, until=lambda: app.counter.current == count + 1)

    # Старая клавиша больше не считает.
    press(VK_F9)
    pump(app, 0.5)
    assert app.counter.current == count + 1

    # Обычная буква без модификаторов — то, в чём раньше программа отказывала.
    assert app.change_hotkey("add", parse_hotkey("K")) is None
    press(ord("K"))
    assert pump(app, 3, until=lambda: app.counter.current == count + 2)

    # Сброс возвращает F9.
    assert app.reset_hotkeys() is None
    press(VK_F9)
    assert pump(app, 3, until=lambda: app.counter.current == count + 3)


def test_settings_window_catches_real_key_presses(app):
    require_working_key_simulation(app)
    user32 = _user32()

    app.show_hotkeys()
    window = app._hotkeys_window
    pump(app, 0.3)

    window.start_capture("add")
    pump(app, 0.3)
    top = user32.GetAncestor(window.window.winfo_id(), 2)
    if user32.GetForegroundWindow() != top:
        pytest.skip("окно настройки не удалось вывести на передний план")

    # Одиночная клавиша.
    press(VK_F7)
    assert pump(app, 3, until=lambda: labels(app)["add"] == "F7"), window._message.cget("text")

    # Сочетание: Ctrl+Shift+U.
    window.start_capture("undo")
    pump(app, 0.2)
    press(VK_CONTROL, VK_SHIFT, ord("U"))
    assert pump(app, 3, until=lambda: labels(app)["undo"] == "Ctrl+Shift+U"), window._message.cget("text")

    # Обычная буква (на вопрос «всё равно назначить?» в тесте отвечаем «да»).
    window.start_capture("end_match")
    pump(app, 0.2)
    press(ord("M"))
    assert pump(app, 3, until=lambda: labels(app)["end_match"] == "M"), window._message.cget("text")

    # Esc отменяет выбор и ничего не меняет.
    window.start_capture("add")
    pump(app, 0.2)
    press(VK_ESCAPE)
    assert pump(app, 3, until=lambda: window._capturing is None)
    assert labels(app)["add"] == "F7"

    # Всё сохранено на диск.
    from chest_counter.core.config import load_config

    assert load_config(app._config_path)["hotkeys"] == {
        "add": "F7", "undo": "Ctrl+Shift+U", "end_match": "M",
    }

    # И только что назначенные клавиши сразу работают как глобальные.
    count = app.counter.current
    press(VK_F7)
    assert pump(app, 3, until=lambda: app.counter.current == count + 1)
    press(VK_CONTROL, VK_SHIFT, ord("U"))
    assert pump(app, 3, until=lambda: app.counter.current == count)


VK_F10, VK_F6 = 0x79, 0x75


def test_whole_match_played_with_real_keys(app):
    """Три сундука, одна отмена, конец матча — всё клавишами, как в игре."""
    require_working_key_simulation(app)   # это уже первое нажатие F9

    for expected in (2, 3):
        press(VK_F9)
        assert pump(app, 3, until=lambda: app.counter.current == expected)

    press(VK_CONTROL, VK_F9)              # отмена
    assert pump(app, 3, until=lambda: app.counter.current == 2)

    press(VK_F10)                         # конец матча
    assert pump(app, 3, until=lambda: app.counter.current == 0)
    summary = app.storage.summary()
    assert (summary.matches, summary.chests, summary.record) == (1, 2, 2)

    snapshot = app.counter.snapshot()
    assert (snapshot.current, snapshot.today, snapshot.all_time) == (0, 2, 2)

    # Отмена на нуле не уводит счёт в минус, пустой матч не записывается.
    press(VK_CONTROL, VK_F9)
    press(VK_F10)
    pump(app, 0.6)
    assert app.counter.current == 0
    assert app.storage.summary().matches == 1


def test_rebound_keys_and_count_survive_restart(make_app):
    """Закрыли программу и открыли снова: клавиши и счёт матча на месте."""
    from chest_counter.core.hotkeys import parse_hotkey

    first = make_app()
    require_working_key_simulation(first)
    assert first.change_hotkey("add", parse_hotkey("Ctrl+Shift+F6")) is None
    press(VK_CONTROL, VK_SHIFT, VK_F6)
    assert pump(first, 3, until=lambda: first.counter.current == 2)
    first.quit()

    second = make_app()
    assert second._hotkey_failures == []       # прежняя копия освободила клавиши
    assert labels(second)["add"] == "Ctrl+Shift+F6"
    assert second.counter.current == 2         # счёт матча не потерялся
    press(VK_CONTROL, VK_SHIFT, VK_F6)
    assert pump(second, 3, until=lambda: second.counter.current == 3)
    press(VK_F9)                               # старая клавиша так и не вернулась
    pump(second, 0.5)
    assert second.counter.current == 3


def test_key_taken_by_another_program_is_refused(app):
    """Клавишу держит «другая программа» — счётчик отказывает и оставляет прежнюю."""
    from chest_counter.core.hotkeys import parse_hotkey
    from chest_counter.win.hotkeys import HotkeyListener

    require_working_key_simulation(app)
    taken = parse_hotkey("Ctrl+Alt+F6")
    other_program = HotkeyListener({"x": taken}, lambda _action: None)
    assert other_program.start() == []
    try:
        error = app.change_hotkey("add", taken)
        assert error and "занята" in error
        assert labels(app)["add"] == "F9"
        assert app._hotkey_failures == []

        count = app.counter.current
        press(VK_F9)                           # прежняя клавиша продолжает работать
        assert pump(app, 3, until=lambda: app.counter.current == count + 1)
    finally:
        other_program.stop()

    # Одна клавиша на два действия — тоже отказ.
    error = app.change_hotkey("undo", parse_hotkey("F9"))
    assert error and "уже назначена" in error
    assert labels(app)["undo"] == "Ctrl+F9"
