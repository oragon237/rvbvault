import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from rvb_vault.app import AppController
from rvb_vault.db import Entry, EntryField
from rvb_vault.security import create_password_verifier
from rvb_vault.settings import AppPreferences, SettingsStore


class LockFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.previous_data_dir = os.environ.get("RVB_VAULT_DATA_DIR")
        os.environ["RVB_VAULT_DATA_DIR"] = self.temp.name
        settings = SettingsStore(QSettings(str(Path(self.temp.name) / "settings.ini"), QSettings.Format.IniFormat))
        settings.save(AppPreferences(global_hotkey=False, close_to_tray=False))
        settings.set_bytes("security/password_verifier", create_password_verifier("test-master-password"))
        self.controller = AppController(self.app, settings)

    def tearDown(self):
        self.controller.window.hide()
        self.controller.shutdown()
        if self.previous_data_dir is None:
            os.environ.pop("RVB_VAULT_DATA_DIR", None)
        else:
            os.environ["RVB_VAULT_DATA_DIR"] = self.previous_data_dir
        self.temp.cleanup()

    def test_lock_clears_visible_secret_and_sensitive_clipboard(self):
        category = self.controller.db.list_categories()[2]
        entry_id = self.controller.db.save_entry(
            Entry(category_id=category.id, title="Lock probe", fields=[EntryField(name="Password", value="only-in-memory", is_secret=True)])
        )
        self.assertEqual(self.controller.window.results.count(), 0, "No entries should be decrypted before first unlock")
        self.controller.window.refresh_entries()
        self.controller.window.open_entry(entry_id)
        self.assertEqual(self.controller.window.editor.rows[0].value(), "only-in-memory")
        self.controller.clipboard.copy("only-in-memory", sensitive=True)
        self.controller.remaining_seconds = 1
        self.controller._inactivity_tick()
        self.assertTrue(self.controller.locked)
        self.assertIsNone(self.controller.window.editor.current_entry)
        self.assertEqual(QApplication.clipboard().text(), "")

        class AcceptedUnlock:
            class DialogCode:
                Accepted = 1

            def __init__(self, verifier):
                pass

            def exec(self):
                return 1

        with patch("rvb_vault.app.UnlockDialog", AcceptedUnlock):
            self.controller.unlock()
        self.assertFalse(self.controller.locked)
        self.assertEqual(self.controller.window.editor.current_entry.id, entry_id)
        self.controller.session_monitor.lock_requested.emit()
        self.assertTrue(self.controller.locked)


if __name__ == "__main__":
    unittest.main()
