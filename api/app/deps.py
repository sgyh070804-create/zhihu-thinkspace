from __future__ import annotations

import time
from dataclasses import dataclass

from fastapi import HTTPException, Request

from .config import Settings
from .store import Store


SESSION_COOKIE = "thinkspace_session"
OAUTH_TX_COOKIE = "thinkspace_oauth_tx"


@dataclass(frozen=True)
class Identity:
    user_id: str
    mode: str
    oauth_token: str | None = None
    oauth_expires_at: int | None = None
    via_extension: bool = False


def settings_of(request: Request) -> Settings:
    return request.app.state.settings


def store_of(request: Request) -> Store:
    return request.app.state.store


def optional_identity(request: Request) -> Identity | None:
    authorization = request.headers.get("Authorization", "")
    if authorization.startswith("Bearer "):
        token = authorization[7:].strip()
        user_id = store_of(request).get_extension_user(token)
        return Identity(user_id=user_id, mode="extension", via_extension=True) if user_id else None
    session = store_of(request).get_session(request.cookies.get(SESSION_COOKIE, ""))
    if not session:
        return None
    return Identity(
        user_id=session["user_id"],
        mode="demo" if session["is_demo"] else "zhihu",
        oauth_token=session["oauth_token"],
        oauth_expires_at=session["oauth_expires_at"],
    )


def current_identity(request: Request) -> Identity:
    identity = optional_identity(request)
    if not identity:
        raise HTTPException(401, detail={"code": "AUTH_REQUIRED", "message": "请先登录 ThinkSpace。"})
    return identity


def real_zhihu_identity(request: Request) -> Identity:
    identity = current_identity(request)
    if identity.mode == "demo":
        raise HTTPException(400, detail={"code": "DEMO_MODE", "message": "演示身份不能访问真实知乎数据。"})
    if not identity.oauth_token or (
        identity.oauth_expires_at and identity.oauth_expires_at <= int(time.time())
    ):
        raise HTTPException(
            401,
            detail={"code": "ZHIHU_REAUTH_REQUIRED", "message": "知乎授权已过期，请重新授权。"},
        )
    return identity
