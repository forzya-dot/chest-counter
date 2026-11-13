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

from .core import overlay_image
from .core.autostart import MINIMIZED_FLAG
from .core.config import DEFAULT_CONFIG, load_config
from .core.counter import ChestCounter
from .core.hotkeys import Hotkey, HotkeyError, parse_hotkey
from .core.paths import data_dir, resource_path
from .core.storage import Storage
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
        self._events: queue.Queue[str] = queue.Queue()

        folder = data_dir()
        self.config = load_config(folder / "config.json")
        self.storage = Storage(folder / "stats.db")
        self.counter = ChestCounter(
            self.storage, save_empty_matches=self.config["save_empty_matches"]
        )

        self.root = tk.Tk()
        self.root.report_callback_exception = self._on_tk_error
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        warnings: list[str] = []
        self._hotkeys = self._parse_hotkeys(warnings)
        self.window = MainWindow(
            self.root, self.add, self.undo, self.end_match,
            {action: hotkey.label for action, hotkey in self._hotkeys.items()},
        )
        self._stats: StatsWindow | None = None

        # Картинка: своя из config.json или встроенная в программу.
        self._picture = overlay_image.load_image(
            self.config["overlay"]["image"] or resource_path("assets/chest.png")
        )
        self._icon_photo = ImageTk.PhotoImage(_square_icon(self._picture, 64), master=self.root)
        self.root.iconphoto(True, self._icon_photo)

        # --- части, которые есть только в Windows --------------------------
        self._beeper = None
        self._overlay = None
        self._listener = None
        self._tray = None
        self._autostart = None
        if IS_WINDOWS:
            self._init_windows(warnings)

        self.refresh()
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
        return result

    def _init_windows(self, warnings: list[str]) -> None:
        from .win import autostart
        from .win.hotkeys import HotkeyListener
        from .win.overlay import Overlay
        from .win.sound import Beeper

        self._autostart = autostart
        self._beeper = Beeper(self.config["sound"]["enabled"])

        if self.config["overlay"]["enabled"]:
            try:
                self._overlay = Overlay(self.root, self.config["overlay"], self._picture)
            except Exception:
                log.exception("Не удалось создать оверлей")
                self._failed = True
                warnings.append("Не удалось создать картинку поверх экрана (подробности в app.log).")

        # Горячие клавиши: слушатель только кладёт событие в очередь.
        self._listener = HotkeyListener(self._hotkeys, self._events.put)
        for failed in self._listener.start():
            log.warning("Клавиша %s не зарегистрирована, код %s", failed.label, failed.error_code)
            reason = (
                "уже занята другой программой"
                if failed.already_taken
                else f"не зарегистрировалась (код {failed.error_code})"
            )
            warnings.append(
                f"Клавиша {failed.label} ({ACTION_NAMES[failed.action]}) {reason}. "
                "Закройте ту программу или поменяйте клавишу в config.json. "
                "Кнопки в окне работают как обычно."
            )

        try:
            from .ui.tray import Tray

            self._tray = Tray(_square_icon(self._picture, 64), self._events.put, autostart.is_enabled)
            self._tray.start()
        except Exception:
            # Без трея программа всё равно полезна: окно будет сворачиваться на панель задач.
            log.exception("Не удалось создать значок в трее")
            self._tray = None

    def run(self) -> int:
        self.root.mainloop()
        return 1 if self._failed else 0

    # --- действия счётчика ---------------------------------------------------

    def add(self) -> None:
        count = self.counter.add()
        self._beep("add")
        if self._overlay is not None:
            self._overlay.show(count)
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
            "export": self.export_csv,
            "toggle_autostart": self.toggle_autostart,
            "quit": self.quit,
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
        elif IS_WINDOWS:
            self.root.iconify()  # трея нет — хотя бы на панель задач
        else:
            self.quit()  # на Mac/Linux (разработка) трея нет, просто выходим

    def show_stats(self) -> None:
        if self._stats is None or not self._stats.alive():
            self._stats = StatsWindow(self.root, self.storage, self.export_csv)
        self._stats.refresh()
        self._stats.show()

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
        if self._listener is not None:
            self._listener.stop()  # снимает регистрацию горячих клавиш
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
            if IS_WINDOWS and self.config["overlay"]["enabled"]:
                assert self._overlay is not None and self._overlay.visible, "оверлей не показан"

        def step_end():
            self.show_stats()
            self.end_match()
            assert self.counter.current == 0, "счётчик не обнулился"
            assert self.storage.summary().matches == 1, "матч не сохранён"

        def step_quit():
            log.info("Самопроверка: %s", "ОШИБКА" if self._failed else "OK")
            self.quit()

        self.root.after(500, step_add)
        self.root.after(1200, step_end)
        self.root.after(2500, step_quit)


def _square_icon(picture: Image.Image, size: int) -> Image.Image:
    """Квадратный значок из картинки (для окна и трея)."""
    fitted = overlay_image.fit_image(picture, size)
    icon = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    icon.alpha_composite(fitted, ((size - fitted.width) // 2, (size - fitted.height) // 2))
    return icon


def _native_message(text: str, error: bool = False) -> None:
    """Сообщение без tkinter — на случай, когда главное окно создать не удалось."""
    if IS_WINDOWS:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, text, TITLE, 0x10 if error else 0x40)
    else:
        print(text, file=sys.stderr)


def _enable_dpi_awareness() -> None:
    """Чёткий текст и настоящие пиксели на экранах с масштабом 125–200 %."""
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass  # старая Windows или режим уже задан — не страшно


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ChestCounter")
    parser.add_argument(MINIMIZED_FLAG, action="store_true", help="запуститься сразу в трей")
    parser.add_argument("--self-test", action="store_true", help="самопроверка для сборки")
    # parse_known_args: лишние аргументы не должны ронять программу без консоли.
    args, _unknown = parser.parse_known_args(argv)

    # Консоли у программы нет, поэтому ошибки пишем в файл рядом с данными.
    handler = RotatingFileHandler(
        data_dir() / "app.log", maxBytes=200_000, backupCount=1, encoding="utf-8"
    )
    logging.basicConfig(
        level=logging.INFO, handlers=[handler], format="%(asctime)s %(levelname)s %(message)s"
    )

    try:
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
                f"Программа не смогла запуститься:\n{error}\n\nПодробности: {data_dir() / 'app.log'}",
                error=True,
            )
        return 1
