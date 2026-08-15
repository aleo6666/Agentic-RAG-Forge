"""SQLite-backed conversation session store.

Multi-turn chat memory for the agentic RAG engine (smart customer service,
step 1). Zero new dependencies — stdlib ``sqlite3`` only. The database lives at
``data/sessions.db`` (project root) by default, overridable via the
``RAGFORGE_SESSION_DB`` environment variable.

Thread-safety: a fresh connection is opened per operation (single-process
FastAPI, < 1000 req/s — no connection pooling needed).
"""

from __future__ import annotations

import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id         TEXT PRIMARY KEY,
    tenant_id  TEXT NOT NULL DEFAULT 'default',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role       TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content    TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);

CREATE TABLE IF NOT EXISTS missed_questions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    question   TEXT NOT NULL,
    tenant_id  TEXT NOT NULL DEFAULT 'default',
    created_at TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'new'
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_missed_session_question
    ON missed_questions(session_id, question);
CREATE INDEX IF NOT EXISTS idx_missed_tenant_created
    ON missed_questions(tenant_id, created_at DESC);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_db_path() -> Path:
    override = os.getenv("RAGFORGE_SESSION_DB")
    if override:
        return Path(override)
    # src/ragforge/session/session_store.py → parents[3] == project root
    return Path(__file__).resolve().parents[3] / "data" / "sessions.db"


class SessionStore:
    """Conversation session storage.

    Sessions are tenant-scoped; messages carry a role (``user``/``assistant``)
    and are ordered by insertion. ``recent_messages`` returns the most recent N
    messages in chronological order for prompt injection.
    """

    def __init__(self, db_path: str | os.PathLike | None = None):
        self.db_path = str(db_path) if db_path else str(_default_db_path())
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _db(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._db() as conn:
            conn.executescript(_SCHEMA)

    # ── Sessions ───────────────────────────────────────────────

    def create_session(self, tenant_id: str = "default") -> str:
        session_id = uuid.uuid4().hex
        with self._db() as conn:
            conn.execute(
                "INSERT INTO sessions (id, tenant_id, created_at) VALUES (?, ?, ?)",
                (session_id, tenant_id, _now()),
            )
        return session_id

    def session_exists(self, session_id: str) -> bool:
        with self._db() as conn:
            row = conn.execute(
                "SELECT 1 FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
        return row is not None

    def list_sessions(self, tenant_id: str | None = None) -> list[dict]:
        """List sessions (optionally filtered by tenant), newest first."""
        where = "" if tenant_id is None else "WHERE s.tenant_id = ?"
        params = () if tenant_id is None else (tenant_id,)
        sql = f"""
            SELECT s.id, s.tenant_id, s.created_at, COUNT(m.id) AS message_count
            FROM sessions s
            LEFT JOIN messages m ON m.session_id = s.id
            {where}
            GROUP BY s.id
            ORDER BY s.created_at DESC
        """
        with self._db() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    # ── Messages ───────────────────────────────────────────────

    def append_message(self, session_id: str, role: str, content: str) -> int:
        if role not in ("user", "assistant"):
            raise ValueError(f"role must be 'user' or 'assistant', got {role!r}")
        with self._db() as conn:
            cur = conn.execute(
                "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                (session_id, role, content, _now()),
            )
        return cur.lastrowid

    def recent_messages(self, session_id: str, limit: int = 8) -> list[dict]:
        """Return the most recent ``limit`` messages in chronological order."""
        with self._db() as conn:
            rows = conn.execute(
                "SELECT role, content, created_at FROM messages "
                "WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        rows = list(reversed(rows))
        return [
            {"role": r["role"], "content": r["content"], "created_at": r["created_at"]}
            for r in rows
        ]

    def round_count(self, session_id: str) -> int:
        """Number of completed user turns (each user message starts a round)."""
        with self._db() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE session_id = ? AND role = 'user'",
                (session_id,),
            ).fetchone()
        return row[0]

    # ── Missed questions ───────────────────────────────────────

    def record_missed_question(
        self, session_id: str, question: str, tenant_id: str = "default"
    ) -> bool:
        """Record a question the agent could not answer.

        Deduplicated by (session_id, question) — the same question asked again
        in the same session is not re-recorded. Returns True if newly inserted,
        False if it was a duplicate.
        """
        with self._db() as conn:
            cur = conn.execute(
                "INSERT OR IGNORE INTO missed_questions "
                "(session_id, question, tenant_id, created_at, status) "
                "VALUES (?, ?, ?, ?, 'new')",
                (session_id, question, tenant_id, _now()),
            )
        return cur.rowcount > 0

    def list_missed_questions(
        self, tenant_id: str | None = None, status: str | None = None
    ) -> list[dict]:
        """List missed questions, newest first, optionally filtered by tenant/status."""
        where, params = [], []
        if tenant_id is not None:
            where.append("tenant_id = ?")
            params.append(tenant_id)
        if status is not None:
            where.append("status = ?")
            params.append(status)
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        sql = (
            "SELECT id, session_id, question, tenant_id, created_at, status "
            f"FROM missed_questions {clause} ORDER BY created_at DESC"
        )
        with self._db() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
