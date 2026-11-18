"""讨论室数据层。

讨论、座位、消息、事件四张表由本模块自己维护，不塞进 `store.py` 的通用存储类：
两者通过 `discussions.user_id` 关联同一批用户，但表结构和读写逻辑互不干扰。

设计取舍：
- **事件单独成表**，而不是“拿消息表当状态源”。暂停、恢复、停止、结束这些变化
  不属于任何一条消息，必须有自己的记录位置；`seq` 由 `discussions.event_seq`
  在写事务内分配，天然单调。
- **消息序号与事件序号分离**：消息 `seq` 表示“这是第几句话”，用于稳定排序和分页；
  事件 `seq` 表示“第几次变化”，用于断线补发。两者数值不相等，不能混用。
- **消息落库即定型**：本模块不参与生成过程，没有中间状态，也不提供修改入口。
- **状态流转集中在 `_transition`**，避免四个端点各写一份判断。
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
import weakref
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

# 与 packages/debate-room/engine.mjs 的 roles 一一对应，前端无需再定义一份。
ROLE_CATALOG: tuple[dict, ...] = (
    {"role_id": "explorer", "display_name": "探索者", "title": "寻找另一种可能"},
    {"role_id": "skeptic", "display_name": "质疑者", "title": "给观点一点阻力"},
    {"role_id": "weaver", "display_name": "归纳者", "title": "把线索连成观点"},
    {"role_id": "user", "display_name": "你", "title": "这张桌子的一员"},
)
DEFAULT_ROLE_IDS: tuple[str, ...] = tuple(item["role_id"] for item in ROLE_CATALOG)
ROLE_IDS = frozenset(item["role_id"] for item in ROLE_CATALOG)
USER_ROLE = "user"
# 单条消息的字符上限。HTTP 层用同一个常量做 pydantic 校验，避免两处数字各改各的。
MAX_MESSAGE_LENGTH = 4000

STATUS_ACTIVE = "active"
STATUS_PAUSED = "paused"
STATUS_STOPPED = "stopped"
STATUS_FINISHED = "finished"
# 可以发言、可以继续推进的状态。
OPEN_STATUSES = (STATUS_ACTIVE, STATUS_PAUSED)
# 终态：只读，不再接受消息，也不能恢复。
CLOSED_STATUSES = (STATUS_STOPPED, STATUS_FINISHED)

MESSAGE_COMPLETED = "completed"
MESSAGE_FAILED = "failed"
MESSAGE_CANCELLED = "cancelled"
# 本模块只保存**已经定型的消息**，不处理生成过程。
# 因此没有 streaming：一条消息落库时状态就定了，之后不会变。
FINAL_MESSAGE_STATUSES = (MESSAGE_COMPLETED, MESSAGE_FAILED, MESSAGE_CANCELLED)

EVENT_DISCUSSION_CREATED = "discussion.created"
EVENT_DISCUSSION_PAUSED = "discussion.paused"
EVENT_DISCUSSION_RESUMED = "discussion.resumed"
EVENT_DISCUSSION_STOPPED = "discussion.stopped"
EVENT_DISCUSSION_FINISHED = "discussion.finished"
# 只有一种消息事件：消息落库。状态（成功/失败/取消）在快照的 status 里，
# 不需要为它单独发事件，也就不存在"状态被改写"的问题。
EVENT_MESSAGE_CREATED = "message.created"

# 单条讨论的消息上限：防止误用或刷接口把 SQLite 撑到不可用。
MAX_MESSAGES_PER_DISCUSSION = int(os.environ.get("THINKSPACE_MAX_MESSAGES", "500"))

# 表结构版本号，写在 `PRAGMA user_version` 里，供启动时判断是否需要迁移。
# v2 → v3：事件表增加 payload 列，消息快照在事件里固化，不再回查消息表。
SCHEMA_VERSION = 3

# 状态时间戳列名白名单。用映射而不是 assert：assert 在 `python -O` 下会被移除，
# 那样拼进 SQL 的列名就失去了最后一道检查。
TIMESTAMP_COLUMNS = ("paused_at", "stopped_at", "finished_at")


class DiscussionNotFound(Exception):
    """讨论（或其中的消息）不存在，或当前用户无权访问。

    刻意不区分“没这条”和“不是你的”，避免通过错误信息探测他人数据。
    """


class DiscussionClosed(Exception):
    """讨论已进入终态，不再接受新消息。"""


class DiscussionStateError(Exception):
    """非法的状态流转，例如对已结束的讨论调用 pause。"""

    def __init__(self, current: str, action: str) -> None:
        super().__init__(f"讨论当前状态是 {current}，不能执行 {action}。")
        self.current = current
        self.action = action


class DiscussionQuotaExceeded(Exception):
    """单条讨论的消息数量超过上限。"""


class DiscussionStore:
    def __init__(self, database_path: str) -> None:
        self.database_path = database_path
        # 等待某个讨论有新事件的条件变量，让 SSE 在写入后立刻唤醒，而不是死等轮询间隔。
        # 用弱引用字典：没有订阅者等待时条目会被自动回收，不会随讨论数量无限增长。
        self._listeners: weakref.WeakValueDictionary[str, threading.Condition] = (
            weakref.WeakValueDictionary()
        )
        self._listeners_lock = threading.Lock()
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.database_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        # WAL：读不阻塞写，写不阻塞读。SSE 反复读事件时，用户仍能正常发言。
        conn.execute("PRAGMA journal_mode = WAL")
        # NORMAL 在 WAL 下已能保证崩溃一致性，比 FULL 少一次 fsync。
        conn.execute("PRAGMA synchronous = NORMAL")
        return conn

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        """用完必定关闭的连接，不管事务。

        `with sqlite3.connect(...) as conn` 只负责提交/回滚，**不会关闭连接**，
        依赖 GC 回收在 Windows 上会拖延文件句柄释放（测试里删临时库会失败）。
        读操作和建表都走这里；需要写锁的场景用 `_write()`。
        """
        conn = self._connect()
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def _read_snapshot(self) -> Iterator[sqlite3.Connection]:
        """在同一个读事务里跑多条查询，保证它们看到同一份快照。

        直接用 `_connection()` 时，两次查询之间可能插入新写入，
        会出现「返回了新消息，顶层水位却还是旧值」的撕裂。
        SQLite 的 DEFERRED 事务在第一次读时固定快照，正好解决这个问题。
        """
        conn = self._connect()
        conn.isolation_level = None
        try:
            conn.execute("BEGIN DEFERRED")
            yield conn
        finally:
            # 只读事务，提交或回滚都只是释放快照，不影响数据。
            try:
                conn.execute("COMMIT")
            except sqlite3.Error:
                pass
            conn.close()

    @contextmanager
    def _write(self) -> Iterator[sqlite3.Connection]:
        """写事务：拿到写锁、自动提交/回滚、必定关闭连接。

        所有写操作都必须走这里。手写 try/except/rollback 很容易漏掉某一步，
        上一版就因此出现过"恢复后暂停时间戳又被写回去"的错误。
        """
        conn = self._connect()
        conn.isolation_level = None
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.execute("COMMIT")
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        finally:
            conn.close()

    # ---------------- 事件通知 ----------------

    def _listener_for(self, discussion_id: str) -> threading.Condition:
        with self._listeners_lock:
            condition = self._listeners.get(discussion_id)
            if condition is None:
                condition = threading.Condition()
                self._listeners[discussion_id] = condition
            return condition

    def notify_change(self, discussion_id: str) -> None:
        """写入后唤醒等待该讨论的订阅者；多进程部署时不会跨进程，仍靠轮询兜底。"""
        condition = self._listener_for(discussion_id)
        with condition:
            condition.notify_all()

    def wait_for_change(self, discussion_id: str, timeout: float) -> None:
        """阻塞到有新事件或超时；超时用于兜底轮询与感知客户端断开。"""
        condition = self._listener_for(discussion_id)
        with condition:
            condition.wait(timeout)

    def _init_schema(self) -> None:
        with self._connection() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version == SCHEMA_VERSION:
                return
            if version > SCHEMA_VERSION:
                raise RuntimeError(
                    f"数据库表结构版本 {version} 高于当前代码支持的 {SCHEMA_VERSION}，"
                    "请更新代码后再启动。"
                )
            self._migrate_legacy_schema(conn)
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS discussions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    -- 预留给 A 模块的空间维度：现在恒为空，将来只需一条 UPDATE 补齐，不必改表。
                    space_id TEXT NOT NULL DEFAULT '',
                    topic TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    max_turns INTEGER NOT NULL DEFAULT 6,
                    turn_index INTEGER NOT NULL DEFAULT 0,
                    -- 消息序号水位：第几句话。
                    message_seq INTEGER NOT NULL DEFAULT 0,
                    -- 事件序号水位：第几次变化。与 message_seq 是两套独立计数。
                    event_seq INTEGER NOT NULL DEFAULT 0,
                    message_count INTEGER NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    paused_at INTEGER,
                    stopped_at INTEGER,
                    finished_at INTEGER
                );
                CREATE INDEX IF NOT EXISTS idx_discussions_user
                    ON discussions(user_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS discussion_participants (
                    discussion_id TEXT NOT NULL REFERENCES discussions(id) ON DELETE CASCADE,
                    role_id TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    seat INTEGER NOT NULL,
                    PRIMARY KEY (discussion_id, role_id)
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    discussion_id TEXT NOT NULL REFERENCES discussions(id) ON DELETE CASCADE,
                    seq INTEGER NOT NULL,
                    role_id TEXT NOT NULL,
                    body TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'completed',
                    client_msg_id TEXT,
                    -- 引用另一条消息；留空表示独立发言。
                    in_reply_to TEXT,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    UNIQUE (discussion_id, seq)
                );
                CREATE INDEX IF NOT EXISTS idx_messages_discussion
                    ON messages(discussion_id, seq);
                -- 只对带幂等键的消息建唯一索引；空值不参与，普通消息可以重复内容。
                CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_client
                    ON messages(discussion_id, client_msg_id)
                    WHERE client_msg_id IS NOT NULL;

                CREATE TABLE IF NOT EXISTS discussion_events (
                    discussion_id TEXT NOT NULL REFERENCES discussions(id) ON DELETE CASCADE,
                    -- 每条讨论内从 1 开始独立计数，与消息序号对称；不是全局自增。
                    seq INTEGER NOT NULL,
                    type TEXT NOT NULL,
                    message_id TEXT,
                    -- 写入时固化的消息 JSON 快照。事件是不可变的历史，
                    -- 不能等读的时候再回查消息表——那样后续状态会改写过去的事件。
                    payload TEXT,
                    created_at INTEGER NOT NULL,
                    PRIMARY KEY (discussion_id, seq)
                );
                """
            )
            # PRAGMA 不能用占位符绑定，这里拼的是代码内常量。
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def _migrate_legacy_schema(self, conn: sqlite3.Connection) -> None:
        """开发期结构迁移。

        早期版本把消息序号和事件序号合并成一个字段、事件表用全局自增主键，
        这两版都还没有真实数据。检测到旧结构时：表为空就重建，有数据就拒绝启动，
        避免静默改坏别人的库。
        """

        def table_exists(name: str) -> bool:
            return (
                conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
                ).fetchone()
                is not None
            )

        needs_rebuild = False
        if table_exists("discussions"):
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(discussions)")}
            if not {"message_seq", "event_seq", "message_count"} <= columns:
                needs_rebuild = True
        if table_exists("discussion_events"):
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(discussion_events)")}
            primary_key = [
                row["name"]
                for row in conn.execute("PRAGMA table_info(discussion_events)")
                if row["pk"]
            ]
            # v2 的事件表没有 payload 列，读事件时要回查消息表，历史会被后续状态改写。
            if primary_key != ["discussion_id", "seq"] or "payload" not in columns:
                needs_rebuild = True

        if not needs_rebuild:
            return

        for name in ("discussion_events", "messages", "discussion_participants", "discussions"):
            if not table_exists(name):
                continue
            rows = conn.execute(f"SELECT COUNT(*) AS count FROM {name}").fetchone()["count"]
            if rows:
                raise RuntimeError(
                    f"{name} 使用的是旧表结构且已有 {rows} 行数据。"
                    "请先备份 data/thinkspace.db 并手动迁移，再启动服务。"
                )
        conn.executescript(
            """
            DROP TABLE IF EXISTS discussion_events;
            DROP TABLE IF EXISTS messages;
            DROP TABLE IF EXISTS discussion_participants;
            DROP TABLE IF EXISTS discussions;
            """
        )

    # ---------------- 行转换 ----------------

    @staticmethod
    def _discussion_row(row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "topic": row["topic"],
            "status": row["status"],
            "max_turns": row["max_turns"],
            "turn_index": row["turn_index"],
            "message_seq": row["message_seq"],
            "event_seq": row["event_seq"],
            "message_count": row["message_count"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "paused_at": row["paused_at"],
            "stopped_at": row["stopped_at"],
            "finished_at": row["finished_at"],
        }

    @staticmethod
    def _message_row(row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "seq": row["seq"],
            "role_id": row["role_id"],
            "body": row["body"],
            "status": row["status"],
            "client_msg_id": row["client_msg_id"],
            "in_reply_to": row["in_reply_to"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    @staticmethod
    def _insert_event(
        conn: sqlite3.Connection,
        discussion_id: str,
        seq: int,
        event_type: str,
        now: int,
        message_id: str | None = None,
        payload: str | None = None,
    ) -> None:
        """写一条事件。四处写事件的地方都走这里，避免列顺序写错或漏字段。"""
        conn.execute(
            """INSERT INTO discussion_events(
                seq, discussion_id, type, message_id, payload, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)""",
            (seq, discussion_id, event_type, message_id, payload, now),
        )

    # ---------------- 讨论 ----------------

    def create_discussion(
        self,
        user_id: str,
        topic: str,
        max_turns: int = 6,
        role_ids: list[str] | None = None,
    ) -> dict:
        """创建讨论并落座，同时写入 `discussion.created` 事件。"""
        discussion_id = uuid.uuid4().hex
        now = int(time.time())
        catalog = {item["role_id"]: item for item in ROLE_CATALOG}
        wanted = set(role_ids) if role_ids is not None else set(DEFAULT_ROLE_IDS)
        # 用户必须始终在座，否则无法发言。
        wanted.add(USER_ROLE)
        chosen = [role_id for role_id in DEFAULT_ROLE_IDS if role_id in wanted]

        with self._write() as conn:
            conn.execute(
                """INSERT INTO discussions(
                    id, user_id, topic, status, max_turns, turn_index,
                    message_seq, event_seq, message_count, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 0, 0, 1, 0, ?, ?)""",
                (discussion_id, user_id, topic, STATUS_ACTIVE, max_turns, now, now),
            )
            conn.executemany(
                """INSERT INTO discussion_participants(
                    discussion_id, role_id, display_name, title, seat
                ) VALUES (?, ?, ?, ?, ?)""",
                [
                    (
                        discussion_id,
                        role_id,
                        catalog[role_id]["display_name"],
                        catalog[role_id]["title"],
                        seat,
                    )
                    for seat, role_id in enumerate(chosen)
                ],
            )
            self._insert_event(conn, discussion_id, 1, EVENT_DISCUSSION_CREATED, now)
        self.notify_change(discussion_id)

        created = self.get_discussion(user_id, discussion_id)
        if created is None:  # pragma: no cover - 刚提交就读不到属于存储故障
            raise RuntimeError("讨论创建后读取失败。")
        return created

    def get_discussion(self, user_id: str, discussion_id: str) -> dict | None:
        """读取讨论详情；`user_id` 参与查询，改 ID 也拿不到别人的讨论。"""
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM discussions WHERE id = ? AND user_id = ?",
                (discussion_id, user_id),
            ).fetchone()
            if row is None:
                return None
            participants = conn.execute(
                """SELECT role_id, display_name, title, seat FROM discussion_participants
                WHERE discussion_id = ? ORDER BY seat""",
                (discussion_id,),
            ).fetchall()
        result = self._discussion_row(row)
        result["participants"] = [dict(item) for item in participants]
        return result

    def list_discussions(
        self, user_id: str, limit: int = 20, offset: int = 0
    ) -> tuple[list[dict], int]:
        """按创建时间倒序分页；同一秒内用 rowid 兜底，保证分页不会抖动。

        列表也带在座角色，否则前端要为每条讨论再请求一次详情（典型 N+1）。
        角色用一条 IN 查询批量取出，不随讨论数量线性增长。
        """
        with self._connection() as conn:
            total = conn.execute(
                "SELECT COUNT(*) AS count FROM discussions WHERE user_id = ?", (user_id,)
            ).fetchone()["count"]
            rows = conn.execute(
                """SELECT * FROM discussions WHERE user_id = ?
                ORDER BY created_at DESC, rowid DESC LIMIT ? OFFSET ?""",
                (user_id, limit, offset),
            ).fetchall()
            items = [self._discussion_row(row) for row in rows]
            for item in items:
                item["participants"] = []
            if items:
                identifiers = [item["id"] for item in items]
                placeholders = ",".join("?" * len(identifiers))
                seats = conn.execute(
                    f"""SELECT discussion_id, role_id, display_name, title, seat
                    FROM discussion_participants
                    WHERE discussion_id IN ({placeholders})
                    ORDER BY discussion_id, seat""",
                    identifiers,
                ).fetchall()
                grouped: dict[str, list[dict]] = {item["id"]: [] for item in items}
                for seat in seats:
                    grouped[seat["discussion_id"]].append(
                        {
                            "role_id": seat["role_id"],
                            "display_name": seat["display_name"],
                            "title": seat["title"],
                            "seat": seat["seat"],
                        }
                    )
                for item in items:
                    item["participants"] = grouped[item["id"]]
        return items, int(total)

    def _transition(
        self,
        user_id: str,
        discussion_id: str,
        allowed_from: tuple[str, ...],
        target: str,
        event_type: str,
        timestamp_column: str,
        action: str,
    ) -> dict:
        """统一的状态流转：只允许从 `allowed_from` 迁移到 `target`。

        已经是目标状态时幂等返回，不重复写事件；其余非允许来源一律抛 `DiscussionStateError`。
        """
        now = int(time.time())
        unchanged = False
        with self._write() as conn:
            row = conn.execute(
                "SELECT status, event_seq FROM discussions WHERE id = ? AND user_id = ?",
                (discussion_id, user_id),
            ).fetchone()
            if row is None:
                raise DiscussionNotFound("讨论不存在或不属于当前用户。")
            current = row["status"]
            if current == target:
                # 已经是目标状态：幂等返回。不在事务里查库，避免持有写锁时再开连接。
                unchanged = True
            else:
                if current not in allowed_from:
                    raise DiscussionStateError(current, action)
                event_seq = int(row["event_seq"]) + 1
                if target == STATUS_ACTIVE:
                    # 恢复：清空暂停时间，标记“当前没有在暂停”。
                    conn.execute(
                        """UPDATE discussions
                        SET status = ?, paused_at = NULL, event_seq = ?, updated_at = ?
                        WHERE id = ?""",
                        (target, event_seq, now, discussion_id),
                    )
                else:
                    # 列名只可能是下面三者之一，由调用方以字面量传入，不接受外部输入。
                    # 用显式判断而不是 assert：assert 在 `python -O` 下会被整条移除。
                    if timestamp_column not in TIMESTAMP_COLUMNS:
                        raise ValueError(f"未知的时间戳列：{timestamp_column}")
                    conn.execute(
                        f"""UPDATE discussions
                        SET status = ?, {timestamp_column} = ?, event_seq = ?, updated_at = ?
                        WHERE id = ?""",
                        (target, now, event_seq, now, discussion_id),
                    )
                self._insert_event(conn, discussion_id, event_seq, event_type, now)
        if unchanged:
            return self.get_discussion(user_id, discussion_id)  # type: ignore[return-value]
        self.notify_change(discussion_id)
        return self.get_discussion(user_id, discussion_id)  # type: ignore[return-value]

    def pause_discussion(self, user_id: str, discussion_id: str) -> dict:
        return self._transition(
            user_id,
            discussion_id,
            allowed_from=(STATUS_ACTIVE,),
            target=STATUS_PAUSED,
            event_type=EVENT_DISCUSSION_PAUSED,
            timestamp_column="paused_at",
            action="暂停",
        )

    def resume_discussion(self, user_id: str, discussion_id: str) -> dict:
        return self._transition(
            user_id,
            discussion_id,
            allowed_from=(STATUS_PAUSED,),
            target=STATUS_ACTIVE,
            event_type=EVENT_DISCUSSION_RESUMED,
            timestamp_column="paused_at",
            action="恢复",
        )

    def stop_discussion(self, user_id: str, discussion_id: str) -> dict:
        return self._transition(
            user_id,
            discussion_id,
            allowed_from=OPEN_STATUSES,
            target=STATUS_STOPPED,
            event_type=EVENT_DISCUSSION_STOPPED,
            timestamp_column="stopped_at",
            action="停止",
        )

    def finish_discussion(self, user_id: str, discussion_id: str) -> dict:
        return self._transition(
            user_id,
            discussion_id,
            allowed_from=OPEN_STATUSES,
            target=STATUS_FINISHED,
            event_type=EVENT_DISCUSSION_FINISHED,
            timestamp_column="finished_at",
            action="结束",
        )

    # ---------------- 消息 ----------------

    def append_message(
        self,
        user_id: str,
        discussion_id: str,
        role_id: str,
        body: str,
        client_msg_id: str | None = None,
        in_reply_to: str | None = None,
        status: str = MESSAGE_COMPLETED,
        turn_index: int | None = None,
    ) -> tuple[dict, bool]:
        """追加一条**已经定型**的消息，返回 (消息, 是否新建)。

        只保存完整结果，不处理流式生成：`status` 在落库时确定，之后不会改变。
        生成过程（增量、取消、重试）属于编排模块，本层不参与。

        `turn_index` 由 E 模块在写回 AI 发言时传入，和消息序号在同一个事务里推进；
        不传则保持原值。用户消息不会传这个参数，轮次只由 AI 发言推进。

        消息序号、事件序号、消息计数三者在同一个 `BEGIN IMMEDIATE` 事务里推进，
        写锁保证并发提交不会拿到同一个序号。

        带 `client_msg_id` 时是幂等提交：同一讨论内重复提交返回原消息，`created=False`。
        空字符串与纯空白视为未提供——空值不是 NULL，不归一化会撞上唯一索引。
        """
        message_id = uuid.uuid4().hex
        now = int(time.time())
        client_msg_id = (client_msg_id or "").strip() or None
        in_reply_to = (in_reply_to or "").strip() or None
        # 内部调用方（E 模块）绕过了 HTTP 的 pydantic 校验，这里兜一道。
        if role_id not in ROLE_IDS:
            raise ValueError(f"未知角色：{role_id}")
        if status not in FINAL_MESSAGE_STATUSES:
            raise ValueError(
                "消息状态只能是 " + "、".join(FINAL_MESSAGE_STATUSES) + f" 之一，收到 {status}。"
            )
        body = body.strip()
        if not body:
            raise ValueError("消息内容不能为空。")
        if len(body) > MAX_MESSAGE_LENGTH:
            raise ValueError(f"单条消息最多 {MAX_MESSAGE_LENGTH} 字。")
        with self._write() as conn:
            row = conn.execute(
                """SELECT status, message_seq, event_seq, message_count, turn_index
                FROM discussions WHERE id = ? AND user_id = ?""",
                (discussion_id, user_id),
            ).fetchone()
            if row is None:
                raise DiscussionNotFound("讨论不存在或不属于当前用户。")

            if turn_index is not None and int(turn_index) < int(row["turn_index"]):
                raise ValueError("轮次不能回退。")

            if client_msg_id:
                existing = conn.execute(
                    "SELECT * FROM messages WHERE discussion_id = ? AND client_msg_id = ?",
                    (discussion_id, client_msg_id),
                ).fetchone()
                if existing is not None:
                    # 幂等命中：不写事件，不通知订阅者。
                    return self._message_row(existing), False

            if row["status"] not in OPEN_STATUSES:
                state = "停止" if row["status"] == STATUS_STOPPED else "结束"
                raise DiscussionClosed(f"讨论已{state}，不能再发送消息。")
            if int(row["message_count"]) >= MAX_MESSAGES_PER_DISCUSSION:
                raise DiscussionQuotaExceeded(
                    f"单条讨论最多 {MAX_MESSAGES_PER_DISCUSSION} 条消息。"
                )
            # 只有在这条讨论里落座的角色才能发言，否则 E 模块可以让一个不在场的人插话。
            seated = conn.execute(
                """SELECT 1 FROM discussion_participants
                WHERE discussion_id = ? AND role_id = ?""",
                (discussion_id, role_id),
            ).fetchone()
            if seated is None:
                raise ValueError(f"角色 {role_id} 没有在这条讨论中落座。")
            if in_reply_to:
                target = conn.execute(
                    "SELECT 1 FROM messages WHERE id = ? AND discussion_id = ?",
                    (in_reply_to, discussion_id),
                ).fetchone()
                if target is None:
                    raise ValueError("引用的消息不存在或不属于这条讨论。")

            message_seq = int(row["message_seq"]) + 1
            event_seq = int(row["event_seq"]) + 1
            conn.execute(
                """INSERT INTO messages(
                    id, discussion_id, seq, role_id, body, status,
                    client_msg_id, in_reply_to, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    message_id,
                    discussion_id,
                    message_seq,
                    role_id,
                    body,
                    status,
                    client_msg_id,
                    in_reply_to,
                    now,
                    now,
                ),
            )
            # 快照在写入时固化，之后消息状态再变也不会改写这条历史事件。
            inserted = conn.execute(
                "SELECT * FROM messages WHERE id = ?", (message_id,)
            ).fetchone()
            payload = json.dumps(
                self._message_row(inserted), ensure_ascii=False, separators=(",", ":")
            )
            self._insert_event(
                conn, discussion_id, event_seq, EVENT_MESSAGE_CREATED, now, message_id, payload
            )
            effective_turn = int(row["turn_index"]) if turn_index is None else int(turn_index)
            conn.execute(
                """UPDATE discussions
                SET message_seq = ?, event_seq = ?, message_count = message_count + 1,
                    turn_index = ?, updated_at = ?
                WHERE id = ?""",
                (message_seq, event_seq, effective_turn, now, discussion_id),
            )
        self.notify_change(discussion_id)
        return self.get_message(user_id, discussion_id, message_id), True

    def get_message(self, user_id: str, discussion_id: str, message_id: str) -> dict:
        with self._connection() as conn:
            row = conn.execute(
                """SELECT m.* FROM messages m
                JOIN discussions d ON d.id = m.discussion_id
                WHERE d.user_id = ? AND m.discussion_id = ? AND m.id = ?""",
                (user_id, discussion_id, message_id),
            ).fetchone()
        if row is None:
            raise DiscussionNotFound("消息不存在或不属于当前用户。")
        return self._message_row(row)

    def list_messages(
        self,
        user_id: str,
        discussion_id: str,
        after_seq: int = 0,
        before_seq: int | None = None,
        limit: int = 50,
        newest_first: bool = False,
    ) -> tuple[list[dict], bool, int]:
        """读取消息，返回 (消息, 是否还有更多, 消息序号水位)。

        **两种游标，不要混用**：

        - 正向拿新消息（默认）：`after_seq`，取 `seq > after_seq` 的升序结果，
          用于轮询增量。
        - 往回翻历史（`newest_first=True`）：`before_seq`，取 `seq < before_seq`
          中最大的 limit 条。第一页不传 `before_seq`，之后把它返回结果里最小的
          `seq` 再传回来，就能一页页往前翻。此模式下 `after_seq` 不生效。

        返回的列表**始终按 seq 升序**，前端不用再排一次。
        """
        with self._read_snapshot() as conn:
            discussion = conn.execute(
                "SELECT message_seq FROM discussions WHERE id = ? AND user_id = ?",
                (discussion_id, user_id),
            ).fetchone()
            if discussion is None:
                raise DiscussionNotFound("讨论不存在或不属于当前用户。")
            if newest_first:
                if before_seq is None:
                    rows = conn.execute(
                        """SELECT * FROM messages WHERE discussion_id = ?
                        ORDER BY seq DESC LIMIT ?""",
                        (discussion_id, limit + 1),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """SELECT * FROM messages WHERE discussion_id = ? AND seq < ?
                        ORDER BY seq DESC LIMIT ?""",
                        (discussion_id, before_seq, limit + 1),
                    ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM messages WHERE discussion_id = ? AND seq > ?
                    ORDER BY seq ASC LIMIT ?""",
                    (discussion_id, after_seq, limit + 1),
                ).fetchall()
            message_seq = int(discussion["message_seq"])
        has_more = len(rows) > limit
        selected = rows[:limit]
        if newest_first:
            selected = list(reversed(selected))
        return (
            [self._message_row(row) for row in selected],
            has_more,
            message_seq,
        )

    # ---------------- 事件 ----------------

    def list_events(
        self,
        user_id: str,
        discussion_id: str,
        after_seq: int = 0,
        limit: int = 100,
    ) -> tuple[list[dict], bool, int, str]:
        """读取事件流，返回 (事件, 是否还有更多, 事件序号水位, 讨论状态)。

        事件带上消息快照，客户端拿到一次就能渲染，不必再按 message_id 回查。
        """
        with self._read_snapshot() as conn:
            discussion = conn.execute(
                "SELECT status, event_seq FROM discussions WHERE id = ? AND user_id = ?",
                (discussion_id, user_id),
            ).fetchone()
            if discussion is None:
                raise DiscussionNotFound("讨论不存在或不属于当前用户。")
            rows = conn.execute(
                """SELECT seq AS event_seq, type AS event_type, payload,
                          created_at AS event_created_at
                FROM discussion_events
                WHERE discussion_id = ? AND seq > ?
                ORDER BY seq ASC LIMIT ?""",
                (discussion_id, after_seq, limit + 1),
            ).fetchall()
            event_seq = int(discussion["event_seq"])
            status = discussion["status"]

        has_more = len(rows) > limit
        events = []
        for row in rows[:limit]:
            events.append(
                {
                    "seq": row["event_seq"],
                    "type": row["event_type"],
                    "created_at": row["event_created_at"],
                    # 直接还原写入时的快照：即使消息后来变了状态，这条历史事件也不会跟着变。
                    "message": json.loads(row["payload"]) if row["payload"] else None,
                }
            )
        return events, has_more, int(discussion["event_seq"]), discussion["status"]
