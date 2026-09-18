from __future__ import annotations

import hashlib
import re

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication, QInputDialog, QWidget


VARIABLE_RE = re.compile(r"\{\{\s*([A-Za-z_][\w.-]*)\s*\}\}")


def template_variables(text: str) -> list[str]:
    return list(dict.fromkeys(VARIABLE_RE.findall(text)))


def resolve_template(text: str, values: dict[str, str]) -> str:
    return VARIABLE_RE.sub(lambda m: values.get(m.group(1), m.group(0)), text)


def prompt_template_values(parent: QWidget, text: str) -> str | None:
    values: dict[str, str] = {}
    for name in template_variables(text):
        value, ok = QInputDialog.getText(parent, "Template value", f"{name}:")
        if not ok:
            return None
        values[name] = value
    return resolve_template(text, values)


class ClipboardService(QObject):
    copied = Signal(str)
    cleared = Signal()

    def __init__(self, clear_seconds: int = 30) -> None:
        super().__init__()
        self.clear_seconds = clear_seconds
        self._expected_hash: bytes | None = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._clear_if_unchanged)

    def copy(self, text: str, *, sensitive: bool = False) -> None:
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
        self.copied.emit("Secret copied" if sensitive else "Copied")
        self._timer.stop()
        self._expected_hash = None
        if sensitive and self.clear_seconds > 0:
            self._expected_hash = hashlib.sha256(text.encode("utf-8")).digest()
            self._timer.start(self.clear_seconds * 1000)

    def _clear_if_unchanged(self) -> None:
        if self._expected_hash is None:
            return
        clipboard = QApplication.clipboard()
        current = clipboard.text()
        if hashlib.sha256(current.encode("utf-8")).digest() == self._expected_hash:
            clipboard.clear()
            self.cleared.emit()
        self._expected_hash = None

    def clear_sensitive(self) -> None:
        """Clear only clipboard content that RVB Vault marked as sensitive."""
        self._timer.stop()
        if self._expected_hash is not None:
            clipboard = QApplication.clipboard()
            current = clipboard.text()
            if hashlib.sha256(current.encode("utf-8")).digest() == self._expected_hash:
                clipboard.clear()
                self.cleared.emit()
        self._expected_hash = None
