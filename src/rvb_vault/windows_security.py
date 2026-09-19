from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal


class WindowsHelloAuthenticator:
    """Fail-closed capability check until supported desktop interop is available."""

    def __init__(self) -> None:
        self.last_error = ""

    def available(self) -> bool:
        # A device-level availability check is not proof that an unpackaged Qt
        # desktop process can display a supported, window-owned consent prompt.
        # The UWP RequestVerificationAsync API must not be used as an unlock gate.
        self.last_error = "Windows Hello desktop unlock is not supported in this build"
        return False


WM_WTSSESSION_CHANGE = 0x02B1
WM_POWERBROADCAST = 0x0218
WTS_SESSION_LOCK = 0x7
WTS_SESSION_UNLOCK = 0x8
PBT_APMSUSPEND = 0x0004
PBT_APMRESUMEAUTOMATIC = 0x0012
NOTIFY_FOR_THIS_SESSION = 0


class WindowsSessionMonitor(QObject, QAbstractNativeEventFilter):
    lock_requested = Signal()
    resumed = Signal()

    def __init__(self) -> None:
        QObject.__init__(self)
        QAbstractNativeEventFilter.__init__(self)
        self._hwnd = 0

    def register(self, hwnd: int) -> bool:
        if os.name != "nt":
            return False
        self._hwnd = hwnd
        register = ctypes.windll.wtsapi32.WTSRegisterSessionNotification
        register.argtypes = [wintypes.HWND, wintypes.DWORD]
        register.restype = wintypes.BOOL
        return bool(register(wintypes.HWND(hwnd), NOTIFY_FOR_THIS_SESSION))

    def unregister(self) -> None:
        if self._hwnd and os.name == "nt":
            unregister = ctypes.windll.wtsapi32.WTSUnRegisterSessionNotification
            unregister.argtypes = [wintypes.HWND]
            unregister.restype = wintypes.BOOL
            unregister(wintypes.HWND(self._hwnd))
        self._hwnd = 0

    def nativeEventFilter(self, event_type, message):  # noqa: N802 - Qt API
        if os.name != "nt" or event_type not in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            return False, 0
        msg = wintypes.MSG.from_address(int(message))
        if msg.message == WM_WTSSESSION_CHANGE:
            if msg.wParam == WTS_SESSION_LOCK:
                self.lock_requested.emit()
            elif msg.wParam == WTS_SESSION_UNLOCK:
                self.resumed.emit()
        elif msg.message == WM_POWERBROADCAST:
            if msg.wParam == PBT_APMSUSPEND:
                self.lock_requested.emit()
            elif msg.wParam == PBT_APMRESUMEAUTOMATIC:
                self.resumed.emit()
        return False, 0
