from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

# OAuth 凭证按赛事手册流程，在「创建项目」后由赛事页面分配（预计 2026-12-05 开启）。
# 拿到后只需在项目根目录 .env 中填写 ZHIHU_OAUTH_APP_ID / ZHIHU_OAUTH_APP_KEY，重启后端即可。
# 真实密钥一律不进源码：Access Secret 也只放 .env（已被 .gitignore 忽略）。


def _bool_env(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    access_secret: str
    oauth_app_id: str
    oauth_app_key: str
    oauth_redirect_uri: str
    zhihu_api_base: str
    zhihu_oauth_base: str
    web_url: str
    database_path: str
    secret_key: str
    enable_demo: bool
    secure_cookie: bool

    @classmethod
    def from_env(cls) -> "Settings":
        api_url = os.environ.get("THINKSPACE_API_URL", "http://localhost:8000").rstrip("/")
        return cls(
            access_secret=os.environ.get("ZHIHU_ACCESS_SECRET", "").strip(),
            oauth_app_id=os.environ.get("ZHIHU_OAUTH_APP_ID", "").strip(),
            oauth_app_key=os.environ.get("ZHIHU_OAUTH_APP_KEY", "").strip(),
            oauth_redirect_uri=os.environ.get(
                "ZHIHU_OAUTH_REDIRECT_URI", f"{api_url}/api/auth/zhihu/callback"
            ),
            zhihu_api_base=os.environ.get(
                "ZHIHU_OPENAPI_BASE_URL", "https://developer.zhihu.com"
            ).rstrip("/"),
            zhihu_oauth_base=os.environ.get(
                "ZHIHU_OAUTH_BASE_URL", "https://openapi.zhihu.com"
            ).rstrip("/"),
            web_url=os.environ.get("THINKSPACE_WEB_URL", "http://localhost:5173").rstrip("/"),
            database_path=os.environ.get(
                "THINKSPACE_DATABASE_PATH", str(PROJECT_ROOT / "data" / "thinkspace.db")
            ),
            secret_key=os.environ.get(
                "THINKSPACE_SECRET_KEY", "local-development-only-change-this-secret"
            ),
            enable_demo=_bool_env("THINKSPACE_ENABLE_DEMO", True),
            secure_cookie=_bool_env("THINKSPACE_SECURE_COOKIE", False),
        )

    @property
    def oauth_configured(self) -> bool:
        return bool(self.access_secret and self.oauth_app_id and self.oauth_app_key)
