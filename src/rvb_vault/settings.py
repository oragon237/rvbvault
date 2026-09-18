from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QSettings


@dataclass(slots=True)
class AppPreferences:
    appearance: str = "System"
    clipboard_clear_seconds: int = 30
    auto_lock_minutes: int = 15
    backup_keep: int = 7
    close_to_tray: bool = True
    global_hotkey: bool = True
    windows_hello: bool = True


class SettingsStore:
    def __init__(self, settings: QSettings | None = None) -> None:
        self.qs = settings or QSettings("RVB", "RVB Vault")

    def load(self) -> AppPreferences:
        return AppPreferences(
            appearance=str(self.qs.value("appearance", "System")),
            clipboard_clear_seconds=int(self.qs.value("clipboard_clear_seconds", 30)),
            auto_lock_minutes=int(self.qs.value("auto_lock_minutes", 15)),
            backup_keep=int(self.qs.value("backup_keep", 7)),
            close_to_tray=self._bool("close_to_tray", True),
            global_hotkey=self._bool("global_hotkey", True),
            windows_hello=self._bool("windows_hello", True),
        )

    def save(self, prefs: AppPreferences) -> None:
        for key in prefs.__dataclass_fields__:
            self.qs.setValue(key, getattr(prefs, key))
        self.qs.sync()

    def _bool(self, key: str, default: bool) -> bool:
        value = self.qs.value(key, default)
        return value if isinstance(value, bool) else str(value).lower() in {"1", "true", "yes"}

    def get_bytes(self, key: str) -> bytes | None:
        value = self.qs.value(key)
        if value is None:
            return None
        if isinstance(value, bytes):
            return value
        return bytes(value)

    def set_bytes(self, key: str, value: bytes) -> None:
        self.qs.setValue(key, value)
        self.qs.sync()

    def remove(self, key: str) -> None:
        self.qs.remove(key)
        self.qs.sync()
