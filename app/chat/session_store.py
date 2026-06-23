"""SQLite-backed storage for chat sessions and messages.

Reuses the same ``memory.db`` as the rest of the system so chat history is
persisted across restarts, alongside the episodic / persona tables.
"""

from __future__ import annotations

import sqlite3
import threading
import time

from app.config import settings
from app.schemas import ChatMessage, ChatSession, SessionSummary


class SessionStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(settings.sqlite_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS chat_sessions (
                id TEXT PRIMARY KEY,
                person TEXT,
                title TEXT NOT NULL,
                state TEXT NOT NULL,
                created_at REAL NOT NULL,
                last_active REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS chat_messages (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_msg_session ON chat_messages(session_id);
            """
        )
        self._conn.commit()

    # --------------------------------------------------------------- sessions
    def create(self) -> ChatSession:
        with self._lock:
            session = ChatSession()
            self._conn.execute(
                "INSERT INTO chat_sessions (id, person, title, state, created_at, last_active)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    session.id,
                    session.person,
                    session.title,
                    session.state,
                    session.created_at,
                    session.last_active,
                ),
            )
            self._conn.commit()
            return session

    def get(self, session_id: str) -> ChatSession | None:
        row = self._conn.execute(
            "SELECT * FROM chat_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        return self._row_to_session(row) if row else None

    @staticmethod
    def _row_to_session(row: sqlite3.Row) -> ChatSession:
        return ChatSession(
            id=row["id"],
            person=row["person"],
            title=row["title"],
            state=row["state"],
            created_at=row["created_at"],
            last_active=row["last_active"],
        )

    def bind_person(self, session_id: str, name: str) -> None:
        with self._lock:
            title = name or "新会话"
            self._conn.execute(
                "UPDATE chat_sessions SET person = ?, title = ?, state = 'active',"
                " last_active = ? WHERE id = ?",
                (name, title, time.time(), session_id),
            )
            self._conn.commit()

    def touch(self, session_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE chat_sessions SET last_active = ? WHERE id = ?",
                (time.time(), session_id),
            )
            self._conn.commit()

    def delete(self, session_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))
            self._conn.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
            self._conn.commit()

    def list(self) -> list[SessionSummary]:
        rows = self._conn.execute(
            "SELECT * FROM chat_sessions ORDER BY last_active DESC"
        ).fetchall()
        out: list[SessionSummary] = []
        for row in rows:
            last = self._conn.execute(
                "SELECT content FROM chat_messages WHERE session_id = ?"
                " ORDER BY created_at DESC LIMIT 1",
                (row["id"],),
            ).fetchone()
            out.append(
                SessionSummary(
                    id=row["id"],
                    person=row["person"],
                    title=row["title"],
                    state=row["state"],
                    last_active=row["last_active"],
                    last_message=(last["content"][:60] if last else ""),
                )
            )
        return out

    # --------------------------------------------------------------- messages
    def add_message(self, session_id: str, role: str, content: str) -> ChatMessage:
        with self._lock:
            msg = ChatMessage(session_id=session_id, role=role, content=content)
            self._conn.execute(
                "INSERT INTO chat_messages (id, session_id, role, content, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (msg.id, msg.session_id, msg.role, msg.content, msg.created_at),
            )
            self._conn.commit()
            self.touch(session_id)
            return msg

    def messages(self, session_id: str, limit: int | None = None) -> list[ChatMessage]:
        sql = "SELECT * FROM chat_messages WHERE session_id = ? ORDER BY created_at ASC"
        rows = self._conn.execute(sql, (session_id,)).fetchall()
        msgs = [
            ChatMessage(
                id=r["id"],
                session_id=r["session_id"],
                role=r["role"],
                content=r["content"],
                created_at=r["created_at"],
            )
            for r in rows
        ]
        if limit is not None:
            return msgs[-limit:]
        return msgs
