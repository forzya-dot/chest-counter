"""Код, который работает только в Windows (WinAPI через ctypes, winsound, реестр).

Эти модули нельзя импортировать на Mac/Linux — app.py подключает их только
при sys.platform == "win32".
"""
