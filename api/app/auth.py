from __future__ import annotations

import time
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from .deps import OAUTH_TX_COOKIE, SESSION_COOKIE, optional_identity, settings_of, store_of


router = APIRouter(prefix="/api/auth", tags=["auth"])


def _set_cookie(response: Response, name: str, value: str, max_age: int, secure: bool) -> None:
    response.set_cookie(
        name,
        value,
        max_age=max_age,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )


@router.get("/zhihu/start")
def start_zhihu_oauth(request: Request) -> RedirectResponse:
    settings = settings_of(request)
    if not settings.oauth_configured:
        raise HTTPException(
            503,
            detail={
                "code": "OAUTH_NOT_CONFIGURED",
                "message": "请先配置 ZHIHU_ACCESS_SECRET、ZHIHU_OAUTH_APP_ID 和 ZHIHU_OAUTH_APP_KEY。",
            },
        )
    identity = optional_identity(request)
    transaction_id, state = store_of(request).create_oauth_transaction(
        identity.user_id if identity else None
    )
    query = urlencode(
        {
            "redirect_uri": settings.oauth_redirect_uri,
            "app_id": settings.oauth_app_id,
            "response_type": "code",
            "state": state,
        }
    )
    response = RedirectResponse(f"{settings.zhihu_oauth_base}/authorize?{query}", status_code=302)
    _set_cookie(response, OAUTH_TX_COOKIE, transaction_id, 600, settings.secure_cookie)
    return response


@router.get("/zhihu/callback")
async def zhihu_callback(
    request: Request,
    authorization_code: str | None = None,
    code: str | None = None,
    state: str | None = None,
) -> RedirectResponse:
    settings = settings_of(request)
    transaction_id = request.cookies.get(OAUTH_TX_COOKIE, "")
    if not transaction_id:
        raise HTTPException(400, detail="授权事务不存在，请从 ThinkSpace 重新发起登录。")
    try:
        user_id = store_of(request).consume_oauth_transaction(transaction_id, state)
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    auth_code = authorization_code or code
    if not auth_code:
        raise HTTPException(400, detail="知乎回调缺少 authorization_code。")
    token = await request.app.state.zhihu.exchange_authorization_code(auth_code)
    profile = await request.app.state.zhihu.get_user_profile(token["access_token"])
    raw_session, session_user = store_of(request).create_session(
        user_id=user_id,
        oauth_token=token["access_token"],
        oauth_expires_at=token["expires_at"],
    )
    store_of(request).save_profile(session_user, profile)
    response = RedirectResponse(f"{settings.web_url}/?auth=success", status_code=302)
    _set_cookie(response, SESSION_COOKIE, raw_session, 30 * 24 * 3600, settings.secure_cookie)
    response.delete_cookie(OAUTH_TX_COOKIE, path="/")
    return response


@router.post("/demo")
def demo_login(request: Request) -> JSONResponse:
    settings = settings_of(request)
    if not settings.enable_demo:
        raise HTTPException(404, detail="演示模式未启用。")
    raw_session, user_id = store_of(request).create_session(demo=True)
    response = JSONResponse({"authenticated": True, "mode": "demo", "user_id": user_id})
    _set_cookie(response, SESSION_COOKIE, raw_session, 30 * 24 * 3600, settings.secure_cookie)
    return response


@router.get("/status")
def auth_status(request: Request) -> dict:
    settings = settings_of(request)
    identity = optional_identity(request)
    return {
        "authenticated": identity is not None,
        "mode": identity.mode if identity else None,
        "user_id": identity.user_id if identity else None,
        "oauth_configured": settings.oauth_configured,
        "demo_enabled": settings.enable_demo,
        "oauth_expires_at": identity.oauth_expires_at if identity else None,
        "oauth_expired": bool(
            identity
            and identity.mode == "zhihu"
            and identity.oauth_expires_at
            and identity.oauth_expires_at <= int(time.time())
        ),
    }


@router.post("/logout")
def logout(request: Request) -> Response:
    raw_session = request.cookies.get(SESSION_COOKIE, "")
    if raw_session:
        store_of(request).delete_session(raw_session)
    response = JSONResponse({"authenticated": False})
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(OAUTH_TX_COOKIE, path="/")
    return response
