from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from rvb_vault import __version__
from rvb_vault.security import verify_password
from rvb_vault.settings import AppPreferences


class SettingsDialog(QDialog):
    def __init__(self, prefs: AppPreferences, has_password: bool, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(430)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        form = QFormLayout()
        form.setSpacing(11)
        self.appearance = QComboBox()
        self.appearance.addItems(["System", "Light", "Dark"])
        self.appearance.setCurrentText(prefs.appearance)
        form.addRow("Appearance", self.appearance)

        self.clipboard = QComboBox()
        self.clipboard.addItem("Never", 0)
        for seconds in (15, 30, 60, 120):
            self.clipboard.addItem(f"After {seconds} seconds", seconds)
        index = self.clipboard.findData(prefs.clipboard_clear_seconds)
        self.clipboard.setCurrentIndex(max(index, 0))
        form.addRow("Clear secret clipboard", self.clipboard)

        self.auto_lock = QComboBox()
        for label, minutes in [("After 5 minutes", 5), ("After 15 minutes", 15), ("After 30 minutes", 30), ("After 1 hour", 60), ("Never", 0)]:
            self.auto_lock.addItem(label, minutes)
        index = self.auto_lock.findData(prefs.auto_lock_minutes)
        self.auto_lock.setCurrentIndex(max(index, 0))
        form.addRow("Auto-lock", self.auto_lock)

        self.keep = QSpinBox()
        self.keep.setRange(1, 30)
        self.keep.setValue(prefs.backup_keep)
        self.keep.setSuffix(" backups")
        form.addRow("Rolling backups", self.keep)

        self.close_to_tray = QCheckBox("Keep RVB Vault available in the system tray")
        self.close_to_tray.setChecked(prefs.close_to_tray)
        form.addRow("When closing", self.close_to_tray)
        self.global_hotkey = QCheckBox("Use Ctrl+Shift+Space outside the app")
        self.global_hotkey.setChecked(prefs.global_hotkey)
        form.addRow("Quick search", self.global_hotkey)
        self.windows_hello = QCheckBox("Use Windows Hello / Windows Security to unlock")
        self.windows_hello.setChecked(prefs.windows_hello)
        form.addRow("Vault protection", self.windows_hello)
        root.addLayout(form)

        security = QLabel("Vault lock")
        security.setObjectName("sectionTitle")
        root.addWidget(security)
        note = QLabel("Windows Hello is preferred. A master password is kept only as a fallback when Hello is unavailable.")
        note.setWordWrap(True)
        note.setObjectName("muted")
        root.addWidget(note)
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setPlaceholderText("Leave blank to keep current setting")
        root.addWidget(self.password)
        self.confirm = QLineEdit()
        self.confirm.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm.setPlaceholderText("Confirm new master password")
        root.addWidget(self.confirm)
        self.remove_password = QCheckBox("Remove the existing master password")
        self.remove_password.setVisible(has_password)
        root.addWidget(self.remove_password)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save)
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _validate(self) -> None:
        if self.password.text() and self.password.text() != self.confirm.text():
            QMessageBox.warning(self, "Passwords do not match", "Enter the same new master password twice.")
            return
        if self.password.text() and len(self.password.text()) < 6:
            QMessageBox.warning(self, "Password too short", "Use at least 6 characters.")
            return
        self.accept()

    def preferences(self) -> AppPreferences:
        return AppPreferences(
            appearance=self.appearance.currentText(),
            clipboard_clear_seconds=int(self.clipboard.currentData()),
            auto_lock_minutes=int(self.auto_lock.currentData()),
            backup_keep=self.keep.value(),
            close_to_tray=self.close_to_tray.isChecked(),
            global_hotkey=self.global_hotkey.isChecked(),
            windows_hello=self.windows_hello.isChecked(),
        )


class RecoveryPasswordDialog(QDialog):
    def __init__(self, *, confirm: bool, title: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(420)
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(10)
        heading = QLabel(title)
        heading.setObjectName("brand")
        root.addWidget(heading)
        note = QLabel(
            "This recovery password encrypts the full backup, including secrets. RVB Vault cannot recover it if lost."
            if confirm else "Enter the recovery password used when this backup was created."
        )
        note.setWordWrap(True)
        note.setObjectName("muted")
        root.addWidget(note)
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setPlaceholderText("Recovery password")
        root.addWidget(self.password)
        self.confirm = QLineEdit()
        self.confirm.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm.setPlaceholderText("Confirm recovery password")
        self.confirm.setVisible(confirm)
        root.addWidget(self.confirm)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(lambda: self._validate(confirm))
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self.password.setFocus()

    def _validate(self, confirm: bool) -> None:
        if len(self.password.text()) < 10:
            QMessageBox.warning(self, "Password too short", "Use at least 10 characters for the recovery password.")
            return
        if confirm and self.password.text() != self.confirm.text():
            QMessageBox.warning(self, "Passwords do not match", "Enter the same recovery password twice.")
            return
        self.accept()


class UnlockDialog(QDialog):
    def __init__(self, verifier: bytes, parent=None) -> None:
        super().__init__(parent)
        self.verifier = verifier
        self.setWindowTitle("Unlock RVB Vault")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)
        title = QLabel("RVB Vault is locked")
        title.setObjectName("brand")
        root.addWidget(title)
        root.addWidget(QLabel("Enter your master password to continue."))
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setPlaceholderText("Master password")
        self.password.returnPressed.connect(self._unlock)
        root.addWidget(self.password)
        self.error = QLabel("")
        self.error.setStyleSheet("color: #c43b32")
        root.addWidget(self.error)
        button = QPushButton("Unlock")
        button.setObjectName("primary")
        button.clicked.connect(self._unlock)
        root.addWidget(button)
        self.password.setFocus()

    def _unlock(self) -> None:
        if verify_password(self.password.text(), self.verifier):
            self.accept()
        else:
            self.error.setText("That password is not correct.")
            self.password.selectAll()


class AboutDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("About RVB Vault")
        self.setFixedWidth(410)
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 24, 26, 24)
        root.setSpacing(10)
        title = QLabel("RVB Vault")
        title.setObjectName("brand")
        root.addWidget(title)
        root.addWidget(QLabel(f"Version {__version__}"))
        body = QLabel(
            "A local-first productivity vault for prompts, commands, procedures, credentials, and the text you use every day."
        )
        body.setWordWrap(True)
        root.addWidget(body)
        privacy = QLabel("Your vault stays on this PC. RVB Vault has no cloud service, telemetry, or localhost server.")
        privacy.setWordWrap(True)
        privacy.setObjectName("muted")
        root.addWidget(privacy)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.clicked.connect(self.accept)
        root.addWidget(buttons)
