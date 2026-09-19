import json
import tempfile
import unittest
from pathlib import Path

from rvb_vault.backup import BackupManager
from rvb_vault.db import Entry, EntryField, GroupField, GroupSegment, VaultDatabase
from rvb_vault.security import LocalCipher


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cipher = LocalCipher(self.root / "key")
        self.db = VaultDatabase(self.root / "vault.db", self.cipher)
        self.manager = BackupManager(self.db, self.cipher, self.root / "backups")

    def tearDown(self):
        try:
            self.db.close()
        except Exception:
            pass
        self.tmp.cleanup()

    def test_encrypted_backup_and_json_transfer(self):
        category = self.db.list_categories()[0]
        self.db.save_entry(
            Entry(
                category_id=category.id,
                title="Backup marker",
                fields=[EntryField(value="transfer-secret", is_secret=True)],
                group_fields=[
                    GroupField(
                        name="API call",
                        segments=[
                            GroupSegment(kind="fixed", text="curl -H \"Authorization: Bearer "),
                            GroupSegment(kind="editable", label="Token", default_value="demo-token"),
                            GroupSegment(kind="fixed", text="\" | jq .\n"),
                        ],
                    )
                ],
            )
        )
        backup = self.manager.create_encrypted()
        self.assertTrue(backup.exists())
        self.assertNotIn(b"Backup marker", backup.read_bytes())
        raw = self.manager.validate_backup(backup)
        self.assertIn(b"SQLite format 3", raw[:20])

        export = self.root / "export.json"
        self.manager.export_json(export)
        exported_text = export.read_text(encoding="utf-8")
        self.assertNotIn("transfer-secret", exported_text)
        exported_payload = json.loads(exported_text)
        secret = exported_payload["entries"][0]["fields"][0]
        self.assertTrue(secret["is_secret"])
        self.assertIsNone(secret["value"])
        self.assertTrue(secret["redacted"])
        update_plan = self.manager.load_import(export)
        update_result = self.manager.import_plan(update_plan, [0], duplicate_mode="update")
        self.assertEqual(update_result.updated, 1)
        preserved = self.db.get_entry(self.db.list_entries("Backup marker")[0].id)
        self.assertEqual(preserved.fields[0].value, "transfer-secret")
        second_root = self.root / "second"
        second = VaultDatabase(second_root / "vault.db", LocalCipher(second_root / "key"))
        try:
            count = BackupManager(second, second.cipher, second_root / "backups").import_json(export)
            self.assertEqual(count, 1)
            imported = second.get_entry(second.list_entries("Backup marker")[0].id)
            self.assertEqual(imported.title, "Backup marker")
            self.assertEqual(imported.fields[0].value, "")
            self.assertTrue(imported.fields[0].is_secret)
            self.assertEqual(imported.group_fields[0].assemble(), 'curl -H "Authorization: Bearer demo-token" | jq .\n')
        finally:
            second.close()

    def test_password_backup_and_collection_import_duplicate_modes(self):
        category = self.db.list_categories()[1]
        self.db.save_entry(
            Entry(category_id=category.id, title="SSH Deploy", fields=[EntryField(value="secret-key", is_secret=True)])
        )
        backup = self.root / "portable.rvbbackup"
        self.manager.create_password_backup(backup, "correct horse battery staple")
        self.assertNotIn(b"secret-key", backup.read_bytes())
        with self.assertRaises(ValueError):
            self.manager.validate_backup(backup, "incorrect password")
        self.assertTrue(self.manager.validate_backup(backup, "correct horse battery staple").startswith(b"SQLite format 3"))

        collection = self.root / "collection.json"
        collection.write_text(
            json.dumps(
                {
                    "rvb_collection": 1,
                    "name": "SSH Essentials",
                    "category": "SSH Commands",
                    "entries": [
                        {"title": "SSH Deploy", "fields": [{"name": "Command", "value": "ssh demo"}]},
                        {"title": "SSH Logs", "notes": "tail logs", "fields": []},
                    ],
                }
            ),
            encoding="utf-8",
        )
        plan = self.manager.load_import(collection)
        self.assertEqual(plan.name, "SSH Essentials")
        self.assertIsNotNone(plan.items[0].existing_id)
        result = self.manager.import_plan(plan, [0, 1], duplicate_mode="skip")
        self.assertEqual((result.imported, result.skipped), (1, 1))
        self.assertEqual(len(self.db.list_entries(category_id=category.id)), 2)

    def test_rolling_prune_keeps_manual_and_preupgrade_backups(self):
        manual = self.manager.backup_dir / "rvb-vault-backup.rvbbackup"
        preupgrade = self.manager.backup_dir / "pre-upgrade-1.2.0-20260919-013739.rvbbackup"
        rolling_old = self.manager.backup_dir / "rvb-vault-20260918-010101.rvbbackup"
        rolling_new = self.manager.backup_dir / "rvb-vault-20260919-010101.rvbbackup"
        for path in (manual, preupgrade, rolling_old, rolling_new):
            path.write_bytes(b"test")
        self.manager.prune(1)
        self.assertTrue(manual.exists())
        self.assertTrue(preupgrade.exists())
        self.assertFalse(rolling_old.exists())
        self.assertTrue(rolling_new.exists())

    def test_password_backup_restore_requires_password_and_preserves_rollback(self):
        category = self.db.list_categories()[0]
        self.db.save_entry(Entry(category_id=category.id, title="Before backup"))
        backup = self.root / "restore-check.rvbbackup"
        self.manager.create_password_backup(backup, "correct horse battery staple")
        self.db.save_entry(Entry(category_id=category.id, title="After backup"))
        with self.assertRaises(ValueError):
            self.manager.restore_encrypted(backup, "incorrect password")
        self.assertEqual(len(self.db.list_entries()), 2)
        self.manager.restore_encrypted(backup, "correct horse battery staple")
        restored = VaultDatabase(self.root / "vault.db", self.cipher)
        try:
            self.assertEqual([entry.title for entry in restored.list_entries()], ["Before backup"])
            self.assertTrue((self.root / "vault.db.before-restore").exists())
        finally:
            restored.close()


if __name__ == "__main__":
    unittest.main()
