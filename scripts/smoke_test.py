"""Headless UI smoke test used by CI and local verification."""

from __future__ import annotations

import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("RVB_VAULT_DATA_DIR", tempfile.mkdtemp(prefix="rvb-vault-smoke-"))

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication, QLineEdit

from rvb_vault.app import AppController, app_icon
from rvb_vault.db import Entry, EntryField, GroupField, GroupSegment, ProcedureStep


def main() -> int:
    app = QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)
    controller = AppController(app)
    icon_sizes = {(size.width(), size.height()) for size in app_icon().availableSizes()}
    assert {(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)} <= icon_sizes
    category = controller.db.list_categories()[0]
    entry_id = controller.db.save_entry(
        Entry(
            category_id=category.id,
            title="Smoke entry",
            fields=[
                EntryField(name="Command", value="echo ready"),
                EntryField(name="Password", value="smoke-secret", is_secret=True),
            ],
            group_fields=[
                GroupField(
                    name="Smoke builder",
                    segments=[
                        GroupSegment(kind="fixed", text="echo \""),
                        GroupSegment(kind="editable", label="Value", default_value="ready"),
                        GroupSegment(kind="fixed", text="\" | test\n"),
                    ],
                )
            ],
        )
    )
    controller.window.reload_categories()
    controller.window.refresh_entries()
    assert controller.db.get_entry(entry_id).fields[0].value == "echo ready"
    assert controller.db.get_entry(entry_id).group_fields[0].assemble() == 'echo "ready" | test\n'
    controller.window.showMaximized()
    app.processEvents()
    controller.window.open_entry(entry_id)
    app.processEvents()
    assert controller.window.isMaximized(), "Opening an entry must not restore a maximized window"
    controller.window.editor._save()
    app.processEvents()
    assert controller.window.isMaximized(), "Saving an entry must not restore a maximized window"
    assert len(controller.window.editor.group_rows) == 1
    card = controller.window.editor.group_rows[0]
    card.inputs[1].setPlainText("changed value")
    app.processEvents()
    assert card.preview.toPlainText() == 'echo "changed value" | test\n'
    procedure_id = controller.db.save_entry(
        Entry(
            category_id=category.id,
            title="Smoke procedure",
            entry_type="procedure",
            fields=[EntryField(name="Start", value="cd /srv"), EntryField(name="Finish", value="done")],
            group_fields=[GroupField(name="Deploy", segments=[GroupSegment(kind="fixed", text="git pull")])],
            procedure_steps=[ProcedureStep("field", 0, 0), ProcedureStep("group", 0, 1), ProcedureStep("field", 1, 2)],
        )
    )
    controller.window.open_entry(procedure_id)
    app.processEvents()
    assert controller.window.editor.kind.currentData() == "procedure"
    assert len(controller.window.editor.procedure_items) == 3
    middle_card = controller.window.editor.step_cards[controller.window.editor.procedure_items[1]]
    controller.window.editor._move_step(middle_card, -1)
    controller.window.editor._save()
    app.processEvents()
    reordered = controller.db.get_entry(procedure_id)
    assert [(step.kind, step.item_index) for step in reordered.procedure_steps] == [("group", 0), ("field", 0), ("field", 1)]
    controller.window.search.setText("Smoke entry")
    app.processEvents()
    assert controller.window.results.count() == 1
    controller.window.editor.rows[0].copy_button.click()
    app.processEvents()
    assert QApplication.clipboard().text() == "echo ready"
    assert controller.window.editor.rows[0].copy_button.text() == "✓"
    secret_row = controller.window.editor.rows[1]
    assert secret_row.single.echoMode() == QLineEdit.EchoMode.Password
    secret_row.reveal.click()
    assert secret_row.single.echoMode() == QLineEdit.EchoMode.Normal
    secret_row.copy_button.click()
    app.processEvents()
    assert QApplication.clipboard().text() == "smoke-secret"
    for row in range(controller.window.nav.count()):
        if controller.window.nav.item(row).data(Qt.ItemDataRole.UserRole) == category.id:
            controller.window.nav.setCurrentRow(row)
            break
    app.processEvents()
    assert controller.window.selected_category_id() == category.id
    controller.window.show()
    QTimer.singleShot(150, app.quit)
    code = app.exec()
    controller.shutdown()
    print("RVB Vault headless smoke test passed")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
