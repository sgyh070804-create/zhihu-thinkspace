from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from app.main import create_app
from app.store import Store
from conftest import make_settings


class FakeZhihu:
    async def exchange_authorization_code(self, code):
        return {"access_token": code, "expires_at": int(time.time()) + 3600}

    async def get_user_profile(self, token):
        return {"uid": token, "fullname": "测试账号 " + token}


def login(client: TestClient, uid: str) -> str:
    response = client.get("/api/auth/zhihu/start", follow_redirects=False)
    state = parse_qs(urlparse(response.headers["location"]).query)["state"][0]
    callback = client.get("/api/auth/zhihu/callback", params={"authorization_code": uid, "state": state}, follow_redirects=False)
    assert callback.status_code == 302
    return client.get("/api/auth/status").json()["user_id"]


def save_note(client: TestClient):
    result = client.post("/api/bubbles", json={"source_url": "https://zhuanlan.zhihu.com/p/30001", "body": "只属于账号 A 的想法"})
    assert result.status_code == 201
    return result.json()["id"]


def app_with_provider(tmp_path):
    app = create_app(make_settings(tmp_path, oauth_configured=True))
    app.state.zhihu = FakeZhihu()
    return app


def test_same_zhihu_account_reuses_its_data_across_browsers(tmp_path):
    app = app_with_provider(tmp_path)
    with TestClient(app) as first, TestClient(app) as second:
        first_id = login(first, "account-a")
        note = save_note(first)
        assert login(second, "account-a") == first_id
        assert second.get("/api/bubbles").json()["items"][0]["id"] == note


def test_switching_provider_accounts_never_reassigns_private_notes(tmp_path):
    with TestClient(app_with_provider(tmp_path)) as client:
        account_a = login(client, "account-a")
        note = save_note(client)
        assert login(client, "account-b") != account_a
        assert client.get("/api/bubbles").json()["items"] == []
        assert client.delete("/api/bubbles/" + note).status_code == 404
        assert login(client, "account-a") == account_a
        assert client.get("/api/bubbles").json()["items"][0]["id"] == note


def test_unbound_demo_user_can_attach_to_one_new_provider_account(tmp_path):
    with TestClient(app_with_provider(tmp_path)) as client:
        demo = client.post("/api/auth/demo").json()["user_id"]
        note = save_note(client)
        assert login(client, "new-account") == demo
        assert client.get("/api/bubbles").json()["items"][0]["id"] == note
        assert login(client, "different-account") != demo
        assert client.get("/api/bubbles").json()["items"] == []


def test_existing_provider_account_does_not_silently_merge_demo_data(tmp_path):
    app = app_with_provider(tmp_path)
    with TestClient(app) as owner, TestClient(app) as demo:
        account = login(owner, "account-a")
        demo.post("/api/auth/demo")
        save_note(demo)
        assert login(demo, "account-a") == account
        assert demo.get("/api/bubbles").json()["items"] == []


def test_concurrent_logins_share_one_provider_user(tmp_path):
    store = Store(str(tmp_path / "concurrent.db"), "test-only-secret")
    def signin(_):
        return store.create_zhihu_session({"uid": "same-account"}, "fake-token", int(time.time()) + 3600)[1]
    with ThreadPoolExecutor(max_workers=4) as pool:
        users = list(pool.map(signin, range(8)))
    assert len(set(users)) == 1


def test_database_file_is_released_after_operations(tmp_path):
    path = tmp_path / "released.db"
    store = Store(str(path), "test-only-secret")
    token, _ = store.create_session(demo=True)
    assert store.get_session(token)
    # On Windows an unclosed SQLite connection prevents this rename/removal.
    moved = path.with_suffix(".moved")
    path.rename(moved)
    moved.unlink()
    assert not path.exists() and not moved.exists()
