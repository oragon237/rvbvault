from __future__ import annotations

from copy import deepcopy

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from rvb_vault.db import GroupField, GroupSegment
from rvb_vault.ui.icons import icon
from rvb_vault.ui.widgets import configure_tool_button


def _mono_font() -> QFont:
    font = QFont("Cascadia Mono")
    font.setStyleHint(QFont.StyleHint.Monospace)
    return font


class SegmentEditorRow(QFrame):
    changed = Signal()
    move_up_requested = Signal(object)
    move_down_requested = Signal(object)
    duplicate_requested = Signal(object)
    delete_requested = Signal(object)

    def __init__(self, segment: GroupSegment, parent=None) -> None:
        super().__init__(parent)
        self.kind = segment.kind
        self.setObjectName("segmentRow")
        root = QVBoxLayout(self)
        root.setContentsMargins(11, 9, 11, 10)
        root.setSpacing(7)
        top = QHBoxLayout()
        badge = QLabel("FIXED TEXT" if self.kind == "fixed" else "EDITABLE VALUE")
        badge.setObjectName("segmentBadge")
        top.addWidget(badge)
        top.addStretch()
        for icon_name, tip, signal, danger in [
            ("up", "Move segment up", self.move_up_requested, False),
            ("down", "Move segment down", self.move_down_requested, False),
            ("duplicate", "Duplicate segment", self.duplicate_requested, False),
            ("trash", "Delete segment", self.delete_requested, True),
        ]:
            button = QToolButton()
            configure_tool_button(button, icon_name, tip, danger=danger)
            button.clicked.connect(lambda _checked=False, s=signal: s.emit(self))
            top.addWidget(button)
        root.addLayout(top)
        self.label = QLineEdit(segment.label)
        self.label.setPlaceholderText("Label shown to the user, e.g. DB User")
        self.label.setVisible(self.kind == "editable")
        self.label.textChanged.connect(self.changed)
        root.addWidget(self.label)
        self.content = QPlainTextEdit()
        self.content.setFont(_mono_font())
        self.content.setMinimumHeight(62)
        self.content.setMaximumHeight(100)
        if self.kind == "fixed":
            self.content.setPlaceholderText("Exact fixed text — spaces and line breaks are preserved")
            self.content.setPlainText(segment.text)
        else:
            self.content.setPlaceholderText("Default editable value")
            self.content.setPlainText(segment.default_value)
        self.content.textChanged.connect(self.changed)
        root.addWidget(self.content)

    def segment(self, position: int) -> GroupSegment:
        content = self.content.toPlainText()
        return GroupSegment(
            kind=self.kind,
            label=self.label.text() if self.kind == "editable" else "",
            text=content if self.kind == "fixed" else "",
            default_value=content if self.kind == "editable" else "",
            position=position,
        )


class GroupBuilderDialog(QDialog):
    def __init__(self, group: GroupField | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Group Field / Command Builder")
        self.resize(720, 680)
        self.rows: list[SegmentEditorRow] = []
        group = deepcopy(group) if group else GroupField()
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(11)
        title = QLabel("Command Builder")
        title.setObjectName("brand")
        root.addWidget(title)
        description = QLabel(
            "Combine exact fixed text with values that can be changed during normal use. Segment order is preserved."
        )
        description.setWordWrap(True)
        description.setObjectName("muted")
        root.addWidget(description)
        self.name = QLineEdit(group.name)
        self.name.setPlaceholderText("Group name, e.g. MySQL Import")
        root.addWidget(self.name)

        actions = QHBoxLayout()
        fixed = QPushButton("Fixed field")
        fixed.setIcon(icon("plus"))
        fixed.setToolTip("Add exact read-only text")
        fixed.clicked.connect(lambda: self.add_segment(GroupSegment(kind="fixed")))
        actions.addWidget(fixed)
        editable = QPushButton("Editable field")
        editable.setIcon(icon("plus"))
        editable.setToolTip("Add a value that can be changed during use")
        editable.clicked.connect(lambda: self.add_segment(GroupSegment(kind="editable")))
        actions.addWidget(editable)
        actions.addStretch()
        root.addLayout(actions)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll_body = QWidget()
        self.segment_layout = QVBoxLayout(scroll_body)
        self.segment_layout.setContentsMargins(0, 0, 0, 0)
        self.segment_layout.setSpacing(7)
        self.segment_layout.addStretch()
        scroll.setWidget(scroll_body)
        root.addWidget(scroll, 1)
        preview_label = QLabel("LIVE PREVIEW")
        preview_label.setObjectName("sectionTitle")
        root.addWidget(preview_label)
        self.preview = QPlainTextEdit()
        self.preview.setObjectName("preview")
        self.preview.setReadOnly(True)
        self.preview.setFont(_mono_font())
        self.preview.setMinimumHeight(90)
        root.addWidget(self.preview)
        for segment in group.segments:
            self.add_segment(segment)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        root.addWidget(buttons)
        self.refresh_preview()

    def add_segment(self, segment: GroupSegment) -> None:
        row = SegmentEditorRow(deepcopy(segment))
        row.changed.connect(self.refresh_preview)
        row.move_up_requested.connect(lambda item: self.move_row(item, -1))
        row.move_down_requested.connect(lambda item: self.move_row(item, 1))
        row.duplicate_requested.connect(self.duplicate_row)
        row.delete_requested.connect(self.delete_row)
        self.rows.append(row)
        self.segment_layout.insertWidget(self.segment_layout.count() - 1, row)
        self.refresh_preview()

    def move_row(self, row: SegmentEditorRow, offset: int) -> None:
        index = self.rows.index(row)
        target = index + offset
        if target < 0 or target >= len(self.rows):
            return
        self.rows.pop(index)
        self.rows.insert(target, row)
        self.segment_layout.removeWidget(row)
        self.segment_layout.insertWidget(target, row)
        self.refresh_preview()

    def duplicate_row(self, row: SegmentEditorRow) -> None:
        index = self.rows.index(row)
        duplicate = SegmentEditorRow(row.segment(index))
        duplicate.changed.connect(self.refresh_preview)
        duplicate.move_up_requested.connect(lambda item: self.move_row(item, -1))
        duplicate.move_down_requested.connect(lambda item: self.move_row(item, 1))
        duplicate.duplicate_requested.connect(self.duplicate_row)
        duplicate.delete_requested.connect(self.delete_row)
        self.rows.insert(index + 1, duplicate)
        self.segment_layout.insertWidget(index + 1, duplicate)
        self.refresh_preview()

    def delete_row(self, row: SegmentEditorRow) -> None:
        self.rows.remove(row)
        self.segment_layout.removeWidget(row)
        row.deleteLater()
        self.refresh_preview()

    def refresh_preview(self) -> None:
        self.preview.setPlainText("".join(row.segment(i).text if row.kind == "fixed" else row.segment(i).default_value for i, row in enumerate(self.rows)))

    def group_field(self) -> GroupField:
        return GroupField(
            name=self.name.text().strip() or "Command Builder",
            segments=[row.segment(i) for i, row in enumerate(self.rows)],
        )


class GroupFieldCard(QFrame):
    copy_requested = Signal(str, bool)
    remove_requested = Signal(object)
    duplicate_requested = Signal(object)

    def __init__(self, group: GroupField, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("groupCard")
        self.group = deepcopy(group)
        self.inputs: dict[int, QPlainTextEdit] = {}
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(12, 10, 12, 12)
        self.root.setSpacing(8)
        self.render()

    def render(self) -> None:
        while self.root.count():
            item = self.root.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.inputs.clear()
        header = QHBoxLayout()
        name = QLabel(self.group.name)
        name.setStyleSheet("font-weight: 620")
        header.addWidget(name)
        header.addStretch()
        edit = QToolButton()
        configure_tool_button(edit, "edit", "Edit builder structure", text="Edit")
        edit.clicked.connect(self.edit_builder)
        header.addWidget(edit)
        duplicate = QToolButton()
        configure_tool_button(duplicate, "duplicate", "Duplicate command builder")
        duplicate.clicked.connect(lambda: self.duplicate_requested.emit(self))
        header.addWidget(duplicate)
        remove = QToolButton()
        configure_tool_button(remove, "trash", "Delete command builder", danger=True)
        remove.clicked.connect(lambda: self.remove_requested.emit(self))
        header.addWidget(remove)
        self.root.addLayout(header)
        for index, segment in enumerate(self.group.segments):
            if segment.kind != "editable":
                continue
            label = QLabel(segment.label or f"Value {index + 1}")
            label.setObjectName("muted")
            self.root.addWidget(label)
            value = QPlainTextEdit(segment.default_value)
            value.setFont(_mono_font())
            value.setMinimumHeight(42)
            value.setMaximumHeight(76)
            value.textChanged.connect(self.refresh_preview)
            self.inputs[index] = value
            self.root.addWidget(value)
        preview_label = QLabel("LIVE PREVIEW")
        preview_label.setObjectName("sectionTitle")
        self.root.addWidget(preview_label)
        self.preview = QPlainTextEdit()
        self.preview.setObjectName("preview")
        self.preview.setReadOnly(True)
        self.preview.setFont(_mono_font())
        self.preview.setMinimumHeight(64)
        self.preview.setMaximumHeight(130)
        self.root.addWidget(self.preview)
        footer = QHBoxLayout()
        footer.addStretch()
        self.copy_button = QPushButton("Copy output")
        self.copy_button.setIcon(icon("copy"))
        self.copy_button.setObjectName("primary")
        self.copy_button.setToolTip("Copy assembled output without labels")
        self.copy_button.clicked.connect(self._copy)
        footer.addWidget(self.copy_button)
        self.root.addLayout(footer)
        self.refresh_preview()

    def assembled_output(self) -> str:
        values = {index: editor.toPlainText() for index, editor in self.inputs.items()}
        return self.group.assemble(values)

    def refresh_preview(self) -> None:
        self.preview.setPlainText(self.assembled_output())

    def _copy(self) -> None:
        self.copy_requested.emit(self.assembled_output(), False)
        self.copy_button.setText("Copied ✓")
        QTimer.singleShot(1500, lambda: self.copy_button.setText("Copy output"))

    def edit_builder(self) -> None:
        dialog = GroupBuilderDialog(self.group, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.group = dialog.group_field()
            self.render()

    def group_definition(self, position: int) -> GroupField:
        group = deepcopy(self.group)
        group.position = position
        group.id = None
        return group
