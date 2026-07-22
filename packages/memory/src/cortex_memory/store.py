"""SQLite knowledge store — MVP bridge for vault migration.

Schema mirrors roxabi-vault entries (namespace/category/type/title/content)
so a one-shot import is straightforward. FTS5 for search; assemble is a
simple recent+keyword pack until the full graph lands.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    namespace TEXT NOT NULL DEFAULT 'vault',
    category TEXT NOT NULL,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_entries_ns ON entries(namespace);
CREATE INDEX IF NOT EXISTS idx_entries_cat ON entries(category);
CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(
    title, content, category, type
);
"""

_TOKEN_RE = re.compile(r"\S+")


def estimate_tokens(text: str) -> int:
    """Rough token estimate (~1.3 words/token heuristic inverted)."""
    words = len(_TOKEN_RE.findall(text))
    return max(1, int(words * 1.3)) if text.strip() else 0


@dataclass(frozen=True, slots=True)
class Entry:
    id: int
    namespace: str
    category: str
    type: str
    title: str
    content: str
    metadata: dict[str, Any]
    created_at: str


class MemoryStore:
    """Sync SQLite store (single-writer MVP)."""

    def __init__(self, db_path: Path | str) -> None:
        self._path = Path(db_path)
        if str(self._path) != ":memory:":
            self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def capture(
        self,
        *,
        title: str,
        body: str,
        category: str,
        entry_type: str,
        namespace: str,
        url: str = "",
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        meta = dict(metadata or {})
        if url:
            meta.setdefault("url", url)
        if tags:
            meta.setdefault("tags", tags)
        cur = self._conn.execute(
            """
            INSERT INTO entries (namespace, category, type, title, content, metadata)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (namespace, category, entry_type, title, body, json.dumps(meta)),
        )
        if cur.lastrowid is None:
            raise RuntimeError("INSERT entries returned no lastrowid")
        entry_id = int(cur.lastrowid)
        # FTS content=external needs explicit insert when using content= table
        # with triggers not defined — rebuild row into fts.
        self._conn.execute(
            """
            INSERT INTO entries_fts(rowid, title, content, category, type)
            VALUES (?, ?, ?, ?, ?)
            """,
            (entry_id, title, body, category, entry_type),
        )
        self._conn.commit()
        return entry_id

    def search(
        self,
        query: str,
        *,
        namespace: str | None = None,
        category: str | None = None,
        limit: int = 20,
    ) -> list[Entry]:
        # Escape FTS special chars lightly — quote as phrase if spaces.
        fts_q = query.strip()
        if not fts_q:
            return []
        # Prefer MATCH; fall back to LIKE if FTS syntax fails.
        try:
            sql = """
                SELECT e.* FROM entries e
                JOIN entries_fts f ON f.rowid = e.id
                WHERE f.entries_fts MATCH ?
            """
            params: list[Any] = [fts_q]
            if namespace:
                sql += " AND e.namespace = ?"
                params.append(namespace)
            if category:
                sql += " AND e.category = ?"
                params.append(category)
            sql += " ORDER BY e.id DESC LIMIT ?"
            params.append(limit)
            rows = self._conn.execute(sql, params).fetchall()
        except sqlite3.OperationalError:
            like = f"%{query}%"
            sql = """
                SELECT * FROM entries
                WHERE (title LIKE ? OR content LIKE ?)
            """
            params = [like, like]
            if namespace:
                sql += " AND namespace = ?"
                params.append(namespace)
            if category:
                sql += " AND category = ?"
                params.append(category)
            sql += " ORDER BY id DESC LIMIT ?"
            params.append(limit)
            rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def assemble(
        self,
        *,
        goal: str | None,
        budget_tokens: int,
        namespace: str | None,
        fresh_tail_days: int,
    ) -> tuple[list[Entry], str, int]:
        """Return (entries, joined_text, tokens_used) within budget."""
        params: list[Any] = []
        sql = "SELECT * FROM entries WHERE 1=1"
        if namespace:
            sql += " AND namespace = ?"
            params.append(namespace)
        if fresh_tail_days > 0:
            sql += " AND created_at >= datetime('now', ?)"
            params.append(f"-{fresh_tail_days} days")
        sql += " ORDER BY id DESC LIMIT 200"
        rows = [self._row_to_entry(r) for r in self._conn.execute(sql, params).fetchall()]

        if goal:
            goal_hits = self.search(goal, namespace=namespace, limit=30)
            # Boost goal hits to front, dedupe by id.
            seen = {e.id for e in goal_hits}
            rows = goal_hits + [e for e in rows if e.id not in seen]

        picked: list[Entry] = []
        tokens = 0
        parts: list[str] = []
        for entry in rows:
            block = f"### {entry.title}\n{entry.content}"
            cost = estimate_tokens(block)
            if tokens + cost > budget_tokens and picked:
                break
            if tokens + cost > budget_tokens and not picked:
                # Always include at least a truncated first item.
                block = block[: max(64, budget_tokens * 4)]
                cost = estimate_tokens(block)
            picked.append(entry)
            parts.append(block)
            tokens += cost
            if tokens >= budget_tokens:
                break
        return picked, "\n\n".join(parts), tokens

    def count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS n FROM entries").fetchone()
        return int(row["n"]) if row else 0

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> Entry:
        meta_raw = row["metadata"]
        try:
            meta = json.loads(meta_raw) if meta_raw else {}
        except json.JSONDecodeError:
            meta = {}
        if not isinstance(meta, dict):
            meta = {}
        return Entry(
            id=int(row["id"]),
            namespace=str(row["namespace"]),
            category=str(row["category"]),
            type=str(row["type"]),
            title=str(row["title"]),
            content=str(row["content"]),
            metadata=meta,
            created_at=str(row["created_at"]),
        )
