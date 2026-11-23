"""收藏问答的数据层。

与会话/泡泡/讨论一样按 `user_id` 隔离；问答本身也是用户私有数据。
表结构独立于 `store.py`，避免把通用存储类继续撑大。
"""

from __future__ import annotations

import sqlite3
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class QASessionNotFound(Exception):
    """会话不存在，或不属于当前用户。"""


class QAStore:
    def __init__(self, database_path: str) -> None:
        self.database_path = database_path
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.database_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            yield conn
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS qa_sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    favlist_url_token INTEGER NOT NULL,
                    favlist_title TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    -- 一个用户在一个收藏夹下先只保留一个会话；后续要多会话再改唯一约束。
                    UNIQUE (user_id, favlist_url_token)
                );
                CREATE INDEX IF NOT EXISTS idx_qa_sessions_user
                    ON qa_sessions(user_id, updated_at DESC);

                CREATE TABLE IF NOT EXISTS qa_messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES qa_sessions(id) ON DELETE CASCADE,
                    role TEXT NOT NULL,
                    body TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    -- 同一秒内按插入顺序稳定读取。
                    seq INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_qa_messages_session
                    ON qa_messages(session_id, seq);

                CREATE TABLE IF NOT EXISTS qa_citations (
                    id TEXT PRIMARY KEY,
                    message_id TEXT NOT NULL REFERENCES qa_messages(id) ON DELETE CASCADE,
                    source_url TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    author_name TEXT NOT NULL DEFAULT '',
                    snippet TEXT NOT NULL DEFAULT '',
                    content_type TEXT NOT NULL DEFAULT '',
                    rank INTEGER NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_qa_citations_message
                    ON qa_citations(message_id, rank);
                """
            )

    @staticmethod
    def _session_row(row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "favlist_url_token": row["favlist_url_token"],
            "favlist_title": row["favlist_title"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "message_count": row["message_count"],
        }

    @staticmethod
    def _message_row(row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "session_id": row["session_id"],
            "role": row["role"],
            "body": row["body"],
            "created_at": row["created_at"],
            "citations": [],
        }

    def create_or_get_session(
        self, user_id: str, favlist_url_token: int, favlist_title: str = ""
    ) -> tuple[dict, bool]:
        """按 (用户, 收藏夹) 取会话；没有就创建。返回 (会话, 是否新建)。"""
        now = int(time.time())
        with self._connection() as conn:
            row = conn.execute(
                """SELECT s.*, (SELECT COUNT(*) FROM qa_messages m
                    WHERE m.session_id = s.id) AS message_count
                FROM qa_sessions s
                WHERE s.user_id = ? AND s.favlist_url_token = ?""",
                (user_id, favlist_url_token),
            ).fetchone()
            if row is not None:
                if favlist_title.strip() and favlist_title.strip() != row["favlist_title"]:
                    conn.execute(
                        "UPDATE qa_sessions SET favlist_title = ? WHERE id = ?",
                        (favlist_title.strip(), row["id"]),
                    )
                    conn.commit()
                    row = conn.execute(
                        """SELECT s.*, (SELECT COUNT(*) FROM qa_messages m
                            WHERE m.session_id = s.id) AS message_count
                        FROM qa_sessions s WHERE s.id = ?""",
                        (row["id"],),
                    ).fetchone()
                return self._session_row(row), False

            session_id = uuid.uuid4().hex
            conn.execute(
                """INSERT INTO qa_sessions(
                    id, user_id, favlist_url_token, favlist_title, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    session_id,
                    user_id,
                    favlist_url_token,
                    favlist_title.strip(),
                    now,
                    now,
                ),
            )
            conn.commit()
        created = self.get_session(user_id, session_id)
        if created is None:  # pragma: no cover - 刚提交就读不到属于存储故障
            raise RuntimeError("问答会话创建后读取失败。")
        return created, True

    def get_session(self, user_id: str, session_id: str) -> dict | None:
        with self._connection() as conn:
            row = conn.execute(
                """SELECT s.*, (SELECT COUNT(*) FROM qa_messages m
                    WHERE m.session_id = s.id) AS message_count
                FROM qa_sessions s
                WHERE s.id = ? AND s.user_id = ?""",
                (session_id, user_id),
            ).fetchone()
        return self._session_row(row) if row else None

    def list_sessions(self, user_id: str, limit: int = 20, offset: int = 0) -> tuple[list[dict], int]:
        with self._connection() as conn:
            total = conn.execute(
                "SELECT COUNT(*) AS count FROM qa_sessions WHERE user_id = ?", (user_id,)
            ).fetchone()["count"]
            rows = conn.execute(
                """SELECT s.*, (SELECT COUNT(*) FROM qa_messages m
                    WHERE m.session_id = s.id) AS message_count
                FROM qa_sessions s
                WHERE s.user_id = ?
                ORDER BY s.updated_at DESC, rowid DESC
                LIMIT ? OFFSET ?""",
                (user_id, limit, offset),
            ).fetchall()
        return [self._session_row(row) for row in rows], int(total)

    def add_exchange(
        self,
        user_id: str,
        session_id: str,
        question: str,
        answer: str,
        citations: list[dict],
    ) -> tuple[dict, dict]:
        """把一轮问答（用户问题 + 助手回答 + 引用）放在同一个事务里落库。"""
        now = int(time.time())
        question_id = uuid.uuid4().hex
        answer_id = uuid.uuid4().hex
        with self._connection() as conn:
            session = conn.execute(
                "SELECT id FROM qa_sessions WHERE id = ? AND user_id = ?",
                (session_id, user_id),
            ).fetchone()
            if session is None:
                raise QASessionNotFound("问答会话不存在或不属于当前用户。")

            next_seq = int(
                conn.execute(
                    "SELECT COALESCE(MAX(seq), 0) FROM qa_messages WHERE session_id = ?",
                    (session_id,),
                ).fetchone()[0]
            )
            conn.execute(
                """INSERT INTO qa_messages(id, session_id, role, body, created_at, seq)
                VALUES (?, ?, 'user', ?, ?, ?)""",
                (question_id, session_id, question, now, next_seq + 1),
            )
            conn.execute(
                """INSERT INTO qa_messages(id, session_id, role, body, created_at, seq)
                VALUES (?, ?, 'assistant', ?, ?, ?)""",
                (answer_id, session_id, answer, now, next_seq + 2),
            )
            for rank, item in enumerate(citations, start=1):
                conn.execute(
                    """INSERT INTO qa_citations(
                        id, message_id, source_url, title, author_name,
                        snippet, content_type, rank, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        uuid.uuid4().hex,
                        answer_id,
                        item.get("source_url", ""),
                        item.get("title", ""),
                        item.get("author_name", ""),
                        item.get("snippet", ""),
                        item.get("content_type", ""),
                        rank,
                        now,
                    ),
                )
            conn.execute(
                "UPDATE qa_sessions SET updated_at = ? WHERE id = ?", (now, session_id)
            )
            conn.commit()
        return (
            self.get_message(user_id, session_id, question_id),
            self.get_message(user_id, session_id, answer_id),
        )

    def _citations_for(self, conn: sqlite3.Connection, message_id: str) -> list[dict]:
        rows = conn.execute(
            """SELECT source_url, title, author_name, snippet, content_type, rank
            FROM qa_citations WHERE message_id = ? ORDER BY rank ASC""",
            (message_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_message(self, user_id: str, session_id: str, message_id: str) -> dict:
        with self._connection() as conn:
            row = conn.execute(
                """SELECT m.* FROM qa_messages m
                JOIN qa_sessions s ON s.id = m.session_id
                WHERE m.id = ? AND m.session_id = ? AND s.user_id = ?""",
                (message_id, session_id, user_id),
            ).fetchone()
            if row is None:
                raise QASessionNotFound("消息不存在或不属于当前用户。")
            message = self._message_row(row)
            message["citations"] = self._citations_for(conn, message_id)
        return message

    def get_messages(self, user_id: str, session_id: str) -> list[dict]:
        with self._connection() as conn:
            session = conn.execute(
                "SELECT id FROM qa_sessions WHERE id = ? AND user_id = ?",
                (session_id, user_id),
            ).fetchone()
            if session is None:
                raise QASessionNotFound("问答会话不存在或不属于当前用户。")
            rows = conn.execute(
                "SELECT * FROM qa_messages WHERE session_id = ? ORDER BY seq ASC",
                (session_id,),
            ).fetchall()
            messages = []
            for row in rows:
                message = self._message_row(row)
                message["citations"] = self._citations_for(conn, row["id"])
                messages.append(message)
        return messages
