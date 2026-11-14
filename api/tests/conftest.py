from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402


def make_settings(tmp_path: Path, oauth_configured: bool = False) -> Settings:
    return Settings(
        access_secret="test-access-secret" if oauth_configured else "",
        oauth_app_id="test-app-id" if oauth_configured else "",
        oauth_app_key="test-app-key" if oauth_configured else "",
        oauth_redirect_uri="http://localhost:8000/api/auth/zhihu/callback",
        zhihu_api_base="https://developer.zhihu.com",
        zhihu_oauth_base="https://openapi.zhihu.com",
        web_url="http://localhost:5173",
        database_path=str(tmp_path / "test.db"),
        secret_key="test-secret-key",
        enable_demo=True,
        secure_cookie=False,
    )


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    with TestClient(create_app(make_settings(tmp_path))) as test_client:
        yield test_client
