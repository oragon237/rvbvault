from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from rvb_vault.clipboard import ClipboardService, prompt_template_values
from rvb_vault.db import VaultDatabase
from rvb_vault.ui.icons import icon
from rvb_vault.ui.widgets import ENTRY_FAVORITE_ROLE, ENTRY_META_ROLE, ENTRY_TITLE_ROLE, EntryListDelegate


class QuickSearchDialog(QDialog):
    entry_requested = Signal(int)

    def __init__(self, db: VaultDatabase, clipboard: ClipboardService, parent=None) -> None:
        super().__init__(parent)
        self.db = db
        self.clipboard = clipboard
        self.setWindowTitle("Quick Search — RVB Vault")
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(680, 440)
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        card = QVBoxLayout()
        card.setContentsMargins(16, 16, 16, 12)
        container = QWidget()
        container.setObjectName("rootCard")
        container.setLayout(card)
        root.addWidget(container)
        self.search = QLineEdit()
        self.search.setObjectName("searchInput")
        self.search.setPlaceholderText("Search prompts, commands, tags, notes…")
        self.search.setClearButtonEnabled(True)
        self.search.addAction(icon("search"), QLineEdit.ActionPosition.LeadingPosition)
        self.search.textChanged.connect(self.refresh)
        self.search.returnPressed.connect(self.copy_selected)
        card.addWidget(self.search)
        self.results = QListWidget()
        self.results.setMouseTracking(True)
        self.results.setItemDelegate(EntryListDelegate(self.results))
        self.results.itemDoubleClicked.connect(lambda _: self.copy_selected())
        card.addWidget(self.results, 1)
        footer = QHBoxLayout()
        hint = QLabel("Enter copy primary field   ·   Ctrl+Enter open entry   ·   Esc close")
        hint.setObjectName("muted")
        footer.addWidget(hint)
        card.addLayout(footer)

    def show_search(self) -> None:
        self.refresh()
        screen = self.screen().availableGeometry()
        self.move(screen.center().x() - self.width() // 2, screen.top() + max(80, screen.height() // 6))
        self.show()
        self.raise_()
        self.activateWindow()
        self.search.selectAll()
        self.search.setFocus()

    def refresh(self) -> None:
        current_id = self.results.currentItem().data(Qt.ItemDataRole.UserRole) if self.results.currentItem() else None
        self.results.clear()
        entries = self.db.list_entries(query=self.search.text(), limit=80)
        for entry in entries:
            item = QListWidgetItem(entry.title)
            item.setData(Qt.ItemDataRole.UserRole, entry.id)
            item.setData(ENTRY_TITLE_ROLE, entry.title)
            item.setData(ENTRY_META_ROLE, entry.tags or "Recently updated")
            item.setData(ENTRY_FAVORITE_ROLE, entry.favorite)
            self.results.addItem(item)
            if entry.id == current_id:
                self.results.setCurrentItem(item)
        if self.results.count() and self.results.currentRow() < 0:
            self.results.setCurrentRow(0)

    def copy_selected(self) -> None:
        item = self.results.currentItem()
        if not item:
            return
        entry = self.db.get_entry(int(item.data(Qt.ItemDataRole.UserRole)))
        if not entry:
            return
        field = next((f for f in entry.fields if f.value), None)
        text = field.value if field else entry.notes
        resolved = prompt_template_values(self, text)
        if resolved is None:
            return
        self.clipboard.copy(resolved, sensitive=bool(field and field.is_secret))
        self.db.record_use(entry.id)
        self.hide()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            return
        if event.key() == Qt.Key.Key_Return and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            item = self.results.currentItem()
            if item:
                self.entry_requested.emit(int(item.data(Qt.ItemDataRole.UserRole)))
                self.hide()
            return
        super().keyPressEvent(event)
