from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from . import demo
from .deps import current_identity, real_zhihu_identity, store_of


router = APIRouter(prefix="/api/zhihu", tags=["zhihu"])


CAPABILITIES = [
    {
        "key": "favorites",
        "name": "公开收藏",
        "status": "supported",
        "description": "公开收藏夹、收藏条目、近期收藏及摘要；不承诺私密收藏或全文。",
        "official_doc": "https://developer.zhihu.com/docs?key=user_favlists",
    },
    {
        "key": "creations",
        "name": "用户创作",
        "status": "supported",
        "description": "授权用户公开的回答、文章、视频、想法和问题，包含摘要与互动计数。",
        "official_doc": "https://developer.zhihu.com/docs?key=user_contents",
    },
    {
        "key": "followees",
        "name": "关注用户",
        "status": "supported",
        "description": "授权用户公开范围内的关注用户列表。",
        "official_doc": "https://developer.zhihu.com/docs?key=user_followees",
    },
    {
        "key": "likes",
        "name": "点赞历史",
        "status": "unavailable",
        "description": "当前官方公开用户数据文档未提供点赞历史接口。LikeCount 只是内容累计点赞数。",
        "official_doc": "https://developer.zhihu.com/docs",
    },
    {
        "key": "comments",
        "name": "评论历史",
        "status": "unavailable",
        "description": "当前官方公开用户数据文档未提供当前用户评论历史接口，不使用私有网页接口代替。",
        "official_doc": "https://developer.zhihu.com/docs",
    },
    {
        "key": "article_bubbles",
        "name": "文章与泡泡",
        "status": "local",
        "description": "扩展保存当前页标题、作者、规范链接、选中文字与用户想法，按内容类型和 ID 关联。",
        "official_doc": "",
    },
]


def _identity(request: Request):
    identity = current_identity(request)
    return identity if identity.mode == "demo" else real_zhihu_identity(request)


async def _get(request: Request, path: str, params: dict) -> dict:
    identity = _identity(request)
    return await request.app.state.zhihu.user_get(path, params, identity.oauth_token or "")


@router.get("/me")
def me(request: Request) -> dict:
    identity = current_identity(request)
    if identity.mode == "demo":
        return demo.PROFILE
    profile = store_of(request).get_profile(identity.user_id)
    if not profile:
        raise HTTPException(404, detail="尚未获取知乎用户信息，请重新授权。")
    return profile


@router.get("/capabilities")
def capabilities(request: Request) -> dict:
    current_identity(request)
    return {"items": CAPABILITIES}


@router.get("/favorites/lists")
async def favorite_lists(request: Request, limit: int = Query(20, ge=1, le=50)) -> dict:
    if _identity(request).mode == "demo":
        return demo.FAVLISTS
    return await _get(request, "/api/v1/user/favlists", {"Limit": limit})


@router.get("/favorites/recent")
async def recent_favorites(request: Request, limit: int = Query(20, ge=1, le=50)) -> dict:
    identity = _identity(request)
    if identity.mode == "demo":
        return {"Items": demo.ARTICLES[:limit]}
    return await _get(request, "/api/v1/user/collections", {"Limit": limit})


@router.get("/favorites/contents")
async def favorite_contents(
    request: Request,
    favlist_url_token: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=50),
) -> dict:
    identity = _identity(request)
    if identity.mode == "demo":
        return demo.page(demo.ARTICLES, offset, limit)
    return await _get(
        request,
        "/api/v1/user/favlist_contents",
        {"FavlistUrlToken": favlist_url_token, "Offset": offset, "Limit": limit},
    )


@router.get("/contents")
async def user_contents(
    request: Request,
    content_type: str = Query("all", pattern="^(all|answer|article|zvideo|pin|question)$"),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=50),
) -> dict:
    identity = _identity(request)
    if identity.mode == "demo":
        items = demo.CREATIONS if content_type == "all" else [
            item for item in demo.CREATIONS if item["ContentType"] == content_type
        ]
        return demo.page(items, offset, limit)
    return await _get(
        request,
        "/api/v1/user/contents",
        {"ContentType": content_type, "Offset": offset, "Limit": limit},
    )


@router.get("/followees")
async def followees(
    request: Request,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=50),
) -> dict:
    identity = _identity(request)
    if identity.mode == "demo":
        return demo.followees_page(offset, limit)
    return await _get(request, "/api/v1/user/followees", {"Offset": offset, "Limit": limit})


@router.get("/likes")
def likes(request: Request) -> dict:
    current_identity(request)
    raise HTTPException(
        501,
        detail={
            "code": "CAPABILITY_UNAVAILABLE",
            "message": "知乎当前公开用户数据文档未提供点赞历史接口，ThinkSpace 不会用累计点赞数冒充历史记录。",
        },
    )


@router.get("/comments")
def comments(request: Request) -> dict:
    current_identity(request)
    raise HTTPException(
        501,
        detail={
            "code": "CAPABILITY_UNAVAILABLE",
            "message": "知乎当前公开用户数据文档未提供评论历史接口，ThinkSpace 不会调用私有网页接口代替。",
        },
    )
