from __future__ import annotations

import os
import sys
import traceback
import ctypes
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QTimer, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMenu, QStyle, QSystemTrayIcon

from rvb_vault import __version__
from rvb_vault.backup import BackupManager
from rvb_vault.clipboard import ClipboardService
from rvb_vault.db import VaultDatabase
from rvb_vault.hotkey import GlobalHotkeyFilter
from rvb_vault.paths import backups_dir, database_path, data_dir, key_path
from rvb_vault.security import LocalCipher
from rvb_vault.settings import SettingsStore
from rvb_vault.ui.dialogs import UnlockDialog
from rvb_vault.ui.main_window import MainWindow
from rvb_vault.ui.quick_search import QuickSearchDialog
from rvb_vault.ui.theme import apply_theme, enable_windows_blur
from rvb_vault.windows_security import WindowsHelloAuthenticator, WindowsSessionMonitor


def resource_path(relative: str) -> Path:
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return bundle_root / relative


def app_icon() -> QIcon:
    return QIcon(str(resource_path("assets/rvb_vault.ico")))


class AppController(QObject):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.settings = SettingsStore()
        self.prefs = self.settings.load()
        self.cipher = LocalCipher(key_path())
        self.db = VaultDatabase(database_path(), self.cipher)
        self.backup = BackupManager(self.db, self.cipher, backups_dir())
        self.clipboard = ClipboardService(self.prefs.clipboard_clear_seconds)
        self.window = MainWindow(self.db, self.clipboard, self.backup, self.settings)
        self.quick = QuickSearchDialog(self.db, self.clipboard, self.window)
        self.quick.entry_requested.connect(self.window.open_entry)
        self.window.settings_changed.connect(self.settings_changed)
        self.window.lock_requested.connect(self.lock)
        self.hotkey = GlobalHotkeyFilter()
        self.hotkey.activated.connect(self.show_quick_search)
        self.app.installNativeEventFilter(self.hotkey)
        self.hello = WindowsHelloAuthenticator()
        self.session_monitor = WindowsSessionMonitor()
        self.session_monitor.lock_requested.connect(self.lock)
        self.session_monitor.resumed.connect(self._session_resumed)
        self.app.installNativeEventFilter(self.session_monitor)
        self.session_monitor.register(int(self.window.winId()))
        self._setup_tray()
        self._setup_inactivity()
        self.apply_preferences()
        QTimer.singleShot(300, self._automatic_backup)

    def _setup_tray(self) -> None:
        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip("RVB Vault")
        menu = QMenu()
        show = menu.addAction("Open RVB Vault")
        quick = menu.addAction("Quick Search")
        lock = menu.addAction("Lock")
        menu.addSeparator()
        quit_action = menu.addAction("Quit")
        show.triggered.connect(self.show_window)
        quick.triggered.connect(self.show_quick_search)
        lock.triggered.connect(self.lock)
        quit_action.triggered.connect(self.quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda reason: self.show_window() if reason == QSystemTrayIcon.ActivationReason.DoubleClick else None
        )
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()

    def _setup_inactivity(self) -> None:
        self.locked = False
        self.remaining_seconds = 0
        self.app.installEventFilter(self)
        self.inactivity = QTimer(self)
        self.inactivity.setInterval(1000)
        self.inactivity.timeout.connect(self._inactivity_tick)
        self.reset_inactivity()
        self.inactivity.start()

    def eventFilter(self, watched, event):  # noqa: N802
        if event.type() in {
            QEvent.Type.MouseButtonPress, QEvent.Type.MouseMove, QEvent.Type.KeyPress,
            QEvent.Type.Wheel, QEvent.Type.TouchBegin,
        }:
            self.reset_inactivity()
        return super().eventFilter(watched, event)

    def reset_inactivity(self) -> None:
        self.remaining_seconds = max(0, self.prefs.auto_lock_minutes * 60)

    def _inactivity_tick(self) -> None:
        if self.locked or self.prefs.auto_lock_minutes <= 0:
            return
        self.remaining_seconds -= 1
        if self.remaining_seconds <= 0:
            self.lock()

    def apply_preferences(self) -> None:
        self.prefs = self.settings.load()
        mode = apply_theme(self.app, self.prefs.appearance)
        self.clipboard.clear_seconds = self.prefs.clipboard_clear_seconds
        enable_windows_blur(self.window, mode == "dark")
        if self.prefs.global_hotkey and not self.hotkey.registered:
            if not self.hotkey.register():
                self.window.flash_status("Global hotkey is unavailable; another app may be using it")
        elif not self.prefs.global_hotkey:
            self.hotkey.unregister()
        self.reset_inactivity()

    def settings_changed(self) -> None:
        self.apply_preferences()
        self.backup.prune(self.prefs.backup_keep)

    def _automatic_backup(self) -> None:
        try:
            existing = sorted(backups_dir().glob("*.rvbbackup"), reverse=True)
            today = __import__("datetime").date.today().strftime("%Y%m%d")
            if not existing or today not in existing[0].name:
                self.backup.create_encrypted()
            self.backup.prune(self.prefs.backup_keep)
        except Exception as exc:
            self.window.flash_status(f"Automatic backup failed: {exc}")

    def start(self) -> None:
        if self._authentication_available():
            self.locked = True
            self.unlock(close_on_cancel=True)
        else:
            self.show_window()
            if self.prefs.windows_hello:
                self.window.flash_status(self.hello.last_error or "Configure Windows Hello to protect the vault")

    def show_window(self) -> None:
        if self.locked:
            self.unlock()
            return
        self.window.show_for_user()
        self.window.raise_()
        self.window.activateWindow()

    def show_quick_search(self) -> None:
        if self.locked:
            self.unlock()
            if self.locked:
                return
        self.quick.show_search()

    def _authentication_available(self) -> bool:
        if self.prefs.windows_hello and self.hello.available():
            return True
        return bool(self.settings.get_bytes("security/password_verifier"))

    def lock(self) -> None:
        if self.locked:
            return
        if not self._authentication_available():
            self.window.flash_status("Configure Windows Hello or a fallback password in Settings")
            self.reset_inactivity()
            return
        self.locked = True
        self.window.prepare_for_lock()
        self.clipboard.clear_sensitive()
        self.quick.hide()
        self.window.hide()

    def unlock(self, *, close_on_cancel: bool = False) -> None:
        if self.prefs.windows_hello and self.hello.available():
            if self.hello.verify("Unlock RVB Vault"):
                self.locked = False
                self.reset_inactivity()
                self.window.restore_after_unlock()
                self.show_window()
                return
            if close_on_cancel:
                self.quit()
            return
        verifier = self.settings.get_bytes("security/password_verifier")
        if not verifier:
            self.locked = False
            self.show_window()
            return
        dialog = UnlockDialog(verifier)
        if dialog.exec() == dialog.DialogCode.Accepted:
            self.locked = False
            self.reset_inactivity()
            self.window.restore_after_unlock()
            self.show_window()

    def _session_resumed(self) -> None:
        # The vault stays locked after session unlock/resume. The next attempt to
        # show it invokes Windows Hello again.
        if not self.locked and self._authentication_available():
            self.lock()

    def quit(self) -> None:
        self.window.persist_window_preferences()
        self.window.force_quit = True
        self.tray.hide()
        self.app.quit()

    def shutdown(self) -> None:
        self.hotkey.unregister()
        self.session_monitor.unregister()
        try:
            self.db.close()
        except Exception:
            pass


def _write_crash_log(exc_type, exc_value, exc_tb) -> None:
    try:
        log = data_dir() / "crash.log"
        log.write_text("".join(traceback.format_exception(exc_type, exc_value, exc_tb)), encoding="utf-8")
    finally:
        sys.__excepthook__(exc_type, exc_value, exc_tb)


def main() -> int:
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    if os.name == "nt":
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("RVB.RVBVault")
    app = QApplication(sys.argv)
    app.setApplicationName("RVB Vault")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("RVB")
    app.setWindowIcon(app_icon())
    app.setQuitOnLastWindowClosed(False)
    sys.excepthook = _write_crash_log
    controller = AppController(app)
    app.styleHints().colorSchemeChanged.connect(lambda _scheme: controller.apply_preferences())
    QTimer.singleShot(0, controller.start)
    code = app.exec()
    controller.shutdown()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
