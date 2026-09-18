import sqlite3
import tempfile
import unittest
from pathlib import Path

from rvb_vault.db import Entry, EntryField, GroupField, GroupSegment, ProcedureStep, VaultDatabase
from rvb_vault.security import LocalCipher


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.db = VaultDatabase(root / "vault.db", LocalCipher(root / "key"))

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_defaults_crud_search_and_secret_exclusion(self):
        categories = self.db.list_categories()
        self.assertEqual([c.name for c in categories], ["Prompts", "SSH Commands", "Passwords"])
        entry_id = self.db.save_entry(
            Entry(
                category_id=categories[2].id,
                title="Production login",
                tags="hosting urgent",
                notes="Main control panel",
                fields=[
                    EntryField(name="URL", value="https://example.test"),
                    EntryField(name="Password", value="NeverIndexThis-938!", is_secret=True),
                ],
            )
        )
        loaded = self.db.get_entry(entry_id)
        self.assertEqual(loaded.fields[1].value, "NeverIndexThis-938!")
        self.assertEqual([e.id for e in self.db.list_entries("production")], [entry_id])
        self.assertEqual([e.id for e in self.db.list_entries("example.test")], [entry_id])
        self.assertEqual(self.db.list_entries("NeverIndexThis"), [])

        inspection = sqlite3.connect(self.db.path)
        try:
            raw = inspection.execute(
                "SELECT value_text, value_secret FROM entry_fields WHERE is_secret=1"
            ).fetchone()
            self.assertIsNone(raw[0])
            self.assertNotIn(b"NeverIndexThis", bytes(raw[1]))
            fts = inspection.execute("SELECT fields FROM entries_fts").fetchone()[0]
            self.assertNotIn("NeverIndexThis", fts)
        finally:
            inspection.close()

    def test_category_delete_requires_destination(self):
        categories = self.db.list_categories()
        source, target = categories[0], categories[1]
        self.db.save_entry(Entry(category_id=source.id, title="Move me"))
        with self.assertRaises(ValueError):
            self.db.delete_category(source.id)
        self.db.delete_category(source.id, target.id)
        self.assertEqual(self.db.list_entries()[0].category_id, target.id)

    def test_duplicate_and_usage(self):
        category = self.db.list_categories()[0]
        original = self.db.save_entry(Entry(category_id=category.id, title="Snippet", fields=[EntryField(value="abc")]))
        duplicate = self.db.duplicate_entry(original)
        self.db.record_use(duplicate)
        loaded = self.db.get_entry(duplicate)
        self.assertEqual(loaded.title, "Snippet Copy")
        self.assertEqual(loaded.use_count, 1)
        self.assertIsNotNone(loaded.last_used_at)

    def test_group_field_preserves_order_whitespace_and_searches_defaults(self):
        category = self.db.list_categories()[1]
        group = GroupField(
            name="MySQL Import",
            segments=[
                GroupSegment(kind="fixed", text="mysql -u "),
                GroupSegment(kind="editable", label="DB User", default_value="creditfuturellc"),
                GroupSegment(kind="fixed", text=" -p "),
                GroupSegment(kind="editable", label="DB Name", default_value="creditfuturellcdb"),
                GroupSegment(kind="fixed", text=" < "),
                GroupSegment(kind="editable", label="SQL File", default_value="backup.sql\n"),
            ],
        )
        entry_id = self.db.save_entry(Entry(category_id=category.id, title="Database restore", group_fields=[group]))
        loaded = self.db.get_entry(entry_id)
        self.assertEqual(len(loaded.group_fields), 1)
        self.assertEqual(
            loaded.group_fields[0].assemble(),
            "mysql -u creditfuturellc -p creditfuturellcdb < backup.sql\n",
        )
        self.assertEqual(
            loaded.group_fields[0].assemble({1: "admin", 3: "prod", 5: 'nightly backup.sql'}),
            "mysql -u admin -p prod < nightly backup.sql",
        )
        self.assertEqual(self.db.list_entries("creditfuturellcdb")[0].id, entry_id)

    def test_procedure_preserves_mixed_step_order(self):
        category = self.db.list_categories()[1]
        entry_id = self.db.save_entry(
            Entry(
                category_id=category.id,
                title="Deploy workflow",
                entry_type="procedure",
                fields=[EntryField(name="First", value="cd /srv"), EntryField(name="Last", value="done")],
                group_fields=[GroupField(name="Deploy", segments=[GroupSegment(kind="fixed", text="git pull")])],
                procedure_steps=[
                    ProcedureStep("field", 0, 0),
                    ProcedureStep("group", 0, 1),
                    ProcedureStep("field", 1, 2),
                ],
            )
        )
        loaded = self.db.get_entry(entry_id)
        self.assertEqual([(step.kind, step.item_index) for step in loaded.procedure_steps], [("field", 0), ("group", 0), ("field", 1)])


if __name__ == "__main__":
    unittest.main()
