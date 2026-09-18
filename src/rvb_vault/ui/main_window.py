from __future__ import annotations

import sqlite3
from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QSize, QTimer, Qt, Signal
from PySide6.QtGui import QAction, QColor, QCloseEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QSystemTrayIcon,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from rvb_vault.backup import BackupManager
from rvb_vault.clipboard import ClipboardService, prompt_template_values
from rvb_vault.db import Category, Entry, VaultDatabase
from rvb_vault.settings import SettingsStore
from rvb_vault.security import PASSWORD_BACKUP_MAGIC
from rvb_vault.ui.dialogs import AboutDialog, RecoveryPasswordDialog, SettingsDialog
from rvb_vault.ui.editor import EntryEditor
from rvb_vault.ui.icons import icon
from rvb_vault.ui.import_dialog import ImportPreviewDialog
from rvb_vault.ui.widgets import ENTRY_FAVORITE_ROLE, ENTRY_META_ROLE, ENTRY_TITLE_ROLE, EntryListDelegate, configure_tool_button


class MainWindow(QMainWindow):
    settings_changed = Signal()
    lock_requested = Signal()
    quit_requested = Signal()

    ALL, FAVORITES, RECENT = -1, -2, -3

    def __init__(
        self,
        db: VaultDatabase,
        clipboard: ClipboardService,
        backup: BackupManager,
        settings: SettingsStore,
    ) -> None:
        super().__init__()
        self.db = db
        self.clipboard = clipboard
        self.backup = backup
        self.settings_store = settings
        self.force_quit = False
        self._compact_layout = False
        self._locked_entry_id: int | None = None
        self.categories: list[Category] = []
        self.setWindowTitle("RVB Vault")
        self.resize(1240, 780)
        self.setMinimumSize(920, 600)
        self._toast_generation = 0
        self._initial_show_done = False
        self._start_maximized = True
        self._build_ui()
        self._restore_window_preferences()
        self._connect()
        self._shortcuts()
        self.reload_categories()
        self.refresh_entries()

    def _build_ui(self) -> None:
        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(8, 8, 8, 8)
        card = QWidget()
        card.setObjectName("rootCard")
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 5)
        shadow.setColor(QColor(0, 0, 0, 42))
        card.setGraphicsEffect(shadow)
        outer.addWidget(card)
        self.setCentralWidget(central)
        layout = QHBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(1)
        self.splitter.setChildrenCollapsible(False)
        layout.addWidget(self.splitter)

        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setMinimumWidth(178)
        sidebar.setMaximumWidth(255)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(13, 15, 11, 11)
        side.setSpacing(7)
        head = QHBoxLayout()
        brand_icon = QLabel()
        brand_icon.setPixmap(QApplication.windowIcon().pixmap(25, 25))
        brand_icon.setFixedSize(27, 27)
        head.addWidget(brand_icon)
        brand = QLabel("RVB Vault")
        brand.setObjectName("brand")
        head.addWidget(brand)
        head.addStretch()
        menu_button = QToolButton()
        configure_tool_button(menu_button, "more", "Vault menu")
        menu_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(menu_button)
        self.settings_action = menu.addAction(icon("edit"), "Settings")
        self.backup_action = menu.addAction(icon("save"), "Encrypted full backup…")
        self.restore_action = menu.addAction(icon("clock"), "Restore encrypted backup")
        menu.addSeparator()
        self.export_action = menu.addAction("Safe export…")
        self.export_collection_action = menu.addAction("Export selected category as collection…")
        self.import_action = menu.addAction("Import collection or export…")
        menu.addSeparator()
        self.lock_action = menu.addAction(icon("lock"), "Lock vault")
        self.about_action = menu.addAction("About")
        menu_button.setMenu(menu)
        head.addWidget(menu_button)
        side.addLayout(head)

        self.nav = QListWidget()
        self.nav.setObjectName("navigation")
        self.nav.setMouseTracking(True)
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.nav.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.nav.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.nav.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        side.addWidget(self.nav, 1)
        add_category = QPushButton("New category")
        add_category.setIcon(icon("plus"))
        add_category.setToolTip("Create a category")
        add_category.clicked.connect(self.add_category)
        side.addWidget(add_category)
        self.splitter.addWidget(sidebar)

        middle = QWidget()
        middle.setObjectName("resultPanel")
        middle.setMinimumWidth(275)
        middle.setMaximumWidth(470)
        mid = QVBoxLayout(middle)
        mid.setContentsMargins(13, 14, 13, 11)
        mid.setSpacing(8)
        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setObjectName("searchInput")
        self.search.setPlaceholderText("Search entries…")
        self.search.setClearButtonEnabled(True)
        self.search.addAction(icon("search"), QLineEdit.ActionPosition.LeadingPosition)
        top.addWidget(self.search, 1)
        new = QPushButton("New")
        new.setObjectName("primary")
        new.setIcon(icon("plus", "#8b929b"))
        new.setToolTip("New entry (Ctrl+N)")
        new.clicked.connect(self.new_entry)
        top.addWidget(new)
        mid.addLayout(top)
        self.result_label = QLabel("Entries")
        self.result_label.setObjectName("sectionTitle")
        mid.addWidget(self.result_label)
        self.results = QListWidget()
        self.results.setMouseTracking(True)
        self.results.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.results.setItemDelegate(EntryListDelegate(self.results))
        self.results.setSpacing(1)
        self.results.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        mid.addWidget(self.results, 1)
        self.splitter.addWidget(middle)

        detail = QWidget()
        detail.setObjectName("detailPanel")
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        self.editor = EntryEditor()
        detail_layout.addWidget(self.editor)
        self.splitter.addWidget(detail)
        self.splitter.setSizes([205, 340, 695])
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setStretchFactor(2, 1)

        self.toast = QLabel("", central)
        self.toast.setObjectName("toast")
        self.toast.hide()

    def _connect(self) -> None:
        self.search.textChanged.connect(self.refresh_entries)
        self.nav.currentItemChanged.connect(lambda *_: self.refresh_entries())
        self.nav.customContextMenuRequested.connect(self.category_menu)
        self.nav.model().rowsMoved.connect(lambda *_: QTimer.singleShot(0, self.save_category_order))
        self.results.currentItemChanged.connect(self.load_selected)
        self.results.itemDoubleClicked.connect(lambda _: self.copy_primary())
        self.results.customContextMenuRequested.connect(self.entry_menu)
        self.editor.save_requested.connect(self.save_entry)
        self.editor.delete_requested.connect(self.delete_entry)
        self.editor.duplicate_requested.connect(self.duplicate_entry)
        self.editor.favorite_toggled.connect(self.set_favorite)
        self.editor.copy_requested.connect(self.copy_text)
        self.clipboard.copied.connect(self.flash_status)
        self.clipboard.cleared.connect(lambda: self.flash_status("Secret removed from clipboard"))
        self.settings_action.triggered.connect(self.open_settings)
        self.backup_action.triggered.connect(self.create_backup)
        self.restore_action.triggered.connect(self.restore_backup)
        self.export_action.triggered.connect(self.export_json)
        self.export_collection_action.triggered.connect(self.export_collection)
        self.import_action.triggered.connect(self.import_json)
        self.about_action.triggered.connect(lambda: AboutDialog(self).exec())
        self.lock_action.triggered.connect(self.lock_requested)

    def _shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self.new_entry)
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self.editor._save)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self.search.setFocus)
        QShortcut(QKeySequence("/"), self, activated=self.search.setFocus)
        QShortcut(QKeySequence("Ctrl+D"), self, activated=self._duplicate_selected)
        QShortcut(QKeySequence("Ctrl+L"), self, activated=self.lock_requested)

    def reload_categories(self, selected: int | None = None) -> None:
        current = selected
        if current is None and self.nav.currentItem():
            current = self.nav.currentItem().data(Qt.ItemDataRole.UserRole)
        self.categories = self.db.list_categories()
        self.nav.blockSignals(True)
        self.nav.clear()
        for label, value in [("All Entries", self.ALL), ("Favorites", self.FAVORITES), ("Recently Used", self.RECENT)]:
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, value)
            item.setIcon(icon({self.ALL: "grid", self.FAVORITES: "star", self.RECENT: "clock"}[value]))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsDragEnabled)
            self.nav.addItem(item)
        for category in self.categories:
            item = QListWidgetItem(category.name)
            item.setData(Qt.ItemDataRole.UserRole, category.id)
            item.setIcon(icon("folder"))
            self.nav.addItem(item)
            if category.id == current:
                self.nav.setCurrentItem(item)
        if self.nav.currentRow() < 0:
            self.nav.setCurrentRow(0)
        self.nav.blockSignals(False)
        self.editor.set_categories(self.categories)

    def refresh_entries(self) -> None:
        selected_id = self.results.currentItem().data(Qt.ItemDataRole.UserRole) if self.results.currentItem() else None
        nav_value = self.nav.currentItem().data(Qt.ItemDataRole.UserRole) if self.nav.currentItem() else self.ALL
        category_id = nav_value if isinstance(nav_value, int) and nav_value > 0 else None
        entries = self.db.list_entries(
            query=self.search.text(), category_id=category_id,
            favorites_only=nav_value == self.FAVORITES, recent_only=nav_value == self.RECENT,
        )
        self.results.blockSignals(True)
        self.results.clear()
        category_names = {c.id: c.name for c in self.categories}
        for entry in entries:
            suffix = category_names.get(entry.category_id, "")
            if entry.tags:
                suffix += f"  ·  {entry.tags}"
            item = QListWidgetItem(entry.title)
            item.setData(Qt.ItemDataRole.UserRole, entry.id)
            item.setData(ENTRY_TITLE_ROLE, entry.title)
            item.setData(ENTRY_META_ROLE, suffix)
            item.setData(ENTRY_FAVORITE_ROLE, entry.favorite)
            item.setSizeHint(QSize(100, 55))
            self.results.addItem(item)
            if entry.id == selected_id:
                self.results.setCurrentItem(item)
        self.results.blockSignals(False)
        self.result_label.setText(f"{len(entries)} ENTR{'Y' if len(entries) == 1 else 'IES'}")
        if self.results.currentItem():
            self.load_selected(self.results.currentItem())
        elif self.results.count():
            self.results.setCurrentRow(0)
            self.load_selected(self.results.currentItem())
        else:
            category_id = self.selected_category_id() or (self.categories[0].id if self.categories else 0)
            secret = any(c.id == category_id and c.name == "Passwords" for c in self.categories)
            self.editor.new_entry(category_id, secret)
            self.editor.metadata.setText("New entry — ready to edit")

    def load_selected(self, item: QListWidgetItem | None, *_args) -> None:
        if item:
            entry = self.db.get_entry(int(item.data(Qt.ItemDataRole.UserRole)))
            if entry:
                self.editor.load_entry(entry)

    def open_entry(self, entry_id: int) -> None:
        self.show_for_user()
        self.raise_()
        self.activateWindow()
        self.nav.setCurrentRow(0)
        self.search.clear()
        self.refresh_entries()
        for i in range(self.results.count()):
            if self.results.item(i).data(Qt.ItemDataRole.UserRole) == entry_id:
                self.results.setCurrentRow(i)
                break

    def selected_category_id(self) -> int | None:
        value = self.nav.currentItem().data(Qt.ItemDataRole.UserRole) if self.nav.currentItem() else None
        return int(value) if isinstance(value, int) and value > 0 else None

    def new_entry(self) -> None:
        category_id = self.selected_category_id() or (self.categories[0].id if self.categories else 0)
        secret = next((c.name == "Passwords" and c.id == category_id for c in self.categories), False)
        self.results.clearSelection()
        self.editor.new_entry(category_id, secret)

    def save_entry(self, entry: Entry) -> None:
        try:
            entry_id = self.db.save_entry(entry)
        except (ValueError, sqlite3.IntegrityError) as exc:
            QMessageBox.warning(self, "Could not save", str(exc))
            return
        self.flash_status("Saved")
        self.refresh_entries()
        self.open_entry(entry_id)

    def copy_text(self, text: str, sensitive: bool) -> None:
        resolved = prompt_template_values(self, text)
        if resolved is None:
            return
        self.clipboard.copy(resolved, sensitive=sensitive)
        if self.editor.current_entry and self.editor.current_entry.id:
            self.db.record_use(self.editor.current_entry.id)
            self.editor.current_entry.use_count += 1

    def copy_primary(self) -> None:
        if not self.editor.current_entry:
            return
        field = next((f for f in self.editor.rows if f.value()), None)
        if field:
            self.copy_text(field.value(), field.secret_box.isChecked())

    def delete_entry(self, entry_id: int) -> None:
        if QMessageBox.question(self, "Delete entry?", "This entry will be permanently removed.") != QMessageBox.StandardButton.Yes:
            return
        self.db.delete_entry(entry_id)
        self.refresh_entries()
        self.flash_status("Entry deleted")

    def duplicate_entry(self, entry_id: int) -> None:
        new_id = self.db.duplicate_entry(entry_id)
        self.refresh_entries()
        self.open_entry(new_id)
        self.flash_status("Entry duplicated")

    def _duplicate_selected(self) -> None:
        if self.editor.current_entry and self.editor.current_entry.id:
            self.duplicate_entry(self.editor.current_entry.id)

    def set_favorite(self, entry_id: int, favorite: bool) -> None:
        self.db.set_favorite(entry_id, favorite)
        self.refresh_entries()

    def add_category(self) -> None:
        name, ok = QInputDialog.getText(self, "New category", "Category name:")
        if not ok or not name.strip():
            return
        try:
            category = self.db.create_category(name)
        except (ValueError, sqlite3.IntegrityError) as exc:
            QMessageBox.warning(self, "Could not create category", str(exc))
            return
        self.reload_categories(category.id)
        self.refresh_entries()

    def category_menu(self, pos: QPoint) -> None:
        item = self.nav.itemAt(pos)
        if not item or int(item.data(Qt.ItemDataRole.UserRole)) <= 0:
            return
        category_id = int(item.data(Qt.ItemDataRole.UserRole))
        menu = QMenu(self)
        rename = menu.addAction("Rename")
        delete = menu.addAction("Delete…")
        chosen = menu.exec(self.nav.mapToGlobal(pos))
        if chosen == rename:
            name, ok = QInputDialog.getText(self, "Rename category", "Name:", text=item.text())
            if ok:
                try:
                    self.db.rename_category(category_id, name)
                    self.reload_categories(category_id)
                except (ValueError, sqlite3.IntegrityError) as exc:
                    QMessageBox.warning(self, "Could not rename", str(exc))
        elif chosen == delete:
            self.delete_category(category_id, item.text())

    def delete_category(self, category_id: int, name: str) -> None:
        count = self.db.category_entry_count(category_id)
        move_to = None
        if count:
            destinations = [c for c in self.categories if c.id != category_id]
            if not destinations:
                QMessageBox.warning(self, "Cannot delete", "Create another category before deleting this one.")
                return
            labels = [c.name for c in destinations]
            selected, ok = QInputDialog.getItem(
                self, "Move entries before deleting", f"Move {count} entr{'y' if count == 1 else 'ies'} to:", labels, 0, False
            )
            if not ok:
                return
            move_to = next(c.id for c in destinations if c.name == selected)
        if QMessageBox.question(self, "Delete category?", f'Delete “{name}”?') != QMessageBox.StandardButton.Yes:
            return
        self.db.delete_category(category_id, move_to)
        self.reload_categories()
        self.refresh_entries()

    def save_category_order(self) -> None:
        ordered = []
        for i in range(self.nav.count()):
            value = self.nav.item(i).data(Qt.ItemDataRole.UserRole)
            if isinstance(value, int) and value > 0:
                ordered.append(value)
        if ordered:
            self.db.reorder_categories(ordered)
            self.categories = self.db.list_categories()

    def entry_menu(self, pos: QPoint) -> None:
        item = self.results.itemAt(pos)
        if not item:
            return
        entry_id = int(item.data(Qt.ItemDataRole.UserRole))
        menu = QMenu(self)
        copy = menu.addAction("Copy primary field")
        duplicate = menu.addAction("Duplicate")
        delete = menu.addAction("Delete")
        chosen = menu.exec(self.results.mapToGlobal(pos))
        if chosen == copy:
            self.results.setCurrentItem(item)
            self.copy_primary()
        elif chosen == duplicate:
            self.duplicate_entry(entry_id)
        elif chosen == delete:
            self.delete_entry(entry_id)

    def open_settings(self) -> None:
        verifier = self.settings_store.get_bytes("security/password_verifier")
        dialog = SettingsDialog(self.settings_store.load(), bool(verifier), self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        self.settings_store.save(dialog.preferences())
        if dialog.remove_password.isChecked():
            self.settings_store.remove("security/password_verifier")
        elif dialog.password.text():
            from rvb_vault.security import create_password_verifier
            self.settings_store.set_bytes("security/password_verifier", create_password_verifier(dialog.password.text()))
        self.settings_changed.emit()

    def create_backup(self) -> None:
        default = str(self.backup.backup_dir / "rvb-vault-backup.rvbbackup")
        path, _ = QFileDialog.getSaveFileName(self, "Encrypted full backup", default, "RVB Backup (*.rvbbackup)")
        if not path:
            return
        password = RecoveryPasswordDialog(confirm=True, title="Create encrypted full backup", parent=self)
        if password.exec() != password.DialogCode.Accepted:
            return
        try:
            self.backup.create_password_backup(Path(path), password.password.text())
            self.flash_status("Encrypted full backup created")
        except Exception as exc:
            QMessageBox.critical(self, "Backup failed", str(exc))

    def restore_backup(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Restore encrypted backup", str(self.backup.backup_dir), "RVB Backup (*.rvbbackup)")
        if not path:
            return
        if QMessageBox.warning(
            self, "Restore backup?", "The current vault will be replaced and the app will close. A rollback copy will be kept.",
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
        ) != QMessageBox.StandardButton.Yes:
            return
        password_value = None
        try:
            password_protected = Path(path).read_bytes()[:8] == PASSWORD_BACKUP_MAGIC
        except OSError as exc:
            QMessageBox.critical(self, "Restore failed", str(exc))
            return
        if password_protected:
            password = RecoveryPasswordDialog(confirm=False, title="Unlock encrypted backup", parent=self)
            if password.exec() != password.DialogCode.Accepted:
                return
            password_value = password.password.text()
        try:
            self.backup.restore_encrypted(Path(path), password_value)
        except Exception as exc:
            QMessageBox.critical(self, "Restore failed", str(exc))
            return
        self.force_quit = True
        QApplication.quit()

    def export_json(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Safe export", "rvb-vault-safe-export.json", "JSON (*.json)")
        if path:
            try:
                self.backup.export_json(Path(path))
                self.flash_status("Safe export created — secrets redacted")
            except Exception as exc:
                QMessageBox.critical(self, "Export failed", str(exc))

    def import_json(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import collection or export", "", "RVB JSON (*.json);;JSON (*.json)")
        if not path:
            return
        try:
            plan = self.backup.load_import(Path(path))
            preview = ImportPreviewDialog(plan, self.db.list_categories(), self)
            if preview.exec() != preview.DialogCode.Accepted:
                return
            selected = preview.selected_indices()
            if not selected:
                self.flash_status("No entries selected")
                return
            result = self.backup.import_plan(
                plan,
                selected,
                duplicate_mode=preview.duplicate_mode(),
                target_category=preview.target_category(),
            )
            self.reload_categories()
            self.refresh_entries()
            detail = f"Imported {result.imported}"
            if result.updated:
                detail += f", updated {result.updated}"
            if result.skipped:
                detail += f", skipped {result.skipped}"
            self.flash_status(detail)
        except Exception as exc:
            QMessageBox.critical(self, "Import failed", str(exc))

    def export_collection(self) -> None:
        category_id = self.selected_category_id()
        category = next((item for item in self.categories if item.id == category_id), None)
        if not category:
            QMessageBox.information(self, "Choose a category", "Select a category in the sidebar before exporting a collection.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export RVB collection",
            f"{category.name}-collection.json",
            "RVB Collection (*.json)",
        )
        if not path:
            return
        try:
            self.backup.export_collection(Path(path), f"{category.name} Collection", category.id)
            self.flash_status("Collection exported — secrets redacted")
        except Exception as exc:
            QMessageBox.critical(self, "Collection export failed", str(exc))

    def prepare_for_lock(self) -> None:
        self._locked_entry_id = self.editor.current_entry.id if self.editor.current_entry else None
        self.editor.clear_sensitive_state()

    def restore_after_unlock(self) -> None:
        self.refresh_entries()
        if self._locked_entry_id:
            self.open_entry(self._locked_entry_id)
        self._locked_entry_id = None

    def flash_status(self, message: str) -> None:
        self._toast_generation += 1
        generation = self._toast_generation
        display = "Copied  ✓" if message in {"Copied", "Secret copied"} else message
        self.toast.setText(display)
        self.toast.adjustSize()
        self._position_toast()
        self.toast.show()
        self.toast.raise_()
        duration = 1600 if "copied" in message.lower() else 2400
        QTimer.singleShot(duration, lambda: self.toast.hide() if generation == self._toast_generation else None)

    def _position_toast(self) -> None:
        if not hasattr(self, "toast"):
            return
        area = self.centralWidget().rect()
        self.toast.move(area.right() - self.toast.width() - 22, area.bottom() - self.toast.height() - 20)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        compact = self.width() < 1050
        if hasattr(self, "splitter") and compact != self._compact_layout:
            self._compact_layout = compact
            available = max(840, self.width() - 16)
            self.splitter.setSizes([180, 280, max(380, available - 460)] if compact else [205, 340, max(560, available - 545)])
        self._position_toast()

    def _restore_window_preferences(self) -> None:
        geometry = self.settings_store.qs.value("window/geometry")
        if geometry:
            self.restoreGeometry(geometry)
        # Start every new app session maximized. Normal geometry is still retained
        # so Windows can restore cleanly when the user clicks the title-bar button.
        self._start_maximized = True

    def persist_window_preferences(self) -> None:
        maximized = bool(self.windowState() & Qt.WindowState.WindowMaximized)
        self.settings_store.qs.setValue("window/geometry", self.saveGeometry())
        self.settings_store.qs.setValue("window/maximized", maximized)
        self.settings_store.qs.sync()

    def show_for_user(self) -> None:
        if self.isVisible():
            self._initial_show_done = True
            state = self.windowState()
            if state & Qt.WindowState.WindowMinimized:
                self.setWindowState((state & ~Qt.WindowState.WindowMinimized) | Qt.WindowState.WindowActive)
            else:
                self.show()
            return
        if not self._initial_show_done:
            self._initial_show_done = True
            if self._start_maximized:
                self.showMaximized()
            else:
                self.show()
            return
        state = self.windowState()
        if state & Qt.WindowState.WindowMinimized:
            self.setWindowState((state & ~Qt.WindowState.WindowMinimized) | Qt.WindowState.WindowActive)
        else:
            self.show()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self.persist_window_preferences()
        if not self.force_quit and self.settings_store.load().close_to_tray and QSystemTrayIcon.isSystemTrayAvailable():
            event.ignore()
            self.hide()
            self.flash_status("RVB Vault is still available in the tray")
        else:
            event.accept()
