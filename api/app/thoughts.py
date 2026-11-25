from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .content import canonicalize_zhihu_url
from .deps import current_identity, store_of

router = APIRouter(prefix="/api/thoughts", tags=["thoughts"])
ThoughtID = Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]


class ThoughtInput(BaseModel):
    request_id: UUID
    title: str = Field(default="", max_length=180)
    body: str = Field(min_length=1, max_length=4000)
    source_url: str = Field(default="", max_length=2000)
    kind: Literal["library", "fusion", "branch", "discussion", "revision"] = "library"
    parent_ids: list[ThoughtID] = Field(default_factory=list, max_length=2)


def missing_thought() -> HTTPException:
    return HTTPException(404, detail="思绪不存在或不属于当前账号。")


@router.get("")
def list_thoughts(request: Request) -> dict:
    identity = current_identity(request)
    return {"items": store_of(request).list_thoughts(identity.user_id)}


@router.get("/{thought_id}")
def get_thought(thought_id: ThoughtID, request: Request) -> dict:
    identity = current_identity(request)
    thought = store_of(request).get_thought(identity.user_id, thought_id)
    if thought is None:
        raise missing_thought()
    return thought


@router.post("", status_code=201)
def create_thought(payload: ThoughtInput, request: Request) -> dict:
    identity = current_identity(request)
    body = payload.body.strip()
    if not body:
        raise HTTPException(422, detail="请填写思绪内容。")
    expected_parents = {"library": 0, "fusion": 2, "branch": 1, "discussion": 1, "revision": 1}[payload.kind]
    if len(set(payload.parent_ids)) != expected_parents or len(payload.parent_ids) != expected_parents:
        raise HTTPException(422, detail="这条思绪的来源数量不正确。")
    source_url = ""
    if payload.source_url.strip():
        if expected_parents:
            raise HTTPException(422, detail="派生思绪的出处由原思绪继承。")
        try:
            source_url = canonicalize_zhihu_url(payload.source_url).source_url
        except ValueError as exc:
            raise HTTPException(422, detail=str(exc)) from exc
    thought = store_of(request).create_thought(
        identity.user_id, str(payload.request_id), payload.title.strip() or body.splitlines()[0][:60],
        body, source_url, payload.kind, payload.parent_ids,
    )
    if thought is None:
        raise missing_thought()
    return thought
