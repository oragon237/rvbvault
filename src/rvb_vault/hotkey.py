from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal


HOTKEY_ID = 0x5242
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
VK_SPACE = 0x20
WM_HOTKEY = 0x0312


class GlobalHotkeyFilter(QObject, QAbstractNativeEventFilter):
    activated = Signal()

    def __init__(self) -> None:
        QObject.__init__(self)
        QAbstractNativeEventFilter.__init__(self)
        self.registered = False

    def register(self) -> bool:
        if os.name != "nt":
            return False
        self.registered = bool(
            ctypes.windll.user32.RegisterHotKey(None, HOTKEY_ID, MOD_CONTROL | MOD_SHIFT, VK_SPACE)
        )
        return self.registered

    def unregister(self) -> None:
        if self.registered and os.name == "nt":
            ctypes.windll.user32.UnregisterHotKey(None, HOTKEY_ID)
        self.registered = False

    def nativeEventFilter(self, event_type, message):  # noqa: N802 - Qt API
        if os.name == "nt" and event_type in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                self.activated.emit()
                return True, 0
        return False, 0

