from __future__ import annotations

import secrets
import string
from datetime import UTC, datetime

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
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

from rvb_vault.db import Category, Entry, EntryField, GroupField, ProcedureStep
from rvb_vault.ui.group_builder import GroupBuilderDialog, GroupFieldCard
from rvb_vault.ui.icons import icon
from rvb_vault.ui.widgets import configure_tool_button


def format_local_timestamp(value: str | None) -> str:
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        local = parsed.astimezone()
        hour = local.strftime("%I").lstrip("0") or "12"
        return f"{local.strftime('%b')} {local.day}, {local.year} · {hour}:{local.strftime('%M %p')}"
    except (TypeError, ValueError):
        return value


class FieldRow(QFrame):
    copy_requested = Signal(str, bool)
    remove_requested = Signal(object)

    def __init__(self, field: EntryField | None = None, parent=None) -> None:
        super().__init__(parent)
        field = field or EntryField()
        self.setObjectName("fieldRow")
        self.secret = field.is_secret
        self.multiline = field.multiline
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 9, 10, 10)
        root.setSpacing(7)
        top = QHBoxLayout()
        self.name = QLineEdit(field.name)
        self.name.setPlaceholderText("Field name")
        self.name.setMinimumWidth(122)
        self.name.setMaximumWidth(136)
        top.addWidget(self.name)
        self.secret_box = QCheckBox("Secret")
        self.secret_box.setChecked(field.is_secret)
        self.secret_box.toggled.connect(self._secret_changed)
        top.addWidget(self.secret_box)
        self.multiline_box = QCheckBox("Multiline")
        self.multiline_box.setChecked(field.multiline)
        self.multiline_box.toggled.connect(self._multiline_changed)
        top.addWidget(self.multiline_box)
        top.addStretch()
        self.generate = QToolButton()
        configure_tool_button(self.generate, "sparkle", "Generate a strong password")
        self.generate.setVisible(field.is_secret)
        self.generate.clicked.connect(self._generate)
        top.addWidget(self.generate)
        self.reveal = QToolButton()
        configure_tool_button(self.reveal, "eye", "Reveal secret")
        self.reveal.setCheckable(True)
        self.reveal.setVisible(field.is_secret)
        self.reveal.toggled.connect(self._reveal_changed)
        top.addWidget(self.reveal)
        self.copy_button = QToolButton()
        configure_tool_button(self.copy_button, "copy", "Copy field")
        self.copy_button.clicked.connect(self._copy)
        top.addWidget(self.copy_button)
        remove = QToolButton()
        configure_tool_button(remove, "trash", "Remove field", danger=True)
        remove.clicked.connect(lambda: self.remove_requested.emit(self))
        top.addWidget(remove)
        root.addLayout(top)

        self.single = QLineEdit(field.value)
        self.single.setPlaceholderText("Value — {{variable}} is supported")
        self.multi = QPlainTextEdit(field.value)
        self.multi.setPlaceholderText("Value — templates and multiple lines are supported")
        self.multi.setMinimumHeight(94)
        mono = QFont("Cascadia Mono")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        mono.setPointSize(10)
        self.single.setFont(mono)
        self.multi.setFont(mono)
        root.addWidget(self.single)
        root.addWidget(self.multi)
        self._multiline_changed(field.multiline)
        self._secret_changed(field.is_secret)

    def _secret_changed(self, checked: bool) -> None:
        self.generate.setVisible(checked)
        self.reveal.setVisible(checked)
        if checked and self.multiline_box.isChecked():
            self.multiline_box.setChecked(False)
        self.multiline_box.setEnabled(not checked)
        self.reveal.setChecked(False)
        self.single.setEchoMode(QLineEdit.EchoMode.Password if checked else QLineEdit.EchoMode.Normal)

    def _reveal_changed(self, revealed: bool) -> None:
        self.reveal.setToolTip("Mask secret" if revealed else "Reveal secret")
        mode = QLineEdit.EchoMode.Normal if revealed or not self.secret_box.isChecked() else QLineEdit.EchoMode.Password
        self.single.setEchoMode(mode)

    def _copy(self) -> None:
        self.copy_requested.emit(self.value(), self.secret_box.isChecked())
        self.copy_button.setText("✓")
        self.copy_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        QTimer.singleShot(1500, self._reset_copy_button)

    def _reset_copy_button(self) -> None:
        self.copy_button.setText("")
        self.copy_button.setIcon(icon("copy"))
        self.copy_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)

    def _multiline_changed(self, checked: bool) -> None:
        if checked:
            if not self.single.isHidden():
                self.multi.setPlainText(self.single.text())
        else:
            if not self.multi.isHidden():
                self.single.setText(self.multi.toPlainText())
        self.single.setVisible(not checked)
        self.multi.setVisible(checked)

    def _generate(self) -> None:
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"
        value = "".join(secrets.choice(alphabet) for _ in range(24))
        if self.multiline_box.isChecked():
            self.multi.setPlainText(value)
        else:
            self.single.setText(value)

    def value(self) -> str:
        return self.multi.toPlainText() if self.multiline_box.isChecked() else self.single.text()

    def field(self, position: int) -> EntryField:
        return EntryField(
            name=self.name.text().strip() or "Value", value=self.value(), is_secret=self.secret_box.isChecked(),
            multiline=self.multiline_box.isChecked(), position=position,
        )


class ProcedureStepCard(QFrame):
    move_requested = Signal(object, int)

    def __init__(self, content: QWidget, kind: str, parent=None) -> None:
        super().__init__(parent)
        self.content = content
        self.kind = kind
        self.setObjectName("procedureStep")
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 10)
        root.setSpacing(7)
        header = QHBoxLayout()
        self.number = QLabel("STEP")
        self.number.setObjectName("sectionTitle")
        header.addWidget(self.number)
        badge = QLabel("COPYABLE FIELD" if kind == "field" else "COMMAND BUILDER")
        badge.setObjectName("segmentBadge")
        header.addWidget(badge)
        header.addStretch()
        up = QToolButton()
        configure_tool_button(up, "up", "Move step up")
        up.clicked.connect(lambda: self.move_requested.emit(self, -1))
        header.addWidget(up)
        down = QToolButton()
        configure_tool_button(down, "down", "Move step down")
        down.clicked.connect(lambda: self.move_requested.emit(self, 1))
        header.addWidget(down)
        root.addLayout(header)
        root.addWidget(content)

    def set_number(self, number: int) -> None:
        self.number.setText(f"STEP {number}")


class EntryEditor(QWidget):
    save_requested = Signal(object)
    delete_requested = Signal(int)
    duplicate_requested = Signal(int)
    copy_requested = Signal(str, bool)
    favorite_toggled = Signal(int, bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.current_entry: Entry | None = None
        self.rows: list[FieldRow] = []
        self.group_rows: list[GroupFieldCard] = []
        self.procedure_items: list[QWidget] = []
        self.step_cards: dict[QWidget, ProcedureStepCard] = {}
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(self.scroll)
        body = QWidget()
        self.scroll.setWidget(body)
        root = QVBoxLayout(body)
        root.setContentsMargins(19, 15, 19, 20)
        root.setSpacing(10)

        toolbar = QHBoxLayout()
        self.favorite = QToolButton()
        self.favorite.setCheckable(True)
        configure_tool_button(self.favorite, "star", "Add to favorites")
        self.favorite.clicked.connect(self._toggle_favorite)
        toolbar.addWidget(self.favorite)
        toolbar.addStretch()
        self.duplicate = QToolButton()
        configure_tool_button(self.duplicate, "duplicate", "Duplicate entry")
        self.duplicate.clicked.connect(self._duplicate)
        toolbar.addWidget(self.duplicate)
        self.delete = QToolButton()
        configure_tool_button(self.delete, "trash", "Delete entry", danger=True)
        self.delete.clicked.connect(self._delete)
        toolbar.addWidget(self.delete)
        root.addLayout(toolbar)

        self.title = QLineEdit()
        self.title.setObjectName("entryTitle")
        self.title.setPlaceholderText("Untitled entry")
        root.addWidget(self.title)
        meta = QHBoxLayout()
        meta.setSpacing(8)
        category_column = QVBoxLayout()
        category_column.setSpacing(4)
        category_label = QLabel("CATEGORY")
        category_label.setObjectName("sectionTitle")
        category_column.addWidget(category_label)
        self.category = QComboBox()
        category_column.addWidget(self.category)
        meta.addLayout(category_column, 1)
        kind_column = QVBoxLayout()
        kind_column.setSpacing(4)
        kind_label = QLabel("TYPE")
        kind_label.setObjectName("sectionTitle")
        kind_column.addWidget(kind_label)
        self.kind = QComboBox()
        self.kind.addItem("Standard", "standard")
        self.kind.addItem("Procedure / copy sequence", "procedure")
        self.kind.currentIndexChanged.connect(self._entry_type_changed)
        kind_column.addWidget(self.kind)
        meta.addLayout(kind_column, 1)
        root.addLayout(meta)
        tags_label = QLabel("TAGS")
        tags_label.setObjectName("sectionTitle")
        root.addWidget(tags_label)
        self.tags = QLineEdit()
        self.tags.setPlaceholderText("Tags, separated by commas")
        root.addWidget(self.tags)

        self.standard_sections = QWidget()
        standard_layout = QVBoxLayout(self.standard_sections)
        standard_layout.setContentsMargins(0, 0, 0, 0)
        standard_layout.setSpacing(8)
        heading = QHBoxLayout()
        label = QLabel("Copyable fields")
        label.setObjectName("sectionTitle")
        heading.addWidget(label)
        heading.addStretch()
        add = QPushButton("Add field")
        add.setIcon(icon("plus"))
        add.clicked.connect(lambda: self.add_field())
        heading.addWidget(add)
        standard_layout.addLayout(heading)
        self.fields_layout = QVBoxLayout()
        self.fields_layout.setSpacing(4)
        standard_layout.addLayout(self.fields_layout)

        group_heading = QHBoxLayout()
        group_label = QLabel("Command builders")
        group_label.setObjectName("sectionTitle")
        group_heading.addWidget(group_label)
        group_heading.addStretch()
        add_group = QPushButton("Command builder")
        add_group.setIcon(icon("plus"))
        add_group.clicked.connect(self.add_group_builder)
        group_heading.addWidget(add_group)
        standard_layout.addLayout(group_heading)
        self.groups_layout = QVBoxLayout()
        self.groups_layout.setSpacing(9)
        standard_layout.addLayout(self.groups_layout)
        root.addWidget(self.standard_sections)

        self.procedure_section = QWidget()
        procedure_layout = QVBoxLayout(self.procedure_section)
        procedure_layout.setContentsMargins(0, 0, 0, 0)
        procedure_layout.setSpacing(8)
        procedure_heading = QHBoxLayout()
        procedure_label = QLabel("Procedure steps")
        procedure_label.setObjectName("sectionTitle")
        procedure_heading.addWidget(procedure_label)
        procedure_heading.addStretch()
        add_step = QPushButton("Field step")
        add_step.setIcon(icon("plus"))
        add_step.clicked.connect(lambda: self.add_field())
        procedure_heading.addWidget(add_step)
        add_builder_step = QPushButton("Builder step")
        add_builder_step.setIcon(icon("plus"))
        add_builder_step.clicked.connect(self.add_group_builder)
        procedure_heading.addWidget(add_builder_step)
        procedure_layout.addLayout(procedure_heading)
        self.steps_layout = QVBoxLayout()
        self.steps_layout.setSpacing(9)
        procedure_layout.addLayout(self.steps_layout)
        root.addWidget(self.procedure_section)

        notes_label = QLabel("Notes")
        notes_label.setObjectName("sectionTitle")
        root.addWidget(notes_label)
        self.notes = QPlainTextEdit()
        self.notes.setPlaceholderText("Context, instructions, or reference notes…")
        self.notes.setMinimumHeight(110)
        root.addWidget(self.notes)
        self.metadata = QLabel("")
        self.metadata.setObjectName("faint")
        root.addWidget(self.metadata)
        buttons = QHBoxLayout()
        copy_all = QPushButton("Copy entire entry")
        copy_all.setIcon(icon("copy"))
        copy_all.clicked.connect(self._copy_entire)
        buttons.addWidget(copy_all)
        buttons.addStretch()
        save = QPushButton("Save")
        save.setObjectName("primary")
        save.setIcon(icon("save"))
        save.clicked.connect(self._save)
        buttons.addWidget(save)
        root.addLayout(buttons)
        root.addStretch()
        self.show_empty()
        self._entry_type_changed()

    def set_categories(self, categories: list[Category]) -> None:
        selected = self.category.currentData()
        self.category.clear()
        for category in categories:
            self.category.addItem(category.name, category.id)
        index = self.category.findData(selected)
        if index >= 0:
            self.category.setCurrentIndex(index)

    def show_empty(self) -> None:
        self.current_entry = None
        self.setEnabled(False)
        self.title.clear()
        self.tags.clear()
        self.notes.clear()
        self._clear_fields()
        self._clear_groups()
        self.metadata.setText("Select an entry or create a new one.")

    def new_entry(self, category_id: int | None = None, secret: bool = False) -> None:
        self.setEnabled(True)
        self.current_entry = Entry(category_id=category_id or int(self.category.itemData(0) or 0))
        self.title.clear()
        self.tags.clear()
        self.notes.clear()
        self.favorite.setChecked(False)
        self.favorite.setIcon(icon("star"))
        self.kind.setCurrentIndex(0)
        index = self.category.findData(self.current_entry.category_id)
        self.category.setCurrentIndex(max(index, 0))
        self._clear_fields()
        self._clear_groups()
        self.add_field(EntryField(name="Password" if secret else "Value", is_secret=secret, multiline=False))
        self.metadata.setText("New entry")
        self.duplicate.setEnabled(False)
        self.delete.setEnabled(False)
        self.title.setFocus()

    def load_entry(self, entry: Entry) -> None:
        self.setEnabled(True)
        self.current_entry = entry
        self.title.setText(entry.title)
        self.tags.setText(entry.tags)
        self.notes.setPlainText(entry.notes)
        self.favorite.setChecked(entry.favorite)
        self.favorite.setIcon(icon("star_filled" if entry.favorite else "star"))
        self.category.setCurrentIndex(max(self.category.findData(entry.category_id), 0))
        self.kind.blockSignals(True)
        self.kind.setCurrentIndex(max(self.kind.findData(entry.entry_type), 0))
        self.kind.blockSignals(False)
        self._clear_fields()
        self._clear_groups()
        self.procedure_items.clear()
        if entry.entry_type == "procedure":
            used_fields: set[int] = set()
            used_groups: set[int] = set()
            for step in sorted(entry.procedure_steps, key=lambda value: value.position):
                if step.kind == "field" and 0 <= step.item_index < len(entry.fields):
                    self.add_field(entry.fields[step.item_index])
                    used_fields.add(step.item_index)
                elif step.kind == "group" and 0 <= step.item_index < len(entry.group_fields):
                    self.add_group_card(entry.group_fields[step.item_index])
                    used_groups.add(step.item_index)
            for index, item in enumerate(entry.fields):
                if index not in used_fields:
                    self.add_field(item)
            for index, group in enumerate(entry.group_fields):
                if index not in used_groups:
                    self.add_group_card(group)
        else:
            for item in entry.fields:
                self.add_field(item)
            for group in entry.group_fields:
                self.add_group_card(group)
        self._entry_type_changed()
        used = f"Used {entry.use_count} time{'s' if entry.use_count != 1 else ''}"
        recent = f" · Last copied {format_local_timestamp(entry.last_used_at)}" if entry.last_used_at else ""
        self.metadata.setText(f"{used}{recent}")
        self.duplicate.setEnabled(True)
        self.delete.setEnabled(True)

    def add_field(self, field: EntryField | None = None) -> None:
        row = FieldRow(field)
        row.copy_requested.connect(self.copy_requested)
        row.remove_requested.connect(self.remove_field)
        self.rows.append(row)
        if self.kind.currentData() == "procedure":
            self._add_procedure_item(row, "field")
        else:
            self.fields_layout.addWidget(row)

    def remove_field(self, row: FieldRow) -> None:
        if row in self.rows:
            self.rows.remove(row)
            self._remove_procedure_item(row)
            row.deleteLater()

    def _clear_fields(self) -> None:
        for row in list(self.rows):
            self._remove_procedure_item(row)
            self.fields_layout.removeWidget(row)
            row.hide()
            row.deleteLater()
        self.rows.clear()

    def add_group_builder(self) -> None:
        dialog = GroupBuilderDialog(parent=self)
        if dialog.exec() == dialog.DialogCode.Accepted:
            self.add_group_card(dialog.group_field())

    def add_group_card(self, group: GroupField) -> None:
        card = GroupFieldCard(group)
        card.copy_requested.connect(self.copy_requested)
        card.remove_requested.connect(self.remove_group)
        card.duplicate_requested.connect(self.duplicate_group)
        self.group_rows.append(card)
        if self.kind.currentData() == "procedure":
            self._add_procedure_item(card, "group")
        else:
            self.groups_layout.addWidget(card)

    def remove_group(self, card: GroupFieldCard) -> None:
        if card in self.group_rows:
            self.group_rows.remove(card)
            self._remove_procedure_item(card)
            card.deleteLater()

    def duplicate_group(self, card: GroupFieldCard) -> None:
        group = card.group_definition(len(self.group_rows))
        group.name = f"{group.name} Copy"
        self.add_group_card(group)

    def _clear_groups(self) -> None:
        for card in list(self.group_rows):
            self._remove_procedure_item(card)
            self.groups_layout.removeWidget(card)
            card.hide()
            card.deleteLater()
        self.group_rows.clear()

    def _add_procedure_item(self, widget: QWidget, kind: str) -> None:
        if widget in self.procedure_items:
            return
        self.procedure_items.append(widget)
        card = ProcedureStepCard(widget, kind)
        card.move_requested.connect(self._move_step)
        self.step_cards[widget] = card
        self.steps_layout.addWidget(card)
        self._renumber_steps()

    def _remove_procedure_item(self, widget: QWidget) -> None:
        if widget in self.procedure_items:
            self.procedure_items.remove(widget)
        card = self.step_cards.pop(widget, None)
        if card:
            card.layout().removeWidget(widget)
            widget.setParent(self)
            self.steps_layout.removeWidget(card)
            card.deleteLater()
        self._renumber_steps()

    def _move_step(self, card: ProcedureStepCard, offset: int) -> None:
        widget = card.content
        index = self.procedure_items.index(widget)
        target = index + offset
        if target < 0 or target >= len(self.procedure_items):
            return
        self.procedure_items.pop(index)
        self.procedure_items.insert(target, widget)
        self.steps_layout.removeWidget(card)
        self.steps_layout.insertWidget(target, card)
        self._renumber_steps()

    def _renumber_steps(self) -> None:
        for index, widget in enumerate(self.procedure_items):
            card = self.step_cards.get(widget)
            if card:
                card.set_number(index + 1)

    def _entry_type_changed(self) -> None:
        procedure = self.kind.currentData() == "procedure"
        self.standard_sections.setVisible(not procedure)
        self.procedure_section.setVisible(procedure)
        if procedure:
            ordered = self.procedure_items or [*self.rows, *self.group_rows]
            for widget in list(ordered):
                self.fields_layout.removeWidget(widget)
                self.groups_layout.removeWidget(widget)
                if widget not in self.procedure_items:
                    self._add_procedure_item(widget, "field" if isinstance(widget, FieldRow) else "group")
        else:
            for widget in list(self.procedure_items):
                self._remove_procedure_item(widget)
                if isinstance(widget, FieldRow):
                    self.fields_layout.addWidget(widget)
                else:
                    self.groups_layout.addWidget(widget)

    def _save(self) -> None:
        base = self.current_entry or Entry()
        fields = [row.field(i) for i, row in enumerate(self.rows)]
        groups = [card.group_definition(i) for i, card in enumerate(self.group_rows)]
        steps: list[ProcedureStep] = []
        if self.kind.currentData() == "procedure":
            for position, widget in enumerate(self.procedure_items):
                if isinstance(widget, FieldRow):
                    steps.append(ProcedureStep("field", self.rows.index(widget), position))
                else:
                    steps.append(ProcedureStep("group", self.group_rows.index(widget), position))
        entry = Entry(
            id=base.id, category_id=int(self.category.currentData()), title=self.title.text(), tags=self.tags.text(),
            notes=self.notes.toPlainText(), favorite=self.favorite.isChecked(), entry_type=str(self.kind.currentData()),
            created_at=base.created_at, updated_at=base.updated_at, last_used_at=base.last_used_at,
            use_count=base.use_count, fields=fields, group_fields=groups, procedure_steps=steps,
        )
        self.save_requested.emit(entry)

    def _toggle_favorite(self) -> None:
        checked = self.favorite.isChecked()
        self.favorite.setIcon(icon("star_filled" if checked else "star"))
        self.favorite.setToolTip("Remove from favorites" if checked else "Add to favorites")
        if self.current_entry and self.current_entry.id:
            self.favorite_toggled.emit(self.current_entry.id, checked)

    def _delete(self) -> None:
        if self.current_entry and self.current_entry.id:
            self.delete_requested.emit(self.current_entry.id)

    def _duplicate(self) -> None:
        if self.current_entry and self.current_entry.id:
            self.duplicate_requested.emit(self.current_entry.id)

    def _copy_entire(self) -> None:
        parts = [self.title.text()]
        if self.kind.currentData() == "procedure":
            for widget in self.procedure_items:
                if isinstance(widget, FieldRow):
                    parts.append(widget.value())
                else:
                    parts.append(widget.assembled_output())
        else:
            for row in self.rows:
                parts.append(f"{row.name.text().strip() or 'Value'}: {row.value()}")
            for card in self.group_rows:
                parts.append(card.assembled_output())
        if self.notes.toPlainText().strip():
            parts.append(self.notes.toPlainText())
        self.copy_requested.emit("\n\n".join(parts), any(r.secret_box.isChecked() for r in self.rows))

    def clear_sensitive_state(self) -> None:
        """Drop decrypted entry widgets when the vault locks."""
        for row in self.rows:
            row.reveal.setChecked(False)
            if row.secret_box.isChecked():
                row.single.clear()
                row.multi.clear()
        self.show_empty()
