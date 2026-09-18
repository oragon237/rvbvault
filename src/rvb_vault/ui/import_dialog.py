from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from rvb_vault.backup import ImportPlan
from rvb_vault.db import Category


class ImportPreviewDialog(QDialog):
    def __init__(self, plan: ImportPlan, categories: list[Category], parent=None) -> None:
        super().__init__(parent)
        self.plan = plan
        self.setWindowTitle("Import preview")
        self.resize(590, 570)
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(12)

        title = QLabel("Review collection import")
        title.setObjectName("brand")
        root.addWidget(title)
        summary = QFormLayout()
        summary.setSpacing(8)
        summary.addRow("Collection", QLabel(plan.name))
        summary.addRow("Entries", QLabel(str(len(plan.items))))
        self.target = QComboBox()
        self.target.setEditable(True)
        if not plan.is_collection:
            self.target.addItem("Use categories from file", None)
        for category in categories:
            self.target.addItem(category.name, category.name)
        if plan.default_category:
            index = self.target.findText(plan.default_category, Qt.MatchFlag.MatchFixedString)
            if index >= 0:
                self.target.setCurrentIndex(index)
            else:
                self.target.addItem(plan.default_category, plan.default_category)
                self.target.setCurrentIndex(self.target.count() - 1)
        summary.addRow("Target category", self.target)
        root.addLayout(summary)

        duplicate_row = QHBoxLayout()
        duplicate_row.addWidget(QLabel("When a title already exists"))
        self.duplicates = QComboBox()
        self.duplicates.addItem("Skip Existing", "skip")
        self.duplicates.addItem("Update Existing", "update")
        self.duplicates.addItem("Keep Both", "keep")
        duplicate_row.addWidget(self.duplicates, 1)
        root.addLayout(duplicate_row)

        controls = QHBoxLayout()
        select_all = QPushButton("Select All")
        select_all.clicked.connect(lambda: self._set_all(Qt.CheckState.Checked))
        controls.addWidget(select_all)
        deselect_all = QPushButton("Deselect All")
        deselect_all.clicked.connect(lambda: self._set_all(Qt.CheckState.Unchecked))
        controls.addWidget(deselect_all)
        controls.addStretch()
        root.addLayout(controls)

        self.entries = QListWidget()
        self.entries.setObjectName("importPreviewList")
        for index, item in enumerate(plan.items):
            suffix = f"  ·  {item.category_name}"
            if item.existing_id:
                suffix += "  ·  Possible duplicate"
            row = QListWidgetItem(f"{item.entry.title}{suffix}")
            row.setData(Qt.ItemDataRole.UserRole, index)
            row.setFlags(row.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            row.setCheckState(Qt.CheckState.Checked)
            self.entries.addItem(row)
        root.addWidget(self.entries, 1)

        note = QLabel("Nothing will be written until you choose Import Selected.")
        note.setObjectName("muted")
        root.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.import_button = buttons.addButton("Import Selected", QDialogButtonBox.ButtonRole.AcceptRole)
        self.import_button.setObjectName("primary")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _set_all(self, state: Qt.CheckState) -> None:
        for index in range(self.entries.count()):
            self.entries.item(index).setCheckState(state)

    def selected_indices(self) -> list[int]:
        return [
            int(self.entries.item(index).data(Qt.ItemDataRole.UserRole))
            for index in range(self.entries.count())
            if self.entries.item(index).checkState() == Qt.CheckState.Checked
        ]

    def target_category(self) -> str | None:
        if (
            not self.plan.is_collection
            and self.target.currentIndex() == 0
            and self.target.currentText() == "Use categories from file"
        ):
            return None
        return self.target.currentText().strip() or self.plan.default_category or None

    def duplicate_mode(self) -> str:
        return str(self.duplicates.currentData())
