import os
import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import QSettings

from rvb_vault.settings import SettingsStore
from rvb_vault.ui.editor import format_local_timestamp
from rvb_vault.windows_security import WindowsHelloAuthenticator


class SettingsAndWindowsTests(unittest.TestCase):
    def test_fresh_settings_default_to_fifteen_minute_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            qs = QSettings(str(Path(tmp) / "settings.ini"), QSettings.Format.IniFormat)
            self.assertEqual(SettingsStore(qs).load().auto_lock_minutes, 15)

    def test_utc_timestamp_is_formatted_for_local_display(self):
        formatted = format_local_timestamp("2026-09-18T17:24:00+00:00")
        self.assertIn("2026", formatted)
        self.assertIn("·", formatted)
        self.assertNotIn("UTC", formatted)

    @unittest.skipUnless(os.name == "nt", "Windows Hello is Windows-only")
    def test_windows_hello_desktop_gate_fails_closed(self):
        authenticator = WindowsHelloAuthenticator()
        self.assertFalse(authenticator.available())
        self.assertIn("not supported", authenticator.last_error)


if __name__ == "__main__":
    unittest.main()
