"""E 模块的 HTTP 适配层。

路径仍然挂在 `/api/discussions` 下，但实现与 D 的 `discussions.py` 分开：
D 负责讨论和消息的存储，这里只负责“推进一轮 AI 发言”。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from .deps import current_identity
from .discussion_engine import DiscussionEngine, EngineBusy, EnginePaused
from .discussion_store import DiscussionClosed, DiscussionNotFound, DiscussionStateError
from .discussions import DiscussionOut, MessageOut
from .providers.model import ModelError

router = APIRouter(prefix="/api/discussions", tags=["discussion-engine"])


class AdvanceOut(BaseModel):
    advanced: bool
    reason: str | None = None
    role_id: str | None = None
    message: MessageOut | None = None
    discussion: DiscussionOut


@router.post(
    "/{discussion_id}/advance",
    response_model=AdvanceOut,
    summary="推进一轮 AI 发言",
    description=(
        "让编排器选择一位在座 AI 角色生成一句发言。"
        "暂停、结束、没有 AI 角色或达到轮次上限时返回 advanced=false，不写消息；"
        "同一条讨论正在生成时返回 409 ENGINE_BUSY。"
    ),
)
def advance(discussion_id: str, request: Request) -> Any:
    identity = current_identity(request)
    engine: DiscussionEngine = request.app.state.engine
    try:
        return engine.advance(identity.user_id, discussion_id)
    except DiscussionNotFound as exc:
        raise HTTPException(
            404,
            detail={"code": "DISCUSSION_NOT_FOUND", "message": str(exc)},
        ) from exc
    except DiscussionClosed as exc:
        raise HTTPException(
            409,
            detail={"code": "DISCUSSION_CLOSED", "message": str(exc)},
        ) from exc
    except EnginePaused as exc:
        raise HTTPException(
            409,
            detail={"code": "DISCUSSION_PAUSED", "message": str(exc)},
        ) from exc
    except EngineBusy as exc:
        raise HTTPException(
            409,
            detail={"code": "ENGINE_BUSY", "message": str(exc)},
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
    except ModelError as exc:
        raise HTTPException(
            502,
            detail={"code": "MODEL_ERROR", "message": str(exc)},
        ) from exc
