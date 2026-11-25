from __future__ import annotations

import base64
import hashlib
import json
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from collections.abc import Iterator
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from .content import SourceInfo


SESSION_TTL = 30 * 24 * 3600
EXTENSION_TTL = 90 * 24 * 3600
OAUTH_TX_TTL = 10 * 60
PAIR_CODE_TTL = 5 * 60


class Store:
    def __init__(self, database_path: str, secret_key: str) -> None:
        self.database_path = database_path
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(secret_key.encode("utf-8")).digest()
        self.cipher = Fernet(base64.urlsafe_b64encode(digest))
        self._init_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.database_path, timeout=10)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    oauth_token_encrypted TEXT,
                    oauth_expires_at INTEGER,
                    is_demo INTEGER NOT NULL DEFAULT 0,
                    expires_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS oauth_transactions (
                    id_hash TEXT PRIMARY KEY,
                    state_hash TEXT NOT NULL,
                    user_id TEXT,
                    expires_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS profiles (
                    user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                    zhihu_uid TEXT NOT NULL,
                    hash_id TEXT NOT NULL DEFAULT '',
                    fullname TEXT NOT NULL DEFAULT '',
                    headline TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    avatar_path TEXT NOT NULL DEFAULT '',
                    zhihu_url TEXT NOT NULL DEFAULT '',
                    updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS pair_codes (
                    code_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    expires_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS extension_tokens (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    expires_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS articles (
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    article_key TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    content_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    author_name TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    PRIMARY KEY (user_id, article_key)
                );
                CREATE TABLE IF NOT EXISTS bubbles (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    article_key TEXT NOT NULL,
                    body TEXT NOT NULL,
                    quote TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    FOREIGN KEY (user_id, article_key)
                        REFERENCES articles(user_id, article_key) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_bubbles_user_article
                    ON bubbles(user_id, article_key, created_at DESC);
                CREATE TABLE IF NOT EXISTS thoughts (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    request_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    source_title TEXT NOT NULL,
                    quote TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    parent_ids TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    UNIQUE(user_id, request_id)
                );
                CREATE INDEX IF NOT EXISTS idx_thoughts_user ON thoughts(user_id, created_at DESC);
                CREATE VIEW IF NOT EXISTS thought_library AS
                    SELECT id, user_id, title, body, '' AS article_key, source_url, source_title,
                        quote, kind, parent_ids, created_at
                    FROM thoughts
                    UNION ALL
                    SELECT b.id, b.user_id, substr(trim(b.body), 1, 60), b.body, b.article_key,
                        a.source_url, a.title, b.quote, 'reading', '[]', b.created_at
                    FROM bubbles b JOIN articles a
                        ON a.user_id = b.user_id AND a.article_key = b.article_key;
                """
            )

    @staticmethod
    def _hash(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def _new_user(self, conn: sqlite3.Connection) -> str:
        user_id = uuid.uuid4().hex
        conn.execute("INSERT INTO users(id, created_at) VALUES (?, ?)", (user_id, int(time.time())))
        return user_id

    def _insert_session(
        self, conn: sqlite3.Connection, user_id: str | None,
        oauth_token: str | None, oauth_expires_at: int | None, demo: bool,
    ) -> tuple[str, str]:
        raw_token = secrets.token_urlsafe(32)
        encrypted = self.cipher.encrypt(oauth_token.encode("utf-8")).decode("ascii") if oauth_token else None
        if not user_id or not conn.execute("SELECT 1 FROM users WHERE id = ?", (user_id,)).fetchone():
            user_id = self._new_user(conn)
        conn.execute(
            """INSERT INTO sessions(
                token_hash, user_id, oauth_token_encrypted, oauth_expires_at, is_demo, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?)""",
            (self._hash(raw_token), user_id, encrypted, oauth_expires_at, int(demo), int(time.time()) + SESSION_TTL),
        )
        return raw_token, user_id

    def create_session(
        self, user_id: str | None = None, oauth_token: str | None = None,
        oauth_expires_at: int | None = None, demo: bool = False,
    ) -> tuple[str, str]:
        with self._connect() as conn:
            return self._insert_session(conn, user_id, oauth_token, oauth_expires_at, demo)

    def create_zhihu_session(
        self, profile: dict, oauth_token: str, oauth_expires_at: int,
        candidate_user_id: str | None = None,
    ) -> tuple[str, str]:
        """Resolve verified provider identity atomically; never reassign another account's data."""
        uid = str(profile.get("uid") or "").strip()
        if not uid:
            raise ValueError("知乎用户标识不能为空。")
        with self._connect() as conn:
            # Serialize lookup + creation even when two browsers finish OAuth together.
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                """SELECT p.user_id FROM profiles p JOIN users u ON u.id = p.user_id
                   WHERE p.zhihu_uid = ? ORDER BY u.created_at, p.user_id LIMIT 1""", (uid,),
            ).fetchone()
            user_id = existing["user_id"] if existing else None
            if not user_id and candidate_user_id:
                candidate = conn.execute(
                    "SELECT p.zhihu_uid FROM users u LEFT JOIN profiles p ON p.user_id = u.id WHERE u.id = ?",
                    (candidate_user_id,),
                ).fetchone()
                # An unbound demo user can attach once; an existing provider account cannot change UID.
                if candidate and candidate["zhihu_uid"] in (None, uid):
                    user_id = candidate_user_id
            raw_token, user_id = self._insert_session(conn, user_id, oauth_token, oauth_expires_at, False)
            self._save_profile(conn, user_id, {**profile, "uid": uid})
            return raw_token, user_id

    def get_session(self, raw_token: str) -> dict | None:
        if not raw_token:
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE token_hash = ?", (self._hash(raw_token),)
            ).fetchone()
            if not row or row["expires_at"] <= int(time.time()):
                return None
        result = dict(row)
        result["is_demo"] = bool(result["is_demo"])
        encrypted = result.pop("oauth_token_encrypted")
        try:
            result["oauth_token"] = self.cipher.decrypt(encrypted.encode("ascii")).decode("utf-8") if encrypted else None
        except InvalidToken:
            result["oauth_token"] = None
        return result

    def delete_session(self, raw_token: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (self._hash(raw_token),))

    def create_oauth_transaction(self, user_id: str | None) -> tuple[str, str]:
        transaction_id = secrets.token_urlsafe(32)
        state = secrets.token_urlsafe(24)
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM oauth_transactions WHERE expires_at <= ?", (int(time.time()),)
            )
            conn.execute(
                "INSERT INTO oauth_transactions(id_hash, state_hash, user_id, expires_at) VALUES (?, ?, ?, ?)",
                (self._hash(transaction_id), self._hash(state), user_id, int(time.time()) + OAUTH_TX_TTL),
            )
        return transaction_id, state

    def consume_oauth_transaction(self, transaction_id: str, returned_state: str | None) -> str | None:
        now = int(time.time())
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM oauth_transactions WHERE id_hash = ?", (self._hash(transaction_id),)
            ).fetchone()
            conn.execute(
                "DELETE FROM oauth_transactions WHERE id_hash = ?", (self._hash(transaction_id),)
            )
        if not row or row["expires_at"] <= now:
            raise ValueError("授权请求已过期，请重新发起知乎登录。")
        if returned_state and not secrets.compare_digest(row["state_hash"], self._hash(returned_state)):
            raise ValueError("授权回调校验失败，请重新发起知乎登录。")
        return row["user_id"]

    def save_profile(self, user_id: str, profile: dict) -> None:
        """Update metadata without allowing a local user to change provider identity."""
        with self._connect() as conn:
            previous = conn.execute("SELECT zhihu_uid FROM profiles WHERE user_id = ?", (user_id,)).fetchone()
            if previous and previous["zhihu_uid"] != str(profile.get("uid", "")):
                raise ValueError("不能覆盖已绑定的知乎账号。")
            self._save_profile(conn, user_id, profile)

    def _save_profile(self, conn: sqlite3.Connection, user_id: str, profile: dict) -> None:
        conn.execute(
            """INSERT INTO profiles(
                user_id, zhihu_uid, hash_id, fullname, headline,
                description, avatar_path, zhihu_url, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                zhihu_uid = excluded.zhihu_uid,
                hash_id = excluded.hash_id,
                fullname = excluded.fullname,
                headline = excluded.headline,
                description = excluded.description,
                avatar_path = excluded.avatar_path,
                zhihu_url = excluded.zhihu_url,
                updated_at = excluded.updated_at""",
            (
                user_id,
                str(profile.get("uid", "")),
                str(profile.get("hash_id", "")),
                str(profile.get("fullname", "")),
                str(profile.get("headline", "")),
                str(profile.get("description", "")),
                str(profile.get("avatar_path", "")),
                str(profile.get("url", "")),
                int(time.time()),
            ),
        )

    def get_profile(self, user_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM profiles WHERE user_id = ?", (user_id,)
            ).fetchone()
        if not row:
            return None
        return {
            "uid": row["zhihu_uid"],
            "hash_id": row["hash_id"],
            "fullname": row["fullname"],
            "headline": row["headline"],
            "description": row["description"],
            "avatar_path": row["avatar_path"],
            "url": row["zhihu_url"],
        }

    def create_pair_code(self, user_id: str) -> str:
        code = secrets.token_urlsafe(24)
        with self._connect() as conn:
            conn.execute("DELETE FROM pair_codes WHERE expires_at <= ?", (int(time.time()),))
            conn.execute(
                "INSERT INTO pair_codes(code_hash, user_id, expires_at) VALUES (?, ?, ?)",
                (self._hash(code), user_id, int(time.time()) + PAIR_CODE_TTL),
            )
        return code

    def exchange_pair_code(self, code: str) -> tuple[str, str] | None:
        now = int(time.time())
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM pair_codes WHERE code_hash = ?", (self._hash(code.strip()),)
            ).fetchone()
            conn.execute("DELETE FROM pair_codes WHERE code_hash = ?", (self._hash(code.strip()),))
            if not row or row["expires_at"] <= now:
                return None
            raw_token = secrets.token_urlsafe(32)
            conn.execute(
                "INSERT INTO extension_tokens(token_hash, user_id, expires_at) VALUES (?, ?, ?)",
                (self._hash(raw_token), row["user_id"], now + EXTENSION_TTL),
            )
        return raw_token, row["user_id"]

    def get_extension_user(self, raw_token: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT user_id, expires_at FROM extension_tokens WHERE token_hash = ?",
                (self._hash(raw_token),),
            ).fetchone()
        if not row or row["expires_at"] <= int(time.time()):
            return None
        return row["user_id"]

    def create_bubble(
        self,
        user_id: str,
        source: SourceInfo,
        title: str,
        author_name: str,
        body: str,
        quote: str,
    ) -> dict:
        now = int(time.time())
        bubble_id = uuid.uuid4().hex
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO articles(
                    user_id, article_key, source_url, content_type, content_id,
                    title, author_name, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, article_key) DO UPDATE SET
                    source_url = excluded.source_url,
                    title = CASE WHEN excluded.title <> '' THEN excluded.title ELSE articles.title END,
                    author_name = CASE WHEN excluded.author_name <> '' THEN excluded.author_name ELSE articles.author_name END,
                    updated_at = excluded.updated_at""",
                (
                    user_id,
                    source.article_key,
                    source.source_url,
                    source.content_type,
                    source.content_id,
                    title.strip(),
                    author_name.strip(),
                    now,
                    now,
                ),
            )
            conn.execute(
                "INSERT INTO bubbles(id, user_id, article_key, body, quote, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (bubble_id, user_id, source.article_key, body.strip(), quote.strip(), now),
            )
        return self.get_bubble(user_id, bubble_id)  # type: ignore[return-value]

    @staticmethod
    def _bubble(row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "article_key": row["article_key"],
            "source_url": row["source_url"],
            "content_type": row["content_type"],
            "content_id": row["content_id"],
            "title": row["title"],
            "author_name": row["author_name"],
            "body": row["body"],
            "quote": row["quote"],
            "created_at": row["created_at"],
        }

    def get_bubble(self, user_id: str, bubble_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                """SELECT b.*, a.source_url, a.content_type, a.content_id, a.title, a.author_name
                FROM bubbles b JOIN articles a ON a.user_id = b.user_id AND a.article_key = b.article_key
                WHERE b.user_id = ? AND b.id = ?""",
                (user_id, bubble_id),
            ).fetchone()
        return self._bubble(row) if row else None

    def list_bubbles(self, user_id: str, article_key: str | None = None) -> list[dict]:
        sql = """SELECT b.*, a.source_url, a.content_type, a.content_id, a.title, a.author_name
            FROM bubbles b JOIN articles a ON a.user_id = b.user_id AND a.article_key = b.article_key
            WHERE b.user_id = ?"""
        params: list[str] = [user_id]
        if article_key:
            sql += " AND b.article_key = ?"
            params.append(article_key)
        sql += " ORDER BY b.created_at DESC"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._bubble(row) for row in rows]

    @staticmethod
    def _thought(row: sqlite3.Row) -> dict:
        result = dict(row)
        result.pop("user_id")
        result["parent_ids"] = json.loads(result["parent_ids"])
        return result

    def list_thoughts(self, user_id: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM thought_library WHERE user_id = ? ORDER BY created_at DESC, id DESC",
                (user_id,),
            ).fetchall()
        return [self._thought(row) for row in rows]

    def get_thought(self, user_id: str, thought_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM thought_library WHERE user_id = ? AND id = ?", (user_id, thought_id)
            ).fetchone()
        return self._thought(row) if row else None

    def create_thought(
        self,
        user_id: str,
        request_id: str,
        title: str,
        body: str,
        source_url: str,
        kind: str,
        parent_ids: list[str],
    ) -> dict | None:
        with self._connect() as conn:
            # Keep parent ownership checks and the new record in one write transaction.
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT id FROM thoughts WHERE user_id = ? AND request_id = ?", (user_id, request_id)
            ).fetchone()
            if existing:
                row = conn.execute(
                    "SELECT * FROM thought_library WHERE user_id = ? AND id = ?", (user_id, existing["id"])
                ).fetchone()
                return self._thought(row)

            parents = []
            for parent_id in parent_ids:
                parent = conn.execute(
                    "SELECT * FROM thought_library WHERE user_id = ? AND id = ?", (user_id, parent_id)
                ).fetchone()
                if parent is None:
                    return None
                parents.append(parent)
            source = next((parent for parent in parents if parent["source_url"]), None)
            thought_id = uuid.uuid4().hex
            conn.execute(
                """INSERT INTO thoughts(
                    id, user_id, request_id, title, body, source_url, source_title, quote,
                    kind, parent_ids, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    thought_id, user_id, request_id, title, body,
                    source["source_url"] if source else source_url,
                    source["source_title"] if source else "",
                    source["quote"] if source else "",
                    kind, json.dumps(parent_ids), int(time.time()),
                ),
            )
            row = conn.execute(
                "SELECT * FROM thought_library WHERE user_id = ? AND id = ?", (user_id, thought_id)
            ).fetchone()
            return self._thought(row)

    def list_articles(self, user_id: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT a.*, COUNT(b.id) AS bubble_count, MAX(b.created_at) AS last_bubble_at
                FROM articles a LEFT JOIN bubbles b
                    ON b.user_id = a.user_id AND b.article_key = a.article_key
                WHERE a.user_id = ?
                GROUP BY a.user_id, a.article_key
                -- 历史数据里可能已经有 0 条泡泡的孤儿文章；列表层再挡一道，
                -- 避免用户升级后仍然看到删不掉的行。新数据由 delete_bubble 清理。
                HAVING COUNT(b.id) > 0
                ORDER BY last_bubble_at DESC""",
                (user_id,),
            ).fetchall()
        return [
            {
                "article_key": row["article_key"],
                "source_url": row["source_url"],
                "content_type": row["content_type"],
                "content_id": row["content_id"],
                "title": row["title"],
                "author_name": row["author_name"],
                "bubble_count": row["bubble_count"],
                "last_bubble_at": row["last_bubble_at"],
            }
            for row in rows
        ]

    def delete_bubble(self, user_id: str, bubble_id: str) -> bool:
        """删除泡泡；如果这是该文章的最后一条，连带删除文章记录。

        `articles` 只是泡泡的分组，没有独立内容。只删泡泡会留下
        `bubble_count = 0` 的孤儿文章，前端“有泡泡的文章”就会出现
        删不掉的行。两步放在同一个连接里，避免删完泡泡后文章删除失败。
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT article_key FROM bubbles WHERE user_id = ? AND id = ?",
                (user_id, bubble_id),
            ).fetchone()
            if row is None:
                return False
            article_key = row["article_key"]
            deleted = conn.execute(
                "DELETE FROM bubbles WHERE user_id = ? AND id = ?",
                (user_id, bubble_id),
            )
            if deleted.rowcount == 0:
                return False
            remaining = conn.execute(
                "SELECT COUNT(*) AS count FROM bubbles WHERE user_id = ? AND article_key = ?",
                (user_id, article_key),
            ).fetchone()["count"]
            if remaining == 0:
                conn.execute(
                    "DELETE FROM articles WHERE user_id = ? AND article_key = ?",
                    (user_id, article_key),
                )
            return True
