"""收藏问答 HTTP 接口。

路径统一在 `/api/qa` 下；数据按当前身份隔离，扩展身份不参与问答（没有 OAuth token）。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field, field_validator

from .deps import current_identity, real_zhihu_identity
from .qa import QAService
from .qa_store import QASessionNotFound, QAStore

router = APIRouter(prefix="/api/qa", tags=["qa"])


class SessionInput(BaseModel):
    favlist_url_token: int = Field(gt=0, description="收藏夹的 UrlToken")
    favlist_title: str = Field(default="", max_length=200, description="可选的收藏夹名称")


class QuestionInput(BaseModel):
    question: str = Field(min_length=1, max_length=2000, description="要在这个收藏夹内问的问题")

    @field_validator("question")
    @classmethod
    def _clean_question(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("问题不能只有空格。")
        if "\x00" in cleaned:
            raise ValueError("问题不能包含空字符。")
        return cleaned


class CitationOut(BaseModel):
    source_url: str
    title: str
    author_name: str
    snippet: str
    content_type: str
    rank: int


class MessageOut(BaseModel):
    id: str
    role: str
    body: str
    created_at: int
    citations: list[CitationOut] = Field(default_factory=list)


class SessionOut(BaseModel):
    id: str
    favlist_url_token: int
    favlist_title: str
    created_at: int
    updated_at: int
    message_count: int


class SessionDetailOut(SessionOut):
    messages: list[MessageOut]


class SessionListOut(BaseModel):
    items: list[SessionOut]
    total: int
    limit: int
    offset: int
    has_more: bool


class AskOut(BaseModel):
    session: SessionOut
    question: MessageOut
    answer: MessageOut


def _store(request: Request) -> QAStore:
    return request.app.state.qa_store


def _service(request: Request) -> QAService:
    return request.app.state.qa


def _identity(request: Request):
    identity = current_identity(request)
    if identity.mode == "extension":
        raise HTTPException(
            401,
            detail={
                "code": "AUTH_REQUIRED",
                "message": "收藏问答请在网页端登录后使用。",
            },
        )
    if identity.mode == "demo":
        return identity
    return real_zhihu_identity(request)


def _not_found() -> HTTPException:
    return HTTPException(
        404,
        detail={"code": "QA_SESSION_NOT_FOUND", "message": "问答会话不存在或不属于当前用户。"},
    )


@router.post(
    "/sessions",
    response_model=SessionOut,
    status_code=201,
    summary="创建或复用收藏问答会话",
    description="同一用户在同一收藏夹下只保留一个会话；已存在时返回 200。",
)
def create_session(payload: SessionInput, request: Request, response: Response) -> Any:
    identity = _identity(request)
    session, created = _store(request).create_or_get_session(
        identity.user_id,
        payload.favlist_url_token,
        payload.favlist_title,
    )
    if not created:
        response.status_code = 200
    return session


@router.get("/sessions", response_model=SessionListOut, summary="问答会话列表")
def list_sessions(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> Any:
    identity = _identity(request)
    items, total = _store(request).list_sessions(identity.user_id, limit, offset)
    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(items) < total,
    }


@router.get("/sessions/{session_id}", response_model=SessionDetailOut, summary="问答会话详情")
def get_session(session_id: str, request: Request) -> Any:
    identity = _identity(request)
    session = _store(request).get_session(identity.user_id, session_id)
    if session is None:
        raise _not_found()
    messages = _store(request).get_messages(identity.user_id, session_id)
    return {**session, "messages": messages}


@router.post(
    "/sessions/{session_id}/messages",
    response_model=AskOut,
    summary="在收藏夹内提问",
    description=(
        "只在当前会话对应的收藏夹内检索摘要；没有命中时明确说明资料不足，"
        "不拿不相关的内容凑数。回答与引用全部落库。"
    ),
)
async def ask(
    session_id: str,
    payload: QuestionInput,
    request: Request,
) -> Any:
    identity = _identity(request)
    try:
        return await _service(request).ask(identity, session_id, payload.question)
    except QASessionNotFound as exc:
        raise _not_found() from exc
