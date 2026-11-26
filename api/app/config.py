from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

# OAuth 凭证按赛事手册流程，在「创建项目」后由赛事页面分配（预计 2026-12-05 开启）。
# 拿到后只需在项目根目录 .env 中填写 ZHIHU_OAUTH_APP_ID / ZHIHU_OAUTH_APP_KEY，重启后端即可。
# 真实密钥一律不进源码：Access Secret 也只放 .env（已被 .gitignore 忽略）。


def _cred_env(name: str) -> str:
    """读取凭证类配置；尖括号占位符（如 <待分配>）视为未配置。"""
    value = os.environ.get(name, "").strip()
    if value.startswith("<") and value.endswith(">"):
        return ""
    return value


def _bool_env(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name)
    try:
        value = int(raw) if raw is not None else default
    except ValueError as exc:
        raise ValueError(f"{name} 必须是整数。") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} 必须在 {minimum} 到 {maximum} 之间。")
    return value


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
    zhida_model: str = field(default="zhida-fast-1p5", kw_only=True)
    branch_ai_daily_budget: int = field(default=30, kw_only=True)
    branch_ai_user_budget: int = field(default=10, kw_only=True)
    branch_ai_min_interval: int = field(default=5, kw_only=True)
    branch_ai_concurrency: int = field(default=2, kw_only=True)
    branch_ai_quota_reserve: int = field(default=1, kw_only=True)
    branch_ai_allow_demo: bool = field(default=False, kw_only=True)
    # 生成模型提供方。目前只有 fake（确定性假模型）；接知乎直答时在这里切换。
    model_provider: str = "fake"
    deepseek_api_key: str = field(default="", repr=False)

    @classmethod
    def from_env(cls) -> "Settings":
        api_url = os.environ.get("THINKSPACE_API_URL", "http://localhost:8000").rstrip("/")
        return cls(
            access_secret=_cred_env("ZHIHU_ACCESS_SECRET"),
            oauth_app_id=_cred_env("ZHIHU_OAUTH_APP_ID"),
            oauth_app_key=_cred_env("ZHIHU_OAUTH_APP_KEY"),
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
            zhida_model=os.environ.get("THINKSPACE_ZHIDA_MODEL", "zhida-fast-1p5").strip(),
            branch_ai_daily_budget=_bounded_int("THINKSPACE_BRANCH_AI_DAILY_BUDGET", 30, 0, 10000),
            branch_ai_user_budget=_bounded_int("THINKSPACE_BRANCH_AI_USER_BUDGET", 10, 0, 1000),
            branch_ai_min_interval=_bounded_int("THINKSPACE_BRANCH_AI_MIN_INTERVAL", 5, 0, 3600),
            branch_ai_concurrency=_bounded_int("THINKSPACE_BRANCH_AI_CONCURRENCY", 2, 1, 32),
            branch_ai_quota_reserve=_bounded_int("THINKSPACE_BRANCH_AI_QUOTA_RESERVE", 1, 0, 10000),
            branch_ai_allow_demo=_bool_env("THINKSPACE_BRANCH_AI_ALLOW_DEMO", False),
            model_provider=os.environ.get("THINKSPACE_MODEL_PROVIDER", "fake"),
            deepseek_api_key=_cred_env("DEEPSEEK_API_KEY"),
        )

    @property
    def oauth_configured(self) -> bool:
        return bool(self.access_secret and self.oauth_app_id and self.oauth_app_key)

    def __post_init__(self) -> None:
        if self.zhida_model not in {"zhida-fast-1p5", "zhida-thinking-1p5"}:
            raise ValueError("THINKSPACE_ZHIDA_MODEL 需要选择快速档或深度思考档。")
