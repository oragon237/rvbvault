from __future__ import annotations

import asyncio
import ctypes
import os
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal


class WindowsHelloAuthenticator:
    """Thin wrapper around Windows' own consent UI; no PIN or biometric data enters RVB Vault."""

    def __init__(self) -> None:
        self.last_error = ""

    @staticmethod
    def _run(operation):
        async def wait_for_result():
            return await operation

        return asyncio.run(wait_for_result())

    def available(self) -> bool:
        if os.name != "nt":
            self.last_error = "Windows Hello is only available on Windows"
            return False
        try:
            from winrt.windows.security.credentials.ui import (
                UserConsentVerifier,
                UserConsentVerifierAvailability,
            )

            result = self._run(UserConsentVerifier.check_availability_async())
            if result == UserConsentVerifierAvailability.AVAILABLE:
                self.last_error = ""
                return True
            self.last_error = str(result).rsplit(".", 1)[-1].replace("_", " ").title()
        except Exception as exc:
            self.last_error = f"Windows Hello unavailable: {exc}"
        return False

    def verify(self, message: str = "Unlock RVB Vault") -> bool:
        try:
            from winrt.windows.security.credentials.ui import (
                UserConsentVerificationResult,
                UserConsentVerifier,
            )

            result = self._run(UserConsentVerifier.request_verification_async(message))
            if result == UserConsentVerificationResult.VERIFIED:
                self.last_error = ""
                return True
            self.last_error = str(result).rsplit(".", 1)[-1].replace("_", " ").title()
        except Exception as exc:
            self.last_error = f"Windows Hello failed: {exc}"
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
