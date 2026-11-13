"""Сборка программы из частей.

Главная идея: всё, что меняет данные или интерфейс, выполняется в одном
потоке — потоке tkinter. Горячие клавиши и меню трея работают в своих потоках
и только кладут название события в очередь self._events, а метод _poll
разбирает её по таймеру. Благодаря этому SQLite и tkinter не нужно защищать
блокировками.
"""

from __future__ import annotations

import argparse
import logging
import queue
import sys
import tkinter as tk
from datetime import date
from logging.handlers import RotatingFileHandler
from tkinter import filedialog, messagebox

from PIL import Image, ImageTk

from .core.autostart import MINIMIZED_FLAG
from .core.config import DEFAULT_CONFIG, load_config, save_config
from .core.counter import ChestCounter
from .core.hotkeys import Hotkey, HotkeyError, has_duplicates, parse_hotkey
from .core.paths import data_dir, resource_path
from .core.storage import Storage
from .ui.hotkeys_window import HotkeysWindow
from .ui.main_window import MainWindow
from .ui.stats_window import StatsWindow

IS_WINDOWS = sys.platform == "win32"
POLL_MS = 40  # как часто разбираем очередь событий
TITLE = "Счётчик сундуков"

log = logging.getLogger("chest_counter")

ACTION_NAMES = {"add": "+1 сундук", "undo": "отмена", "end_match": "завершить матч"}


class App:
    def __init__(self, minimized: bool = False, self_test: bool = False):
        self._self_test = self_test
        self._failed = False  # для самопроверки: была ли ошибка в обработчиках
        self._tray_hint_shown = False
        self._events: queue.Queue[str] = queue.Queue()

        folder = data_dir()
        self._config_path = folder / "config.json"
        self.config = load_config(self._config_path)
        self.storage = Storage(folder / "stats.db")
        self.counter = ChestCounter(
            self.storage, save_empty_matches=self.config["save_empty_matches"]
        )

        self.root = tk.Tk()
        self.root.report_callback_exception = self._on_tk_error
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        config_warnings: list[str] = []
        self._hotkeys = self._parse_hotkeys(config_warnings)
        self.window = MainWindow(
            self.root, self.add, self.undo, self.end_match, self.show_hotkeys,
            self._hotkey_labels(),
        )
        self._stats: StatsWindow | None = None
        self._hotkeys_window: HotkeysWindow | None = None

        icon = _load_icon(64)
        self._icon_photo = ImageTk.PhotoImage(icon, master=self.root)
        self.root.iconphoto(True, self._icon_photo)

        # --- части, которые есть только в Windows --------------------------
        self._beeper = None
        self._listener = None
        self._hotkey_failures: list = []
        self._tray = None
        self._autostart = None
        self._modifiers_down = None
        if IS_WINDOWS:
            self._init_windows(icon)

        self.refresh()
        warnings = config_warnings + self._failure_messages()
        if warnings:
            self._warn("\n".join(warnings), popup=not minimized)
        if minimized and self._tray is not None:
            self.root.withdraw()  # автозапуск: сразу в трей, без окна

        self.root.after(POLL_MS, self._poll)
        if self_test:
            self._schedule_self_test()

    # --- запуск ------------------------------------------------------------

    def _parse_hotkeys(self, warnings: list[str]) -> dict[str, Hotkey]:
        """Разбирает клавиши из конфига; при ошибке берёт клавишу по умолчанию."""
        result: dict[str, Hotkey] = {}
        for action, default in DEFAULT_CONFIG["hotkeys"].items():
            text = self.config["hotkeys"][action]
            try:
                result[action] = parse_hotkey(text)
            except HotkeyError:
                result[action] = parse_hotkey(default)
                warnings.append(
                    f"В config.json непонятная клавиша «{text}» — использую {default}."
                )
        if has_duplicates(result):
            warnings.append(
                "Одна и та же клавиша назначена на несколько действий — сработает "
                "только первое. Исправьте это в окне «Изменить клавиши»."
            )
        return result

    def _init_windows(self, icon: Image.Image) -> None:
        from .win import autostart
        from .win.keyboard import modifiers_down
        from .win.sound import Beeper

        self._modifiers_down = modifiers_down
        self._autostart = autostart
        try:
            autostart.refresh()  # .exe могли переместить после включения автозапуска
        except OSError:
            log.exception("Не удалось обновить запись автозапуска")

        self._beeper = Beeper(self.config["sound"]["enabled"])
        self._restart_listener(self._hotkeys)

        try:
            from .ui.tray import Tray

            self._tray = Tray(icon, self._events.put, autostart.is_enabled)
            self._tray.start()
        except Exception:
            # Без трея программа всё равно полезна: окно будет сворачиваться на панель задач.
            log.exception("Не удалось создать значок в трее")
            self._tray = None

    def run(self) -> int:
        self.root.mainloop()
        return 1 if self._failed else 0

    # --- горячие клавиши -------------------------------------------------------

    def _hotkey_labels(self) -> dict[str, str]:
        return {action: hotkey.label for action, hotkey in self._hotkeys.items()}

    def suspend_hotkeys(self) -> None:
        """Снимает регистрацию клавиш (пока окно настройки ждёт нажатия)."""
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def resume_hotkeys(self) -> None:
        self._restart_listener(self._hotkeys)
        self._show_hotkey_status()

    def _restart_listener(self, bindings: dict[str, Hotkey]) -> list:
        """Регистрирует клавиши заново. Возвращает те, что не зарегистрировались."""
        self.suspend_hotkeys()
        self._hotkey_failures = []
        if not IS_WINDOWS:
            return []  # на Mac/Linux глобальных клавиш нет, есть только окно
        from .win.hotkeys import HotkeyListener

        # Слушатель только кладёт событие в очередь.
        self._listener = HotkeyListener(bindings, self._events.put)
        self._hotkey_failures = self._listener.start()
        for failed in self._hotkey_failures:
            log.warning("Клавиша %s не зарегистрирована, код %s", failed.label, failed.error_code)
        return self._hotkey_failures

    @staticmethod
    def _failure_reason(failed) -> str:
        if failed.label == "F12":
            return "зарезервирована самой Windows"
        if failed.already_taken:
            return "уже занята другой программой"
        return f"не зарегистрировалась в Windows (код {failed.error_code})"

    def _failure_messages(self) -> list[str]:
        return [
            f"Клавиша {failed.label} ({ACTION_NAMES[failed.action]}) {self._failure_reason(failed)}. "
            "Закройте ту программу или нажмите «Изменить клавиши». "
            "Кнопки в окне работают как обычно."
            for failed in self._hotkey_failures
        ]

    def _show_hotkey_status(self) -> None:
        self.window.set_status("\n".join(self._failure_messages()))

    def apply_hotkeys(self, candidate: dict[str, Hotkey]) -> str | None:
        """Назначает новый набор клавиш. Возвращает текст ошибки или None.

        При любой ошибке остаются прежние клавиши.
        """
        changed = [a for a in candidate if candidate[a] != self._hotkeys.get(a)]
        if has_duplicates(candidate):
            return "Эта клавиша уже назначена на другое действие. Выберите другую."

        failures = [f for f in self._restart_listener(candidate) if f.action in changed]
        if failures:
            # Windows не отдала клавишу — возвращаем всё как было.
            self._restart_listener(self._hotkeys)
            self._show_hotkey_status()
            failed = failures[0]
            return f"Клавиша {failed.label} {self._failure_reason(failed)}. Выберите другую."

        self._hotkeys = dict(candidate)
        self.config["hotkeys"] = self._hotkey_labels()
        self.window.set_hotkey_labels(self._hotkey_labels())
        self._show_hotkey_status()
        try:
            save_config(self._config_path, self.config)
        except OSError:
            log.exception("Не удалось сохранить config.json")
            return "Клавиши изменены, но сохранить настройки на диск не удалось."
        return None

    def change_hotkey(self, action: str, hotkey: Hotkey) -> str | None:
        return self.apply_hotkeys({**self._hotkeys, action: hotkey})

    def reset_hotkeys(self) -> str | None:
        return self.apply_hotkeys(
            {action: parse_hotkey(text) for action, text in DEFAULT_CONFIG["hotkeys"].items()}
        )

    # --- действия счётчика ---------------------------------------------------

    def add(self) -> None:
        self.counter.add()
        self._beep("add")
        self.refresh()

    def undo(self) -> None:
        self.counter.undo()
        self._beep("undo")
        self.refresh()

    def end_match(self) -> None:
        self.counter.end_match()
        self._beep("end_match")
        self.refresh()

    def refresh(self) -> None:
        """Обновляет цифры в главном окне и, если открыта, статистику."""
        self.window.update(self.counter.snapshot())
        if self._stats is not None and self._stats.alive():
            self._stats.refresh()

    def _beep(self, action: str) -> None:
        if self._beeper is not None:
            self._beeper.play(action)

    # --- очередь событий -----------------------------------------------------

    def _poll(self) -> None:
        handlers = {
            "add": self.add,
            "undo": self.undo,
            "end_match": self.end_match,
            "open": self.show_window,
            "stats": self.show_stats,
            "hotkeys": self.show_hotkeys,
            "export": self.export_csv,
            "toggle_autostart": self.toggle_autostart,
        }
        while True:
            try:
                event = self._events.get_nowait()
            except queue.Empty:
                break
            if event == "quit":
                self.quit()
                return  # окно уничтожено, таймер больше не нужен
            try:
                handlers[event]()
            except Exception:
                log.exception("Ошибка при обработке события %s", event)
                self._failed = True
        self.root.after(POLL_MS, self._poll)

    # --- окна и меню трея ----------------------------------------------------

    def show_window(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _on_close(self) -> None:
        """Крестик окна: прячемся в трей, программа продолжает работать."""
        if self._tray is not None:
            self.root.withdraw()
            if not self._tray_hint_shown:
                self._tray_hint_shown = True
                self._tray.notify(
                    "Программа продолжает работать. Значок — возле часов; "
                    "чтобы закрыть совсем, выберите в его меню «Выход»."
                )
        elif IS_WINDOWS:
            self.root.iconify()  # трея нет — хотя бы на панель задач
        else:
            self.quit()  # на Mac/Linux (разработка) трея нет, просто выходим

    def show_stats(self) -> None:
        if self._stats is None or not self._stats.alive():
            self._stats = StatsWindow(self.root, self.storage, self.export_csv)
        self._stats.refresh()
        self._stats.show()

    def show_hotkeys(self) -> None:
        if self._hotkeys_window is None or not self._hotkeys_window.alive():
            self._hotkeys_window = HotkeysWindow(
                self.root,
                get_bindings=lambda: self._hotkeys,
                change=self.change_hotkey,
                reset=self.reset_hotkeys,
                suspend=self.suspend_hotkeys,
                resume=self.resume_hotkeys,
                modifiers_down=self._modifiers_down,
                # При самопроверке на вопрос «всё равно назначить?» некому ответить.
                confirm=(lambda _text: True) if self._self_test else None,
            )
        self._hotkeys_window.refresh()
        self._hotkeys_window.show()

    def export_csv(self) -> None:
        parent = self._stats.window if self._stats is not None and self._stats.alive() else self.root
        path = filedialog.asksaveasfilename(
            parent=parent,
            title="Экспорт статистики в CSV",
            defaultextension=".csv",
            filetypes=[("CSV (открывается в Excel)", "*.csv")],
            initialfile=f"sunduki_{date.today():%Y-%m-%d}.csv",
        )
        if not path:
            return
        try:
            rows = self.storage.export_csv(path)
        except OSError as error:
            messagebox.showerror(TITLE, f"Не удалось сохранить файл:\n{error}", parent=parent)
            return
        messagebox.showinfo(TITLE, f"Сохранено матчей: {rows}\n{path}", parent=parent)

    def toggle_autostart(self) -> None:
        if self._autostart is None:
            return
        try:
            self._autostart.set_enabled(not self._autostart.is_enabled())
        except OSError as error:
            self._warn(f"Не удалось изменить автозапуск: {error}", popup=True)
        if self._tray is not None:
            self._tray.refresh_menu()

    def quit(self) -> None:
        self.suspend_hotkeys()  # снимает регистрацию горячих клавиш
        if self._tray is not None:
            self._tray.stop()
        self.storage.close()
        self.root.destroy()

    # --- сообщения и ошибки --------------------------------------------------

    def _warn(self, text: str, popup: bool) -> None:
        """Показывает предупреждение: строкой в окне и всплывающим сообщением."""
        log.warning(text)
        self.window.set_status(text)
        if self._self_test:
            return  # при самопроверке окна с кнопкой «ОК» некому закрывать
        if popup:
            messagebox.showwarning(TITLE, text, parent=self.root)
        elif self._tray is not None:
            self._tray.notify(text)

    def _on_tk_error(self, exc_type, exc, tb) -> None:
        log.error("Ошибка в интерфейсе", exc_info=(exc_type, exc, tb))
        self._failed = True

    # --- самопроверка (используется в GitHub Actions) ------------------------

    def _schedule_self_test(self) -> None:
        """Прогоняет основной сценарий на собранном .exe и выходит.

        Код возврата 0 — всё отработало, 1 — где-то была ошибка (см. app.log).
        """

        def step_add():
            self.add()
            assert self.counter.current == 1, "счётчик не увеличился"

        def step_rebind():
            self.show_hotkeys()
            window = self._hotkeys_window
            # Тот же путь, что и при нажатии клавиши в окне настройки.
            window.start_capture("add")
            window.finish_capture(parse_hotkey("Ctrl+Alt+F8"))
            assert self._hotkeys["add"].label == "Ctrl+Alt+F8", "клавиша не переназначена"
            assert load_config(self._config_path)["hotkeys"]["add"] == "Ctrl+Alt+F8", "не сохранено"
            # Клавиша, уже занятая другим действием, отклоняется, прежняя остаётся.
            assert self.change_hotkey("undo", parse_hotkey("Ctrl+Alt+F8")) is not None
            assert self._hotkeys["undo"].label == "Ctrl+F9"
            # Обычная буква назначается (после подтверждения) тем же путём, что и в окне.
            window.start_capture("undo")
            window.finish_capture(parse_hotkey("K"))
            assert self._hotkeys["undo"].label == "K", "буква не назначилась"
            assert self.reset_hotkeys() is None
            assert self._hotkey_labels() == DEFAULT_CONFIG["hotkeys"], "сброс не сработал"
            if IS_WINDOWS:
                assert self._listener is not None, "клавиши не включены обратно"
            window.close()

        def step_end():
            self.show_stats()
            self.end_match()
            assert self.counter.current == 0, "счётчик не обнулился"
            assert self.storage.summary().matches == 1, "матч не сохранён"

        def step_quit():
            log.info("Самопроверка: %s", "ОШИБКА" if self._failed else "OK")
            self.quit()

        self.root.after(500, step_add)
        self.root.after(900, step_rebind)
        self.root.after(1500, step_end)
        self.root.after(2500, step_quit)


def _load_icon(size: int) -> Image.Image:
    """Квадратный значок для окна и трея из картинки, упакованной в программу."""
    icon = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    try:
        with Image.open(resource_path("assets/chest.png"), formats=("PNG",)) as image:
            picture = image.convert("RGBA")
        picture.thumbnail((size, size), Image.LANCZOS)
        icon.alpha_composite(picture, ((size - picture.width) // 2, (size - picture.height) // 2))
    except Exception:
        # Картинка не нашлась — программа должна работать и без неё.
        log.exception("Не удалось загрузить значок")
        icon.paste((245, 185, 66, 255), (size // 8, size // 8, size - size // 8, size - size // 8))
    return icon


def _native_message(text: str, error: bool = False) -> None:
    """Сообщение без tkinter — на случай, когда главное окно создать не удалось."""
    if IS_WINDOWS:
        from .win._dll import system_dll

        system_dll("user32").MessageBoxW(None, text, TITLE, 0x10 if error else 0x40)
    else:
        print(text, file=sys.stderr)


def _enable_dpi_awareness() -> None:
    """Чёткий текст на экранах с масштабом 125–200 %."""
    try:
        from .win._dll import system_dll

        system_dll("shcore").SetProcessDpiAwareness(1)
    except Exception:
        pass  # старая Windows или режим уже задан — не страшно


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ChestCounter")
    parser.add_argument(MINIMIZED_FLAG, action="store_true", help="запуститься сразу в трей")
    parser.add_argument("--self-test", action="store_true", help="самопроверка для сборки")
    # parse_known_args: лишние аргументы не должны ронять программу без консоли.
    args, _unknown = parser.parse_known_args(argv)

    try:
        # Консоли у программы нет, поэтому ошибки пишем в файл рядом с данными.
        handler = RotatingFileHandler(
            data_dir() / "app.log", maxBytes=200_000, backupCount=1, encoding="utf-8"
        )
        logging.basicConfig(
            level=logging.INFO, handlers=[handler], format="%(asctime)s %(levelname)s %(message)s"
        )
        if IS_WINDOWS:
            _enable_dpi_awareness()
            if not args.self_test:
                from .win import single_instance

                if not single_instance.acquire():
                    _native_message(
                        "Счётчик сундуков уже запущен.\nНайдите его значок в трее (возле часов)."
                    )
                    return 0
        return App(minimized=args.minimized, self_test=args.self_test).run()
    except Exception as error:
        log.exception("Программа завершилась с ошибкой")
        if not args.self_test:
            _native_message(
                f"Программа не смогла запуститься:\n{error}\n\n"
                "Подробности — в файле app.log в папке %APPDATA%\\ChestCounter.",
                error=True,
            )
        return 1
