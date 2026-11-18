"""讨论室 HTTP 接口。

分三类：
- 讨论生命周期：创建、详情、列表、暂停、恢复、停止、结束
- 消息：用户发言（幂等）、读取（支持从最新往回取）
- 事件：轮询拉取 + SSE 推送，两者共用同一套事件结构，`Last-Event-ID` 与 `after_seq` 等价

用户端只能以 `user` 身份发言；探索者、质疑者、归纳者的消息必须由服务端编排写入，
不开放给前端，避免伪造角色观点。
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from collections.abc import AsyncIterator, Generator
from contextlib import contextmanager
from typing import Any

import anyio
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from .deps import current_identity
from .discussion_store import (
    CLOSED_STATUSES,
    MAX_MESSAGE_LENGTH,
    ROLE_CATALOG,
    USER_ROLE,
    DiscussionClosed,
    DiscussionNotFound,
    DiscussionQuotaExceeded,
    DiscussionStateError,
    DiscussionStore,
)

router = APIRouter(prefix="/api/discussions", tags=["discussions"])

KNOWN_ROLE_IDS = {item["role_id"] for item in ROLE_CATALOG}

# SSE 参数：多久没有新事件就发一次心跳注释，以及等待新事件的最长时间（也是兜底轮询间隔）。
HEARTBEAT_SECONDS = 15.0
POLL_INTERVAL_SECONDS = 1.0
# 单条连接最长存活时间，避免客户端异常断开后线程被长期占用。
STREAM_MAX_SECONDS = 600.0
STREAM_BATCH = 50
# 同时在线订阅数上限。每个 SSE 连接占一个线程，没有上限时容易被拖垮。
MAX_CONCURRENT_STREAMS = 32
_STREAM_SLOTS = threading.BoundedSemaphore(MAX_CONCURRENT_STREAMS)

# SQLite 的 INTEGER 是 64 位有符号整数；Python 的 int 不限长，
# 超出范围的值绑定到 SQL 参数时会抛 OverflowError（变成 500）。
MAX_SEQ_VALUE = 2**63 - 1


def _clamp_seq(value: int) -> int:
    """把外部传入的序号收敛到 SQLite 能接受的范围。"""
    return max(0, min(int(value), MAX_SEQ_VALUE))


# ---------------- 响应模型 ----------------
# 用显式模型而不是裸 dict：/docs 里能看到字段说明，前端对接不用猜。


class ParticipantOut(BaseModel):
    role_id: str
    display_name: str
    title: str
    seat: int


class DiscussionOut(BaseModel):
    id: str
    topic: str
    status: str
    max_turns: int
    turn_index: int
    message_seq: int = Field(description="最后一条消息的序号，也是消息分页的水位")
    event_seq: int = Field(description="最后一个事件的序号，也是断线补发的水位")
    message_count: int
    created_at: int
    updated_at: int
    paused_at: int | None = None
    stopped_at: int | None = None
    finished_at: int | None = None
    participants: list[ParticipantOut] = Field(default_factory=list)


class MessageOut(BaseModel):
    id: str
    seq: int = Field(description="消息在讨论内的顺序号，从 1 开始")
    role_id: str
    body: str
    status: str
    client_msg_id: str | None = None
    in_reply_to: str | None = None
    created_at: int
    updated_at: int


class EventOut(BaseModel):
    seq: int = Field(description="事件序号，与消息序号无关，用于补发")
    type: str
    created_at: int
    message: MessageOut | None = Field(
        default=None, description="消息类事件带消息快照；状态类事件为 null"
    )


class DiscussionListOut(BaseModel):
    items: list[DiscussionOut]
    total: int
    limit: int
    offset: int
    has_more: bool


class MessageListOut(BaseModel):
    items: list[MessageOut]
    message_seq: int
    has_more: bool
    after_seq: int
    before_seq: int | None = None


class MessageCreatedOut(BaseModel):
    message: MessageOut
    created: bool = Field(description="false 表示命中幂等键，返回的是首次提交的消息")


class EventListOut(BaseModel):
    discussion_id: str
    status: str
    event_seq: int
    has_more: bool
    after_seq: int
    events: list[EventOut]


# ---------------- 请求模型 ----------------


class DiscussionInput(BaseModel):
    topic: str = Field(min_length=1, max_length=200, description="讨论主题")
    max_turns: int = Field(default=6, ge=1, le=20, description="轮次上限，供编排模块读取")
    role_ids: list[str] | None = Field(
        default=None, max_length=8, description="在座角色，不传则四个角色全部在座"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "topic": "AI 应该替我们做决定吗？",
                    "max_turns": 6,
                    "role_ids": ["explorer", "skeptic", "weaver"],
                }
            ]
        }
    }

    @field_validator("topic")
    @classmethod
    def _require_visible_topic(cls, value: str) -> str:
        # min_length 只数字符数，纯空格能混过去，这里去空白后再判。
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("讨论主题不能只有空格。")
        if "\x00" in cleaned:
            # 空字符本身能完整存取，但会让 SQL 的 length()/LIKE 等函数计数错乱，
            # 接口层直接拒绝，避免下游踩坑——这是接口规范，不是“数据库会截断”。
            raise ValueError("讨论主题不能包含空字符。")
        return cleaned


class MessageInput(BaseModel):
    body: str = Field(min_length=1, max_length=MAX_MESSAGE_LENGTH, description="发言内容")
    client_msg_id: str | None = Field(
        default=None,
        max_length=64,
        description="幂等键；网络重试时带上同一个值，服务端只保存一次",
    )
    in_reply_to: str | None = Field(
        default=None, max_length=64, description="引用同一条讨论内的某条消息 ID"
    )
    advance: bool = Field(
        default=False,
        description="创建成功后自动推进一轮 AI 发言；网页端默认开启，普通 API 调用默认不开启",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "body": "我想先区分：替我们分析，和替我们决定。",
                    "client_msg_id": "0f6c3a1e-8c2b-4f7a-9d31-2b5c8e7a1f40",
                    "in_reply_to": None,
                }
            ]
        }
    }

    @field_validator("body")
    @classmethod
    def _require_visible_body(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("发言内容不能只有空格。")
        if "\x00" in cleaned:
            raise ValueError("发言内容不能包含空字符。")
        return cleaned


# ---------------- 公共辅助 ----------------


def _store(request: Request) -> DiscussionStore:
    return request.app.state.discussions


def _not_found() -> HTTPException:
    return HTTPException(
        404,
        detail={"code": "DISCUSSION_NOT_FOUND", "message": "讨论不存在或不属于当前用户。"},
    )


@contextmanager
def _translate_errors() -> Generator[None, None, None]:
    """把存储层异常翻译成 HTTP 错误。

    用上下文管理器而不是 `_guarded(lambda: ...)`：lambda 会把真实调用栈埋掉，
    出错时只剩一行无信息量的包装调用。
    """
    try:
        yield
    except DiscussionNotFound as exc:
        raise _not_found() from exc
    except DiscussionClosed as exc:
        raise HTTPException(
            409, detail={"code": "DISCUSSION_CLOSED", "message": str(exc)}
        ) from exc
    except DiscussionStateError as exc:
        raise HTTPException(
            409,
            detail={
                "code": "INVALID_STATE",
                "message": str(exc),
                "current_status": exc.current,
            },
        ) from exc
    except DiscussionQuotaExceeded as exc:
        raise HTTPException(
            429, detail={"code": "MESSAGE_QUOTA_EXCEEDED", "message": str(exc)}
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            422, detail={"code": "INVALID_REFERENCE", "message": str(exc)}
        ) from exc
    except sqlite3.OperationalError as exc:
        message = str(exc).lower()
        if "locked" in message or "busy" in message:
            raise HTTPException(
                503,
                detail={
                    "code": "DATABASE_BUSY",
                    "message": "数据库繁忙，请稍后重试。",
                },
            ) from exc
        raise


# ---------------- 讨论生命周期 ----------------


@router.post(
    "",
    status_code=201,
    response_model=DiscussionOut,
    summary="创建讨论",
    response_description="新建的讨论，含在座角色",
)
def create_discussion(payload: DiscussionInput, request: Request) -> Any:
    identity = current_identity(request)
    unknown = [role for role in (payload.role_ids or []) if role not in KNOWN_ROLE_IDS]
    if unknown:
        raise HTTPException(
            422,
            detail={
                "code": "UNKNOWN_ROLE",
                "message": "存在未定义的角色：" + "、".join(unknown),
                "known_roles": sorted(KNOWN_ROLE_IDS),
            },
        )
    # 写库可能遇到 SQLite 写锁超时，同样要翻译成 503，不能漏成 500。
    with _translate_errors():
        return _store(request).create_discussion(
            identity.user_id,
            payload.topic,
            max_turns=payload.max_turns,
            role_ids=payload.role_ids,
        )


@router.get("", response_model=DiscussionListOut, summary="讨论列表")
def list_discussions(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=MAX_SEQ_VALUE),
) -> Any:
    identity = current_identity(request)
    items, total = _store(request).list_discussions(
        identity.user_id, limit=limit, offset=offset
    )
    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(items) < total,
    }


@router.get("/{discussion_id}", response_model=DiscussionOut, summary="讨论详情")
def get_discussion(discussion_id: str, request: Request) -> Any:
    identity = current_identity(request)
    discussion = _store(request).get_discussion(identity.user_id, discussion_id)
    if discussion is None:
        raise _not_found()
    return discussion


@router.post("/{discussion_id}/pause", response_model=DiscussionOut, summary="暂停讨论")
def pause_discussion(discussion_id: str, request: Request) -> Any:
    identity = current_identity(request)
    with _translate_errors():
        return _store(request).pause_discussion(identity.user_id, discussion_id)


@router.post("/{discussion_id}/resume", response_model=DiscussionOut, summary="恢复讨论")
def resume_discussion(discussion_id: str, request: Request) -> Any:
    identity = current_identity(request)
    with _translate_errors():
        return _store(request).resume_discussion(identity.user_id, discussion_id)


@router.post("/{discussion_id}/stop", response_model=DiscussionOut, summary="停止讨论")
def stop_discussion(discussion_id: str, request: Request) -> Any:
    identity = current_identity(request)
    with _translate_errors():
        return _store(request).stop_discussion(identity.user_id, discussion_id)


@router.post("/{discussion_id}/finish", response_model=DiscussionOut, summary="结束讨论")
def finish_discussion(discussion_id: str, request: Request) -> Any:
    identity = current_identity(request)
    with _translate_errors():
        return _store(request).finish_discussion(identity.user_id, discussion_id)


# ---------------- 消息 ----------------


@router.post(
    "/{discussion_id}/messages",
    status_code=201,
    response_model=MessageCreatedOut,
    summary="发送用户发言",
    description="带 client_msg_id 时幂等：重复提交返回首次那条消息，HTTP 状态为 200。",
)
def create_message(
    discussion_id: str,
    payload: MessageInput,
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
) -> Any:
    identity = current_identity(request)
    with _translate_errors():
        message, created = _store(request).append_message(
            identity.user_id,
            discussion_id,
            USER_ROLE,
            payload.body,
            client_msg_id=payload.client_msg_id,
            in_reply_to=payload.in_reply_to,
        )
    if not created:
        # 幂等命中不新建记录，用 200 与新建的 201 区分。
        response.status_code = 200
    elif payload.advance:
        # 用户发言成功后，让 E 模块在后台推进一轮 AI 发言。
        # 只有真正新建消息时才排任务：网络重试命中幂等键，不能重复生成。
        engine = getattr(request.app.state, "engine", None)
        if engine is not None:
            background_tasks.add_task(
                engine.advance_safely, identity.user_id, discussion_id
            )
    return {"message": message, "created": created}


@router.get(
    "/{discussion_id}/messages",
    response_model=MessageListOut,
    summary="读取消息",
    description=(
        "默认按 seq 升序返回 after_seq 之后的消息，用于增量轮询。"
        "newest_first=true 时改为往回翻历史，用 before_seq 游标；"
        "第一页不传 before_seq，之后把它返回结果里最小的 seq 传回来。"
    ),
)
def list_messages(
    discussion_id: str,
    request: Request,
    after_seq: int = Query(
        default=0, ge=0, le=MAX_SEQ_VALUE, description="只返回 seq 大于该值的消息"
    ),
    before_seq: int | None = Query(
        default=None,
        ge=1,
        le=MAX_SEQ_VALUE,
        description="newest_first 翻历史时使用：只返回 seq 小于该值的消息",
    ),
    limit: int = Query(default=50, ge=1, le=200),
    newest_first: bool = Query(default=False, description="从最新消息往回取"),
) -> Any:
    identity = current_identity(request)
    with _translate_errors():
        items, has_more, message_seq = _store(request).list_messages(
            identity.user_id,
            discussion_id,
            after_seq=after_seq,
            before_seq=before_seq,
            limit=limit,
            newest_first=newest_first,
        )
    return {
        "items": items,
        "message_seq": message_seq,
        "has_more": has_more,
        "after_seq": after_seq,
        "before_seq": before_seq,
    }


# ---------------- 事件 ----------------


@router.get(
    "/{discussion_id}/events",
    response_model=EventListOut,
    summary="拉取事件（轮询）",
    description="断线后带上最后收到的事件序号即可补发；讨论状态在顶层返回，不占用事件序号。",
)
def list_events(
    discussion_id: str,
    request: Request,
    after_seq: int = Query(default=0, ge=0, le=MAX_SEQ_VALUE),
    limit: int = Query(default=100, ge=1, le=200),
) -> Any:
    identity = current_identity(request)
    with _translate_errors():
        events, has_more, event_seq, status = _store(request).list_events(
            identity.user_id, discussion_id, after_seq=after_seq, limit=limit
        )
    return {
        "discussion_id": discussion_id,
        "status": status,
        "event_seq": event_seq,
        "has_more": has_more,
        "after_seq": after_seq,
        "events": events,
    }


def _sse_frame(event_id: int | None, event_type: str | None, payload: dict) -> str:
    lines = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    if event_type:
        lines.append(f"event: {event_type}")
    lines.append("data: " + json.dumps(payload, ensure_ascii=False))
    return "\n".join(lines) + "\n\n"


async def _stream_frames(
    store: DiscussionStore,
    user_id: str,
    discussion_id: str,
    cursor: int,
) -> AsyncIterator[str]:
    """逐条产出 SSE 帧，直到讨论进入终态、超时或客户端断开。

    **必须是异步生成器**：客户端断开时 Starlette 会调用 `aclose()`，
    只有异步生成器能在 `await` 点收到取消，`finally` 才会执行、名额才会归还。
    同步生成器阻塞在线程里，"关闭"传不进去，会导致每条断开的连接永久占住
    一个名额和一个线程——这是测试抓出来的真实泄漏。

    数据库是同步 API，用 `anyio.to_thread` 放到线程池执行，不阻塞事件循环。
    """
    deadline = time.monotonic() + STREAM_MAX_SECONDS
    last_beat = time.monotonic()
    try:
        while True:
            try:
                events, has_more, _, status = await anyio.to_thread.run_sync(
                    lambda: store.list_events(
                        user_id, discussion_id, after_seq=cursor, limit=STREAM_BATCH
                    )
                )
            except DiscussionNotFound:
                yield _sse_frame(None, "error", {"code": "DISCUSSION_NOT_FOUND"})
                return

            for event in events:
                cursor = event["seq"]
                yield _sse_frame(cursor, event["type"], event)

            now = time.monotonic()
            if events:
                last_beat = now
                if has_more:
                    continue  # 还有积压，立刻接着读

            # 积压发完且讨论已进入终态，直接收尾。
            if status in CLOSED_STATUSES:
                # 附带 retry：前端若忘记 close()，EventSource 会按 60 秒而不是默认 3 秒重连，
                # 避免对着一条已结束的讨论疯狂重连。
                yield "retry: 60000\n" + _sse_frame(
                    cursor, "stream.end", {"status": status}
                )
                return

            if now - last_beat >= HEARTBEAT_SECONDS:
                # 注释行不会被客户端当作事件，只用于保活。
                yield ": keep-alive\n\n"
                last_beat = time.monotonic()

            if now > deadline:
                yield "retry: 60000\n" + _sse_frame(
                    cursor, "stream.timeout", {"status": status}
                )
                return

            # 有写入时立即唤醒；没有则等满一个间隔。
            # abandon_on_cancel：连接断开时不再等这次等待返回，直接取消。
            await anyio.to_thread.run_sync(
                lambda: store.wait_for_change(discussion_id, POLL_INTERVAL_SECONDS),
                abandon_on_cancel=True,
            )
    finally:
        # 正常结束、超时、客户端断开，都要归还连接名额。
        _STREAM_SLOTS.release()


@router.get(
    "/{discussion_id}/stream",
    summary="订阅事件（SSE）",
    description=(
        "text/event-stream。断线重连时浏览器会自动带上 Last-Event-ID，"
        "也可显式传 after_seq。讨论进入终态后发送 stream.end 并关闭连接。"
    ),
    response_class=StreamingResponse,
)
def stream_events(
    discussion_id: str,
    request: Request,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    after_seq: int = Query(default=0, ge=0, le=MAX_SEQ_VALUE),
) -> StreamingResponse:
    identity = current_identity(request)
    store = _store(request)
    # 先确认存在性和身份，避免流开始后才发现 404（那时已经无法返回错误码）。
    if store.get_discussion(identity.user_id, discussion_id) is None:
        raise _not_found()

    cursor = after_seq
    if last_event_id:
        try:
            cursor = int(last_event_id)
        except ValueError:
            cursor = after_seq
    # Header 不受 Query 的 le 约束，必须在这里收敛，否则超大值会让 SQL 绑定抛 OverflowError。
    cursor = _clamp_seq(cursor)

    # 每个订阅占一个线程，没有上限时几十个连接就能把服务拖住。
    if not _STREAM_SLOTS.acquire(blocking=False):
        raise HTTPException(
            503,
            detail={
                "code": "STREAM_BUSY",
                "message": f"当前订阅数已达上限（{MAX_CONCURRENT_STREAMS}），请稍后重试。",
            },
        )

    try:
        return StreamingResponse(
            _stream_frames(store, identity.user_id, discussion_id, cursor),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                # 关掉反向代理的缓冲，否则事件会被攒着一起发。
                "X-Accel-Buffering": "no",
            },
        )
    except Exception:
        # 生成器没来得及启动就失败时，名额不会被 finally 归还，这里兜底。
        _STREAM_SLOTS.release()
        raise
