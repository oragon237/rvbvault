from __future__ import annotations

import json
import re
import shutil
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from rvb_vault.db import Entry, EntryField, GroupField, GroupSegment, ProcedureStep, VaultDatabase
from rvb_vault.security import (
    PASSWORD_BACKUP_MAGIC,
    LocalCipher,
    decrypt_with_password,
    encrypt_with_password,
)


@dataclass(slots=True)
class ImportItem:
    entry: Entry
    category_name: str
    existing_id: int | None = None
    redacted_fields: set[int] | None = None


@dataclass(slots=True)
class ImportPlan:
    name: str
    items: list[ImportItem]
    default_category: str = ""
    is_collection: bool = False


@dataclass(slots=True)
class ImportResult:
    imported: int = 0
    updated: int = 0
    skipped: int = 0

    @property
    def total(self) -> int:
        return self.imported + self.updated


class BackupManager:
    def __init__(self, db: VaultDatabase, cipher: LocalCipher, backup_dir: Path) -> None:
        self.db = db
        self.cipher = cipher
        self.backup_dir = backup_dir
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def _snapshot_bytes(self) -> bytes:
        self.db.checkpoint()
        memory = sqlite3.connect(":memory:")
        try:
            self.db.conn.backup(memory)
            snapshot = bytearray(memory.serialize())
            # The source uses WAL, but sqlite3.deserialize() has no sidecar WAL.
            # The backup API has already merged every page, so mark the portable
            # snapshot as rollback-journal format for in-memory validation/restore.
            if snapshot.startswith(b"SQLite format 3\x00") and len(snapshot) > 19:
                snapshot[18] = 1
                snapshot[19] = 1
            return bytes(snapshot)
        finally:
            memory.close()

    @staticmethod
    def _validate_database_bytes(raw: bytes) -> None:
        cx = sqlite3.connect(":memory:")
        try:
            cx.deserialize(raw)
            result = cx.execute("PRAGMA integrity_check").fetchone()[0]
            if result != "ok":
                raise ValueError(f"Backup integrity check failed: {result}")
            if not cx.execute("SELECT 1 FROM sqlite_master WHERE name='entries'").fetchone():
                raise ValueError("Not an RVB Vault backup")
        finally:
            cx.close()

    def create_encrypted(self, destination: Path | None = None) -> Path:
        """Create a Windows-account-bound rolling backup without plaintext temp files."""
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        destination = destination or self.backup_dir / f"rvb-vault-{stamp}.rvbbackup"
        destination.write_bytes(self.cipher.encrypt(self._snapshot_bytes(), context=b"backup"))
        return destination

    def create_password_backup(self, destination: Path, password: str) -> Path:
        destination.write_bytes(encrypt_with_password(self._snapshot_bytes(), password))
        return destination

    def validate_backup(self, source: Path, password: str | None = None) -> bytes:
        payload = source.read_bytes()
        if payload.startswith(PASSWORD_BACKUP_MAGIC):
            if password is None:
                raise ValueError("This backup requires its recovery password")
            raw = decrypt_with_password(payload, password)
        else:
            raw = self.cipher.decrypt(payload, context=b"backup")
        # Earlier RVB backups stored a complete snapshot with WAL header bytes.
        # A standalone restore has no WAL sidecar, so normalize that header.
        if raw.startswith(b"SQLite format 3\x00") and len(raw) > 19 and raw[18:20] == b"\x02\x02":
            normalized = bytearray(raw)
            normalized[18] = normalized[19] = 1
            raw = bytes(normalized)
        self._validate_database_bytes(raw)
        return raw

    def restore_encrypted(self, source: Path, password: str | None = None) -> None:
        raw = self.validate_backup(source, password)
        self.db.checkpoint()
        self.db.close()
        rollback = self.db.path.with_suffix(".db.before-restore")
        if self.db.path.exists():
            shutil.copy2(self.db.path, rollback)
        Path(f"{self.db.path}-wal").unlink(missing_ok=True)
        Path(f"{self.db.path}-shm").unlink(missing_ok=True)
        self.db.path.write_bytes(raw)

    def prune(self, keep: int) -> None:
        files = sorted(
            (path for path in self.backup_dir.glob("rvb-vault-*.rvbbackup")
             if re.fullmatch(r"rvb-vault-\d{8}-\d{6}\.rvbbackup", path.name)),
            reverse=True,
        )
        for old in files[max(keep, 1):]:
            old.unlink(missing_ok=True)

    @staticmethod
    def _entry_payload(entry: Entry, *, redact_secrets: bool) -> dict:
        data = asdict(entry)
        for field in data["fields"]:
            if field.get("is_secret") and redact_secrets:
                field["value"] = None
                field["redacted"] = True
        return data

    def export_json(self, destination: Path) -> None:
        """Safe export: structure is portable, secret values are always redacted."""
        payload = {"format": 1, "safe_export": True, "categories": [], "entries": []}
        for category in self.db.list_categories():
            payload["categories"].append(asdict(category))
        for summary in self.db.list_entries(limit=100_000):
            entry = self.db.get_entry(summary.id, include_secrets=False)
            if entry:
                payload["entries"].append(self._entry_payload(entry, redact_secrets=True))
        destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def export_collection(self, destination: Path, name: str, category_id: int) -> None:
        categories = {c.id: c.name for c in self.db.list_categories()}
        category_name = categories.get(category_id)
        if not category_name:
            raise ValueError("Category not found")
        entries = []
        for summary in self.db.list_entries(category_id=category_id, limit=100_000):
            entry = self.db.get_entry(summary.id, include_secrets=False)
            if entry:
                data = self._entry_payload(entry, redact_secrets=True)
                data.pop("category_id", None)
                entries.append(data)
        payload = {
            "rvb_collection": 1,
            "name": name.strip() or f"{category_name} Collection",
            "category": category_name,
            "entries": entries,
        }
        destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _entry_from_dict(item: dict, category_id: int = 0) -> Entry:
        fields = []
        for raw in item.get("fields", []):
            fields.append(
                EntryField(
                    name=str(raw.get("name") or "Value"),
                    value="" if raw.get("value") is None else str(raw.get("value", "")),
                    is_secret=bool(raw.get("is_secret", False)),
                    multiline=bool(raw.get("multiline", False)),
                    position=int(raw.get("position", len(fields))),
                )
            )
        groups: list[GroupField] = []
        for raw_group in item.get("group_fields", []):
            segments = []
            for raw_segment in raw_group.get("segments", []):
                kind = str(raw_segment.get("kind", "fixed"))
                segments.append(
                    GroupSegment(
                        kind=kind if kind in {"fixed", "editable"} else "fixed",
                        label=str(raw_segment.get("label", "")),
                        text=str(raw_segment.get("text", raw_segment.get("fixed_text", ""))),
                        default_value=str(raw_segment.get("default_value", "")),
                        position=int(raw_segment.get("position", len(segments))),
                    )
                )
            groups.append(
                GroupField(
                    name=str(raw_group.get("name") or "Command Builder"),
                    position=int(raw_group.get("position", len(groups))),
                    segments=segments,
                )
            )
        steps = []
        for raw_step in item.get("procedure_steps", []):
            kind = str(raw_step.get("kind", "field"))
            if kind in {"field", "group"}:
                steps.append(
                    ProcedureStep(
                        kind=kind,
                        item_index=int(raw_step.get("item_index", 0)),
                        position=int(raw_step.get("position", len(steps))),
                    )
                )
        return Entry(
            category_id=category_id,
            title=str(item.get("title") or "Untitled entry"),
            tags=str(item.get("tags") or ""),
            notes=str(item.get("notes") or ""),
            favorite=bool(item.get("favorite", False)),
            entry_type=str(item.get("entry_type") or "standard"),
            fields=fields,
            group_fields=groups,
            procedure_steps=steps,
        )

    def load_import(self, source: Path) -> ImportPlan:
        payload = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Invalid RVB JSON file")
        is_collection = payload.get("rvb_collection") == 1
        is_export = payload.get("format") in {1, 2}
        if not is_collection and not is_export:
            raise ValueError("Unsupported RVB export or collection format")

        category_by_id = {
            int(c["id"]): str(c["name"])
            for c in payload.get("categories", [])
            if isinstance(c, dict) and "id" in c and "name" in c
        }
        default_category = str(payload.get("category") or "") if is_collection else ""
        fallback = default_category or next(iter(category_by_id.values()), "General Notes")
        items: list[ImportItem] = []
        for raw in payload.get("entries", []):
            if not isinstance(raw, dict):
                continue
            category_name = str(raw.get("category") or "")
            if not category_name and raw.get("category_id") is not None:
                try:
                    category_name = category_by_id.get(int(raw["category_id"]), "")
                except (TypeError, ValueError):
                    pass
            category_name = category_name or fallback
            redacted_fields = {
                index
                for index, field in enumerate(raw.get("fields", []))
                if isinstance(field, dict) and bool(field.get("redacted"))
            }
            items.append(ImportItem(self._entry_from_dict(raw), category_name, redacted_fields=redacted_fields))
        if not items:
            raise ValueError("The file contains no importable entries")
        plan = ImportPlan(
            name=str(payload.get("name") or ("RVB Vault Safe Export" if is_export else "RVB Collection")),
            items=items,
            default_category=default_category,
            is_collection=is_collection,
        )
        self.annotate_duplicates(plan)
        return plan

    def annotate_duplicates(self, plan: ImportPlan, target_category: str | None = None) -> None:
        categories = {c.name.casefold(): c.id for c in self.db.list_categories()}
        for item in plan.items:
            item.existing_id = None
            category_name = target_category or item.category_name
            category_id = categories.get(category_name.casefold())
            if category_id is None:
                continue
            for existing in self.db.list_entries(category_id=category_id, limit=100_000):
                if existing.title.casefold() == item.entry.title.casefold():
                    item.existing_id = existing.id
                    break

    def import_plan(
        self,
        plan: ImportPlan,
        selected: list[int],
        *,
        duplicate_mode: str = "skip",
        target_category: str | None = None,
    ) -> ImportResult:
        if duplicate_mode not in {"skip", "update", "keep"}:
            raise ValueError("Invalid duplicate handling mode")
        categories = {c.name.casefold(): c.id for c in self.db.list_categories()}
        result = ImportResult()
        with self.db.transaction():
            for index in selected:
                item = plan.items[index]
                category_name = (target_category or item.category_name).strip() or "General Notes"
                category_id = categories.get(category_name.casefold())
                if category_id is None:
                    created = self.db.create_category(category_name)
                    category_id = created.id
                    categories[category_name.casefold()] = category_id
                duplicate_id = None
                for existing in self.db.list_entries(category_id=category_id, limit=100_000):
                    if existing.title.casefold() == item.entry.title.casefold():
                        duplicate_id = existing.id
                        break
                if duplicate_id and duplicate_mode == "skip":
                    result.skipped += 1
                    continue
                entry = item.entry
                entry.category_id = category_id
                entry.id = duplicate_id if duplicate_id and duplicate_mode == "update" else None
                if entry.id:
                    existing_entry = self.db.get_entry(entry.id)
                    if existing_entry:
                        for field_index in item.redacted_fields or set():
                            if field_index >= len(entry.fields):
                                continue
                            incoming = entry.fields[field_index]
                            matching = next(
                                (
                                    field
                                    for field in existing_entry.fields
                                    if field.is_secret and field.name.casefold() == incoming.name.casefold()
                                ),
                                None,
                            )
                            if matching:
                                incoming.value = matching.value
                        incoming_secret_names = {
                            field.name.casefold() for field in entry.fields if field.is_secret
                        }
                        for existing_field in existing_entry.fields:
                            if existing_field.is_secret and existing_field.name.casefold() not in incoming_secret_names:
                                entry.fields.append(existing_field)
                self.db.save_entry(entry)
                if duplicate_id and duplicate_mode == "update":
                    result.updated += 1
                else:
                    result.imported += 1
        return result

    def import_json(self, source: Path) -> int:
        """Backward-compatible non-interactive import used by tests and integrations."""
        plan = self.load_import(source)
        return self.import_plan(plan, list(range(len(plan.items))), duplicate_mode="keep").total
