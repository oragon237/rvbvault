from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator

from rvb_vault.security import LocalCipher


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass(slots=True)
class Category:
    id: int
    name: str
    position: int
    is_system: bool = False


@dataclass(slots=True)
class EntryField:
    id: int | None = None
    name: str = "Value"
    value: str = ""
    is_secret: bool = False
    multiline: bool = False
    position: int = 0


@dataclass(slots=True)
class GroupSegment:
    id: int | None = None
    kind: str = "fixed"
    label: str = ""
    text: str = ""
    default_value: str = ""
    position: int = 0


@dataclass(slots=True)
class GroupField:
    id: int | None = None
    name: str = "Command Builder"
    position: int = 0
    segments: list[GroupSegment] = field(default_factory=list)

    def assemble(self, values: dict[int, str] | None = None) -> str:
        values = values or {}
        pieces: list[str] = []
        for index, segment in enumerate(self.segments):
            if segment.kind == "fixed":
                pieces.append(segment.text)
            else:
                pieces.append(values.get(index, segment.default_value))
        return "".join(pieces)


@dataclass(slots=True)
class ProcedureStep:
    kind: str = "field"
    item_index: int = 0
    position: int = 0


@dataclass(slots=True)
class Entry:
    id: int | None = None
    category_id: int = 0
    title: str = ""
    tags: str = ""
    notes: str = ""
    favorite: bool = False
    entry_type: str = "standard"
    created_at: str = ""
    updated_at: str = ""
    last_used_at: str | None = None
    use_count: int = 0
    fields: list[EntryField] = field(default_factory=list)
    group_fields: list[GroupField] = field(default_factory=list)
    procedure_steps: list[ProcedureStep] = field(default_factory=list)


class VaultDatabase:
    def __init__(self, path: Path, cipher: LocalCipher) -> None:
        self.path = path
        self.cipher = cipher
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self._migrate()

    def close(self) -> None:
        self.conn.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        nested = self.conn.in_transaction
        if not nested:
            self.conn.execute("BEGIN")
        try:
            yield self.conn
            if not nested:
                self.conn.commit()
        except Exception:
            if not nested:
                self.conn.rollback()
            raise

    def _migrate(self) -> None:
        with self.transaction() as cx:
            cx.executescript(
                """
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    position INTEGER NOT NULL,
                    is_system INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE RESTRICT,
                    title TEXT NOT NULL,
                    tags TEXT NOT NULL DEFAULT '',
                    notes TEXT NOT NULL DEFAULT '',
                    favorite INTEGER NOT NULL DEFAULT 0,
                    entry_type TEXT NOT NULL DEFAULT 'standard',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_used_at TEXT,
                    use_count INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS entry_fields (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    value_text TEXT,
                    value_secret BLOB,
                    is_secret INTEGER NOT NULL DEFAULT 0,
                    multiline INTEGER NOT NULL DEFAULT 0,
                    position INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS group_fields (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    position INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS group_segments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_field_id INTEGER NOT NULL REFERENCES group_fields(id) ON DELETE CASCADE,
                    kind TEXT NOT NULL CHECK(kind IN ('fixed', 'editable')),
                    label TEXT NOT NULL DEFAULT '',
                    fixed_text TEXT NOT NULL DEFAULT '',
                    default_value TEXT NOT NULL DEFAULT '',
                    position INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_entries_category ON entries(category_id);
                CREATE INDEX IF NOT EXISTS idx_entries_recent ON entries(last_used_at DESC);
                CREATE INDEX IF NOT EXISTS idx_group_fields_entry ON group_fields(entry_id, position);
                CREATE INDEX IF NOT EXISTS idx_group_segments_group ON group_segments(group_field_id, position);
                CREATE TABLE IF NOT EXISTS procedure_steps (
                    entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
                    step_kind TEXT NOT NULL CHECK(step_kind IN ('field', 'group')),
                    item_index INTEGER NOT NULL,
                    position INTEGER NOT NULL,
                    PRIMARY KEY(entry_id, position)
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(
                    entry_id UNINDEXED,
                    title,
                    tags,
                    notes,
                    fields,
                    tokenize='unicode61 remove_diacritics 2'
                );
                """
            )
            count = cx.execute("SELECT COUNT(*) FROM categories").fetchone()[0]
            if count == 0:
                cx.executemany(
                    "INSERT INTO categories(name, position, is_system) VALUES(?, ?, 1)",
                    [("Prompts", 0), ("SSH Commands", 1), ("Passwords", 2)],
                )
            cx.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('schema_version', '3')")

    def list_categories(self) -> list[Category]:
        rows = self.conn.execute(
            "SELECT id, name, position, is_system FROM categories ORDER BY position, name COLLATE NOCASE"
        ).fetchall()
        return [Category(r["id"], r["name"], r["position"], bool(r["is_system"])) for r in rows]

    def create_category(self, name: str) -> Category:
        name = name.strip()
        if not name:
            raise ValueError("Category name cannot be empty")
        with self.transaction() as cx:
            pos = cx.execute("SELECT COALESCE(MAX(position), -1) + 1 FROM categories").fetchone()[0]
            cur = cx.execute("INSERT INTO categories(name, position) VALUES(?, ?)", (name, pos))
        return Category(cur.lastrowid, name, pos, False)

    def rename_category(self, category_id: int, name: str) -> None:
        name = name.strip()
        if not name:
            raise ValueError("Category name cannot be empty")
        with self.transaction() as cx:
            cx.execute("UPDATE categories SET name=? WHERE id=?", (name, category_id))

    def reorder_categories(self, ordered_ids: list[int]) -> None:
        with self.transaction() as cx:
            for position, category_id in enumerate(ordered_ids):
                cx.execute("UPDATE categories SET position=? WHERE id=?", (position, category_id))

    def category_entry_count(self, category_id: int) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM entries WHERE category_id=?", (category_id,)).fetchone()[0])

    def delete_category(self, category_id: int, move_to: int | None = None) -> None:
        with self.transaction() as cx:
            count = cx.execute("SELECT COUNT(*) FROM entries WHERE category_id=?", (category_id,)).fetchone()[0]
            if count and move_to is None:
                raise ValueError("Category is not empty; choose a destination first")
            if move_to == category_id:
                raise ValueError("Destination must be a different category")
            if count:
                cx.execute("UPDATE entries SET category_id=?, updated_at=? WHERE category_id=?", (move_to, utc_now(), category_id))
            cx.execute("DELETE FROM categories WHERE id=?", (category_id,))

    def save_entry(self, entry: Entry) -> int:
        title = entry.title.strip()
        if not title:
            raise ValueError("Title cannot be empty")
        now = utc_now()
        with self.transaction() as cx:
            if entry.id is None:
                cur = cx.execute(
                    """INSERT INTO entries(category_id,title,tags,notes,favorite,entry_type,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (entry.category_id, title, entry.tags.strip(), entry.notes, int(entry.favorite), entry.entry_type, now, now),
                )
                entry_id = int(cur.lastrowid)
            else:
                entry_id = entry.id
                cx.execute(
                    """UPDATE entries SET category_id=?,title=?,tags=?,notes=?,favorite=?,entry_type=?,updated_at=?
                       WHERE id=?""",
                    (entry.category_id, title, entry.tags.strip(), entry.notes, int(entry.favorite), entry.entry_type, now, entry_id),
                )
                cx.execute("DELETE FROM entry_fields WHERE entry_id=?", (entry_id,))
                cx.execute("DELETE FROM group_fields WHERE entry_id=?", (entry_id,))
                cx.execute("DELETE FROM procedure_steps WHERE entry_id=?", (entry_id,))
            for pos, item in enumerate(entry.fields):
                secret = self.cipher.encrypt(item.value) if item.is_secret and item.value else None
                plain = None if item.is_secret else item.value
                cx.execute(
                    """INSERT INTO entry_fields(entry_id,name,value_text,value_secret,is_secret,multiline,position)
                       VALUES(?,?,?,?,?,?,?)""",
                    (entry_id, item.name.strip() or "Value", plain, secret, int(item.is_secret), int(item.multiline), pos),
                )
            for group_pos, group in enumerate(entry.group_fields):
                cur = cx.execute(
                    "INSERT INTO group_fields(entry_id,name,position) VALUES(?,?,?)",
                    (entry_id, group.name.strip() or "Command Builder", group_pos),
                )
                group_id = int(cur.lastrowid)
                for segment_pos, segment in enumerate(group.segments):
                    kind = segment.kind if segment.kind in {"fixed", "editable"} else "fixed"
                    cx.execute(
                        """INSERT INTO group_segments(group_field_id,kind,label,fixed_text,default_value,position)
                           VALUES(?,?,?,?,?,?)""",
                        (
                            group_id, kind, segment.label, segment.text if kind == "fixed" else "",
                            segment.default_value if kind == "editable" else "", segment_pos,
                        ),
                    )
            if entry.entry_type == "procedure":
                steps = entry.procedure_steps or (
                    [ProcedureStep("field", index, index) for index in range(len(entry.fields))]
                    + [ProcedureStep("group", index, len(entry.fields) + index) for index in range(len(entry.group_fields))]
                )
                for position, step in enumerate(steps):
                    if step.kind not in {"field", "group"}:
                        continue
                    cx.execute(
                        "INSERT INTO procedure_steps(entry_id,step_kind,item_index,position) VALUES(?,?,?,?)",
                        (entry_id, step.kind, step.item_index, position),
                    )
            self._reindex(cx, entry_id)
        return entry_id

    def _reindex(self, cx: sqlite3.Connection, entry_id: int) -> None:
        cx.execute("DELETE FROM entries_fts WHERE entry_id=?", (entry_id,))
        row = cx.execute("SELECT title,tags,notes FROM entries WHERE id=?", (entry_id,)).fetchone()
        if not row:
            return
        public_fields = cx.execute(
            "SELECT name, value_text FROM entry_fields WHERE entry_id=? AND is_secret=0 ORDER BY position",
            (entry_id,),
        ).fetchall()
        field_text = "\n".join(f"{r['name']} {r['value_text'] or ''}" for r in public_fields)
        group_rows = cx.execute(
            """SELECT gf.name, gs.label, gs.fixed_text, gs.default_value
               FROM group_fields gf JOIN group_segments gs ON gs.group_field_id=gf.id
               WHERE gf.entry_id=? ORDER BY gf.position, gs.position""",
            (entry_id,),
        ).fetchall()
        if group_rows:
            field_text += "\n" + "\n".join(
                f"{r['name']} {r['label']} {r['fixed_text']} {r['default_value']}" for r in group_rows
            )
        cx.execute(
            "INSERT INTO entries_fts(entry_id,title,tags,notes,fields) VALUES(?,?,?,?,?)",
            (entry_id, row["title"], row["tags"], row["notes"], field_text),
        )

    def get_entry(self, entry_id: int, *, include_secrets: bool = True) -> Entry | None:
        row = self.conn.execute("SELECT * FROM entries WHERE id=?", (entry_id,)).fetchone()
        if not row:
            return None
        field_rows = self.conn.execute(
            "SELECT * FROM entry_fields WHERE entry_id=? ORDER BY position", (entry_id,)
        ).fetchall()
        fields: list[EntryField] = []
        for f in field_rows:
            is_secret = bool(f["is_secret"])
            value = ""
            if is_secret and include_secrets and f["value_secret"]:
                value = self.cipher.decrypt(bytes(f["value_secret"])).decode("utf-8")
            elif not is_secret:
                value = f["value_text"] or ""
            fields.append(EntryField(f["id"], f["name"], value, is_secret, bool(f["multiline"]), f["position"]))
        group_fields: list[GroupField] = []
        group_rows = self.conn.execute(
            "SELECT id,name,position FROM group_fields WHERE entry_id=? ORDER BY position", (entry_id,)
        ).fetchall()
        for group_row in group_rows:
            segment_rows = self.conn.execute(
                """SELECT id,kind,label,fixed_text,default_value,position FROM group_segments
                   WHERE group_field_id=? ORDER BY position""",
                (group_row["id"],),
            ).fetchall()
            segments = [
                GroupSegment(
                    id=s["id"], kind=s["kind"], label=s["label"], text=s["fixed_text"],
                    default_value=s["default_value"], position=s["position"],
                )
                for s in segment_rows
            ]
            group_fields.append(GroupField(group_row["id"], group_row["name"], group_row["position"], segments))
        step_rows = self.conn.execute(
            "SELECT step_kind,item_index,position FROM procedure_steps WHERE entry_id=? ORDER BY position",
            (entry_id,),
        ).fetchall()
        procedure_steps = [ProcedureStep(r["step_kind"], r["item_index"], r["position"]) for r in step_rows]
        if row["entry_type"] == "procedure" and not procedure_steps:
            procedure_steps = (
                [ProcedureStep("field", index, index) for index in range(len(fields))]
                + [ProcedureStep("group", index, len(fields) + index) for index in range(len(group_fields))]
            )
        return Entry(
            id=row["id"], category_id=row["category_id"], title=row["title"], tags=row["tags"],
            notes=row["notes"], favorite=bool(row["favorite"]), entry_type=row["entry_type"],
            created_at=row["created_at"], updated_at=row["updated_at"], last_used_at=row["last_used_at"],
            use_count=row["use_count"], fields=fields, group_fields=group_fields, procedure_steps=procedure_steps,
        )

    def list_entries(
        self,
        query: str = "",
        category_id: int | None = None,
        *,
        favorites_only: bool = False,
        recent_only: bool = False,
        limit: int = 200,
    ) -> list[Entry]:
        params: list[object] = []
        where: list[str] = []
        join = ""
        if query.strip():
            tokens = re.findall(r"[\w@./:\\-]+", query, flags=re.UNICODE)
            if tokens:
                fts_query = " AND ".join('"' + t.replace('"', '""') + '"*' for t in tokens)
                join = " JOIN entries_fts f ON f.entry_id=e.id "
                where.append("entries_fts MATCH ?")
                params.append(fts_query)
        if category_id is not None:
            where.append("e.category_id=?")
            params.append(category_id)
        if favorites_only:
            where.append("e.favorite=1")
        if recent_only:
            where.append("e.last_used_at IS NOT NULL")
        clause = " WHERE " + " AND ".join(where) if where else ""
        order = "e.favorite DESC, e.last_used_at DESC, e.updated_at DESC, e.title COLLATE NOCASE"
        rows = self.conn.execute(
            f"SELECT e.* FROM entries e {join}{clause} ORDER BY {order} LIMIT ?", (*params, limit)
        ).fetchall()
        return [
            Entry(
                id=r["id"], category_id=r["category_id"], title=r["title"], tags=r["tags"], notes=r["notes"],
                favorite=bool(r["favorite"]), entry_type=r["entry_type"], created_at=r["created_at"],
                updated_at=r["updated_at"], last_used_at=r["last_used_at"], use_count=r["use_count"],
            )
            for r in rows
        ]

    def duplicate_entry(self, entry_id: int) -> int:
        entry = self.get_entry(entry_id)
        if entry is None:
            raise ValueError("Entry not found")
        entry.id = None
        entry.title = f"{entry.title} Copy"
        entry.favorite = False
        entry.use_count = 0
        entry.last_used_at = None
        return self.save_entry(entry)

    def delete_entry(self, entry_id: int) -> None:
        with self.transaction() as cx:
            cx.execute("DELETE FROM entries_fts WHERE entry_id=?", (entry_id,))
            cx.execute("DELETE FROM entries WHERE id=?", (entry_id,))

    def set_favorite(self, entry_id: int, favorite: bool) -> None:
        with self.transaction() as cx:
            cx.execute("UPDATE entries SET favorite=?, updated_at=? WHERE id=?", (int(favorite), utc_now(), entry_id))

    def record_use(self, entry_id: int) -> None:
        with self.transaction() as cx:
            cx.execute(
                "UPDATE entries SET use_count=use_count+1,last_used_at=? WHERE id=?", (utc_now(), entry_id)
            )

    def rebuild_search_index(self) -> None:
        with self.transaction() as cx:
            cx.execute("DELETE FROM entries_fts")
            for row in cx.execute("SELECT id FROM entries").fetchall():
                self._reindex(cx, row["id"])

    def checkpoint(self) -> None:
        self.conn.execute("PRAGMA wal_checkpoint(FULL)")
