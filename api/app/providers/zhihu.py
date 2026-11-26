from __future__ import annotations

import time
from typing import Any

import httpx

from ..config import Settings


class ZhihuError(Exception):
    def __init__(self, message: str, status_code: int = 502, code: str = "ZHIHU_API_ERROR") -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


class ZhihuClient:
    """知乎官方 HTTP 适配器；不读取网页 Cookie，也不调用私有 API。"""

    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.settings = settings
        self.transport = transport

    def _redact(self, value: str, oauth_token: str | None = None) -> str:
        result = value
        for secret in (self.settings.access_secret, self.settings.oauth_app_key, oauth_token):
            if secret:
                result = result.replace(secret, "***REDACTED***")
        return result

    async def exchange_authorization_code(self, code: str) -> dict[str, Any]:
        if not self.settings.oauth_configured:
            raise ZhihuError("知乎 OAuth 尚未配置。", 503, "OAUTH_NOT_CONFIGURED")
        try:
            async with httpx.AsyncClient(transport=self.transport, timeout=30) as client:
                response = await client.post(
                    f"{self.settings.zhihu_oauth_base}/access_token",
                    data={
                        "app_id": self.settings.oauth_app_id,
                        "app_key": self.settings.oauth_app_key,
                        "grant_type": "authorization_code",
                        "redirect_uri": self.settings.oauth_redirect_uri,
                        "code": code,
                    },
                )
        except httpx.HTTPError as exc:
            raise ZhihuError("连接知乎授权服务失败，请稍后重试。", 502, "OAUTH_NETWORK_ERROR") from exc
        payload = self._json(response)
        token = payload.get("access_token")
        if not token:
            message = self._redact(str(payload.get("error_description") or payload.get("message") or "授权码交换失败"))
            raise ZhihuError(message, 502, "OAUTH_TOKEN_EXCHANGE_FAILED")
        return {
            "access_token": str(token),
            "expires_at": int(time.time()) + int(payload.get("expires_in") or 3600),
        }

    def _json(self, response: httpx.Response, oauth_token: str | None = None) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise ZhihuError("知乎接口返回了非 JSON 内容。", 502, "ZHIHU_INVALID_RESPONSE") from exc
        if not isinstance(payload, dict):
            raise ZhihuError("知乎接口响应结构不符合约定。", 502, "ZHIHU_INVALID_RESPONSE")
        if response.status_code >= 400:
            detail = self._redact(response.text[:400], oauth_token)
            raise ZhihuError(f"知乎接口 HTTP {response.status_code}：{detail}", 502, "ZHIHU_HTTP_ERROR")
        return payload

    async def get_user_profile(self, oauth_token: str) -> dict[str, Any]:
        """黑客松专属接口：GET {oauth_base}/user，只带 OAuth token，无需 Access Secret。
        官方要求建立会话前确认响应包含有效用户标识，不使用空对象登录。
        """
        try:
            async with httpx.AsyncClient(transport=self.transport, timeout=30) as client:
                response = await client.get(
                    f"{self.settings.zhihu_oauth_base}/user",
                    headers={"Authorization": f"Bearer {oauth_token}"},
                )
        except httpx.HTTPError as exc:
            raise ZhihuError("连接知乎用户信息接口失败，请稍后重试。", 502, "ZHIHU_NETWORK_ERROR") from exc
        payload = self._json(response, oauth_token)
        code = payload.get("code")
        if code == 404 or "User don't exist" in str(payload.get("data", "")):
            raise ZhihuError("知乎未返回有效用户，登录未完成。", 502, "ZHIHU_PROFILE_INVALID")
        if code not in (None, 20000):
            detail = self._redact(str(payload.get("data") or payload)[:300], oauth_token)
            raise ZhihuError(f"知乎用户信息接口 Code={code}：{detail}", 502, "ZHIHU_PROFILE_ERROR")
        uid = payload.get("uid")
        if uid in (None, ""):
            raise ZhihuError("知乎未返回有效用户标识，登录未完成。", 502, "ZHIHU_PROFILE_INVALID")
        profile = dict(payload)
        profile["uid"] = str(uid)
        return profile

    def _platform_headers(self) -> dict[str, str]:
        if not self.settings.access_secret:
            raise ZhihuError("服务端未配置 ZHIHU_ACCESS_SECRET。", 503, "ZHIHU_NOT_CONFIGURED")
        return {
            "Authorization": f"Bearer {self.settings.access_secret}",
            "X-Request-Timestamp": str(int(time.time())),
            "Content-Type": "application/json",
        }

    async def _zhida_request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(transport=self.transport, timeout=httpx.Timeout(40, connect=8)) as client:
                response = await client.request(
                    method, f"{self.settings.zhihu_api_base}{path}", headers=self._platform_headers(), **kwargs
                )
        except httpx.TimeoutException:
            raise ZhihuError("知乎直答请求超时，可稍后重试。", 504, "ZHIDA_TIMEOUT") from None
        except httpx.HTTPError:
            raise ZhihuError("无法连接知乎开放平台。", 502, "ZHIDA_NETWORK") from None

        status = response.status_code
        try:
            payload = response.json()
        except ValueError:
            payload = None
        api_code = payload.get("Code") if isinstance(payload, dict) else None
        upstream = payload.get("error") if isinstance(payload, dict) else None
        error_code = str(upstream.get("code", "")).lower() if isinstance(upstream, dict) else ""
        if status == 402 or error_code in {"insufficient_quota", "quota_exceeded", "quota_exhausted"}:
            raise ZhihuError("知乎直答额度已用完。", 429, "ZHIDA_QUOTA_EXHAUSTED")
        if status in (401, 403) or api_code in (20001, "20001"):
            raise ZhihuError("知乎直答鉴权失败，请检查服务端凭证及模型权限。", 503, "ZHIDA_AUTH")
        if status == 429 or api_code in (30001, "30001"):
            raise ZhihuError("知乎直答正在限流，请稍后再试。", 429, "ZHIDA_RATE_LIMIT")
        if not response.is_success or api_code not in (None, 0, "0") or upstream:
            raise ZhihuError("知乎直答服务暂时不可用。", 502, "ZHIDA_UPSTREAM")
        if not isinstance(payload, dict):
            raise ZhihuError("知乎直答返回了无法识别的内容。", 502, "ZHIDA_INVALID_RESPONSE")
        return payload

    async def zhida_remaining(self) -> int:
        payload = await self._zhida_request("GET", "/api/v1/quota", params={"APIIDs": "zhida_openai"})
        data = payload.get("Data")
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get("APIID") == "zhida_openai":
                    remaining = item.get("RemainingQuota")
                    if type(remaining) is int and remaining >= 0:
                        return remaining
        raise ZhihuError("无法确认知乎直答免费额度，请检查开放平台配置。", 503, "ZHIDA_QUOTA_UNKNOWN")

    async def zhida_complete(self, messages: list[dict[str, str]]) -> str:
        payload = await self._zhida_request("POST", "/v1/chat/completions", json={
            "model": self.settings.zhida_model,
            "messages": messages,
            "stream": False,
        })
        try:
            choice = payload["choices"][0]
            content = choice["message"]["content"]
            if choice.get("finish_reason") != "error" and isinstance(content, str) and content.strip():
                return self._redact(content.strip())
        except (KeyError, IndexError, TypeError, AttributeError):
            pass
        raise ZhihuError("知乎直答没有返回可用正文。", 502, "ZHIDA_INVALID_RESPONSE")

    async def user_get(self, path: str, params: dict[str, Any], oauth_token: str) -> dict[str, Any]:
        headers = {**self._platform_headers(), "X-OAuth-Token": oauth_token}
        try:
            async with httpx.AsyncClient(transport=self.transport, timeout=30) as client:
                response = await client.get(
                    f"{self.settings.zhihu_api_base}{path}", params=params, headers=headers
                )
        except httpx.HTTPError as exc:
            raise ZhihuError("连接知乎数据服务失败，请稍后重试。", 502, "ZHIHU_NETWORK_ERROR") from exc
        payload = self._json(response, oauth_token)
        code = payload.get("Code")
        if code not in (None, 0):
            message = self._redact(str(payload.get("Message") or "未知业务错误"), oauth_token)
            status = 401 if code == 20001 else 502
            error_code = "ZHIHU_REAUTH_REQUIRED" if code == 20001 else "ZHIHU_BUSINESS_ERROR"
            raise ZhihuError(f"知乎接口 Code={code}：{message}", status, error_code)
        data = payload.get("Data")
        if not isinstance(data, dict):
            raise ZhihuError("知乎接口缺少 Data 对象。", 502, "ZHIHU_INVALID_RESPONSE")
        return data
