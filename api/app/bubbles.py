from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from .content import canonicalize_zhihu_url
from .deps import current_identity, store_of


router = APIRouter(prefix="/api", tags=["bubbles"])


class BubbleInput(BaseModel):
    source_url: str = Field(min_length=1, max_length=2000)
    title: str = Field(default="", max_length=500)
    author_name: str = Field(default="", max_length=200)
    body: str = Field(min_length=1, max_length=4000)
    quote: str = Field(default="", max_length=4000)


@router.post("/bubbles", status_code=201)
def create_bubble(payload: BubbleInput, request: Request) -> dict:
    identity = current_identity(request)
    try:
        source = canonicalize_zhihu_url(payload.source_url)
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    return store_of(request).create_bubble(
        identity.user_id,
        source,
        payload.title,
        payload.author_name,
        payload.body,
        payload.quote,
    )


@router.get("/bubbles")
def list_bubbles(
    request: Request,
    source_url: str | None = None,
    article_key: str | None = Query(default=None, max_length=200),
) -> dict:
    identity = current_identity(request)
    if source_url:
        try:
            article_key = canonicalize_zhihu_url(source_url).article_key
        except ValueError as exc:
            raise HTTPException(422, detail=str(exc)) from exc
    return {"items": store_of(request).list_bubbles(identity.user_id, article_key)}


@router.get("/articles")
def list_articles(request: Request) -> dict:
    identity = current_identity(request)
    return {"items": store_of(request).list_articles(identity.user_id)}


@router.delete("/bubbles/{bubble_id}", status_code=204)
def delete_bubble(bubble_id: str, request: Request) -> Response:
    identity = current_identity(request)
    if not store_of(request).delete_bubble(identity.user_id, bubble_id):
        raise HTTPException(404, detail="泡泡不存在或不属于当前用户。")
    return Response(status_code=204)
