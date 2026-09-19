import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from rvb_vault.backup import BackupManager, ImportItem, ImportPlan
from rvb_vault.db import Entry, VaultDatabase
from rvb_vault.security import LocalCipher
from rvb_vault.ui.import_dialog import ImportPreviewDialog


class ImportPreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_selection_and_cancel_do_not_write_to_vault(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db = VaultDatabase(root / "vault.db", LocalCipher(root / "vault.key"))
            try:
                manager = BackupManager(db, db.cipher, root / "backups")
                plan = ImportPlan(
                    name="Git Collection",
                    default_category="GitHub",
                    is_collection=True,
                    items=[
                        ImportItem(Entry(title="git status"), "GitHub"),
                        ImportItem(Entry(title="git log"), "GitHub"),
                    ],
                )
                preview = ImportPreviewDialog(plan, db.list_categories())
                self.assertEqual(preview.selected_indices(), [0, 1])
                self.assertEqual(preview.target_category(), "GitHub")
                preview._set_all(Qt.CheckState.Unchecked)
                self.assertEqual(preview.selected_indices(), [])
                preview.reject()
                self.assertEqual(db.list_entries(), [])
                self.assertFalse(any(c.name == "GitHub" for c in db.list_categories()))
                result = manager.import_plan(plan, [1], target_category="GitHub")
                self.assertEqual(result.imported, 1)
                self.assertEqual(db.list_entries()[0].title, "git log")
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
