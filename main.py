"""Точка входа. Из неё PyInstaller собирает ChestCounter.exe.

Запуск из исходников:  python main.py
"""

import sys

from chest_counter.app import main

if __name__ == "__main__":
    sys.exit(main())
