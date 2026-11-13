"""Короткие звуковые сигналы через winsound.

winsound.Beep блокирует поток на время звука, поэтому сигналы играет отдельный
поток-очередь: интерфейс и горячие клавиши не подтормаживают.
"""

from __future__ import annotations

import queue
import threading
import winsound

# Действие -> последовательность (частота в Гц, длительность в мс).
SIGNALS: dict[str, list[tuple[int, int]]] = {
    "add": [(1047, 70)],                    # короткий высокий «пик»
    "undo": [(440, 120)],                   # низкий
    "end_match": [(784, 90), (1175, 150)],  # два тона вверх
}


class Beeper:
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._queue: queue.Queue[str] = queue.Queue()
        threading.Thread(target=self._run, name="sound", daemon=True).start()

    def play(self, action: str) -> None:
        # Если сигналы копятся (быстрые нажатия), новые не добавляем.
        if self.enabled and self._queue.qsize() < 3:
            self._queue.put(action)

    def _run(self) -> None:
        while True:
            action = self._queue.get()
            for frequency, duration in SIGNALS.get(action, []):
                try:
                    winsound.Beep(frequency, duration)
                except RuntimeError:
                    break  # нет звукового устройства — молча пропускаем
