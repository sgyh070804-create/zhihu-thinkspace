from __future__ import annotations

import asyncio

import httpx

from app.providers.zhihu import ZhihuClient
from conftest import make_settings


def test_user_request_uses_both_credentials(tmp_path) -> None:
    observed = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed["path"] = request.url.path
        observed["params"] = dict(request.url.params)
        observed["authorization"] = request.headers.get("Authorization")
        observed["oauth"] = request.headers.get("X-OAuth-Token")
        observed["timestamp"] = request.headers.get("X-Request-Timestamp")
        return httpx.Response(200, json={"Code": 0, "Message": "success", "Data": {"Items": []}})

    settings = make_settings(tmp_path, oauth_configured=True)
    client = ZhihuClient(settings, transport=httpx.MockTransport(handler))
    result = asyncio.run(client.user_get("/api/v1/user/favlists", {"Limit": 20}, "user-token"))
    assert result == {"Items": []}
    assert observed["path"] == "/api/v1/user/favlists"
    assert observed["params"] == {"Limit": "20"}
    assert observed["authorization"] == "Bearer test-access-secret"
    assert observed["oauth"] == "user-token"
    assert observed["timestamp"].isdigit()


def test_oauth_exchange_accepts_documented_success_shape(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/access_token"
        return httpx.Response(
            200,
            json={"code": 20000, "access_token": "oauth-token", "expires_in": 3600},
        )

    settings = make_settings(tmp_path, oauth_configured=True)
    client = ZhihuClient(settings, transport=httpx.MockTransport(handler))
    result = asyncio.run(client.exchange_authorization_code("one-time-code"))
    assert result["access_token"] == "oauth-token"
    assert result["expires_at"] > 0


def test_user_profile_success_and_uid_lossless(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/user"
        assert request.headers.get("Authorization") == "Bearer user-token"
        return httpx.Response(
            200,
            json={
                "uid": 969570047710216200,
                "hash_id": "abc",
                "fullname": "测试用户",
                "headline": "一句话介绍",
                "avatar_path": "https://picx.zhimg.com/example.jpg",
                "url": "https://openapi.zhihu.com/users/969570047710216200",
            },
        )

    settings = make_settings(tmp_path, oauth_configured=True)
    client = ZhihuClient(settings, transport=httpx.MockTransport(handler))
    profile = asyncio.run(client.get_user_profile("user-token"))
    assert profile["uid"] == "969570047710216200"
    assert profile["fullname"] == "测试用户"


def test_user_profile_rejects_invalid_responses(tmp_path) -> None:
    from app.providers.zhihu import ZhihuError

    def user_not_found(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 404, "data": "User don't exist"})

    settings = make_settings(tmp_path, oauth_configured=True)
    client = ZhihuClient(settings, transport=httpx.MockTransport(user_not_found))
    try:
        asyncio.run(client.get_user_profile("user-token"))
    except ZhihuError as exc:
        assert exc.code == "ZHIHU_PROFILE_INVALID"
    else:
        raise AssertionError("用户不存在时不应建立登录会话")

    def no_uid(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 20000, "fullname": "缺 uid"})

    client = ZhihuClient(settings, transport=httpx.MockTransport(no_uid))
    try:
        asyncio.run(client.get_user_profile("user-token"))
    except ZhihuError as exc:
        assert exc.code == "ZHIHU_PROFILE_INVALID"
    else:
        raise AssertionError("缺少 uid 时不应建立登录会话")
