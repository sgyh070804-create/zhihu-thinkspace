"""文章收藏接口。

和知乎自己的收藏夹无关：这里收藏的是“我稍后还想回来看”的知乎内容，
用于阅读扩展的「收藏文章」按钮和网页端的「文章收藏」列表。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from .content import canonicalize_zhihu_url
from .deps import current_identity, store_of

router = APIRouter(prefix="/api/saved", tags=["saved"])


class SavedInput(BaseModel):
    source_url: str = Field(min_length=1, max_length=2000)
    title: str = Field(default="", max_length=500)
    author_name: str = Field(default="", max_length=200)


class SavedArticleOut(BaseModel):
    article_key: str
    source_url: str
    content_type: str
    content_id: str
    title: str
    author_name: str
    saved_at: int


class SavedResultOut(BaseModel):
    saved: bool
    article: SavedArticleOut


class SavedListOut(BaseModel):
    items: list[SavedArticleOut]
    total: int
    limit: int
    offset: int
    has_more: bool


class SavedStatusOut(BaseModel):
    saved: bool
    article_key: str
    article: SavedArticleOut | None = None


def _invalid_url(message: str) -> HTTPException:
    return HTTPException(
        422,
        detail={"code": "INVALID_SOURCE_URL", "message": message},
    )


@router.post("", response_model=SavedResultOut, summary="收藏一篇文章")
def save_article(payload: SavedInput, request: Request, response: Response) -> Any:
    identity = current_identity(request)
    try:
        source = canonicalize_zhihu_url(payload.source_url)
    except ValueError as exc:
        raise _invalid_url(str(exc)) from exc

    store = store_of(request)
    existed = store.is_article_saved(identity.user_id, source.article_key)
    article = store.save_article(
        identity.user_id,
        source,
        payload.title,
        payload.author_name,
    )
    if not existed:
        response.status_code = 201
    return {"saved": True, "article": article}


@router.get("", response_model=SavedListOut, summary="文章收藏列表")
def list_saved(
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> Any:
    identity = current_identity(request)
    items, total = store_of(request).list_saved_articles(
        identity.user_id, limit, offset
    )
    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(items) < total,
    }


@router.get("/status", response_model=SavedStatusOut, summary="查询当前文章是否已收藏")
def saved_status(request: Request, source_url: str = Query(min_length=1, max_length=2000)) -> Any:
    identity = current_identity(request)
    try:
        source = canonicalize_zhihu_url(source_url)
    except ValueError as exc:
        raise _invalid_url(str(exc)) from exc
    article = store_of(request).get_saved_article(identity.user_id, source.article_key)
    return {
        "saved": article is not None,
        "article_key": source.article_key,
        "article": article,
    }


@router.delete("/{article_key}", status_code=204, summary="取消收藏")
def remove_saved(article_key: str, request: Request) -> Response:
    identity = current_identity(request)
    if not store_of(request).remove_saved_article(identity.user_id, article_key):
        raise HTTPException(
            404,
            detail={"code": "SAVED_ARTICLE_NOT_FOUND", "message": "没有找到这条收藏。"},
        )
    return Response(status_code=204)
