"""Значок в трее (pystray).

pystray работает в своём потоке, а tkinter можно трогать только из главного.
Поэтому пункты меню ничего не делают сами: они лишь кладут название события
в очередь через функцию post, а обрабатывает его App в потоке tkinter.
"""

from __future__ import annotations

from typing import Callable

import pystray
from PIL import Image


class Tray:
    def __init__(
        self,
        image: Image.Image,
        post: Callable[[str], None],
        autostart_enabled: Callable[[], bool],
    ):
        def send(event: str):
            return lambda _icon, _item: post(event)

        menu = pystray.Menu(
            # default=True — действие по щелчку левой кнопкой по значку.
            pystray.MenuItem("Открыть окно", send("open"), default=True),
            pystray.MenuItem("Статистика", send("stats")),
            pystray.MenuItem("Экспорт в CSV", send("export")),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Автозапуск с Windows",
                send("toggle_autostart"),
                checked=lambda _item: autostart_enabled(),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Выход", send("quit")),
        )
        self._icon = pystray.Icon("ChestCounter", image, "Счётчик сундуков", menu)

    def start(self) -> None:
        self._icon.run_detached()

    def notify(self, message: str, title: str = "Счётчик сундуков") -> None:
        """Всплывающее уведомление Windows."""
        try:
            self._icon.notify(message, title)
        except Exception:
            pass  # уведомления могут быть отключены в системе — это не ошибка

    def refresh_menu(self) -> None:
        try:
            self._icon.update_menu()
        except Exception:
            pass

    def stop(self) -> None:
        try:
            self._icon.stop()
        except Exception:
            pass
