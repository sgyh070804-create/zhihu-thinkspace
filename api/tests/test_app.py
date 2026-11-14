from __future__ import annotations

from fastapi.testclient import TestClient

from app.content import canonicalize_zhihu_url
from app.main import create_app
from conftest import make_settings


def login_demo(client: TestClient) -> None:
    response = client.post("/api/auth/demo")
    assert response.status_code == 200
    assert response.json()["mode"] == "demo"


def test_health_and_demo_data(client: TestClient) -> None:
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/api/zhihu/favorites/lists").status_code == 401
    login_demo(client)
    lists = client.get("/api/zhihu/favorites/lists")
    assert lists.status_code == 200
    assert lists.json()["Items"][0]["Title"] == "演示收藏夹"
    contents = client.get("/api/zhihu/favorites/contents?favlist_url_token=90001")
    assert contents.status_code == 200
    assert len(contents.json()["Items"]) == 2
    assert client.get("/api/zhihu/likes").status_code == 501
    assert client.get("/api/zhihu/comments").status_code == 501


def test_bubble_normalizes_url_and_associates_article(client: TestClient) -> None:
    login_demo(client)
    source = "https://www.zhihu.com/question/10001/answer/20001?utm_source=share"
    first = client.post(
        "/api/bubbles",
        json={
            "source_url": source,
            "title": "文章标题",
            "author_name": "作者",
            "body": "我的第一个疑问",
            "quote": "用户主动选中的文字",
        },
    )
    assert first.status_code == 201
    assert first.json()["source_url"] == "https://www.zhihu.com/question/10001/answer/20001"
    assert first.json()["article_key"] == "answer:20001"
    second = client.post(
        "/api/bubbles",
        json={"source_url": source + "#comment", "body": "同一文章的第二个想法"},
    )
    assert second.status_code == 201
    articles = client.get("/api/articles").json()["items"]
    assert len(articles) == 1
    assert articles[0]["bubble_count"] == 2
    related = client.get("/api/bubbles", params={"source_url": source}).json()["items"]
    assert len(related) == 2


def test_user_isolation_and_extension_pairing(client: TestClient, tmp_path) -> None:
    login_demo(client)
    created = client.post(
        "/api/bubbles",
        json={"source_url": "https://zhuanlan.zhihu.com/p/30001", "body": "只属于当前用户"},
    )
    assert created.status_code == 201
    pair = client.post("/api/extension/pair")
    assert pair.status_code == 200

    extension = TestClient(create_app(make_settings(tmp_path)))
    # 使用同一应用实例模拟扩展请求，避免不同数据库造成的无关干扰。
    extension.close()
    token_response = client.post("/api/extension/exchange", json={"code": pair.json()["code"]})
    assert token_response.status_code == 200
    token = token_response.json()["extension_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert len(client.get("/api/bubbles", headers=headers).json()["items"]) == 1

    other = TestClient(client.app)
    login_demo(other)
    assert other.get("/api/articles").json()["items"] == []
    assert other.delete(f"/api/bubbles/{created.json()['id']}").status_code == 404


def test_oauth_start_requires_configuration_and_sets_transaction(tmp_path) -> None:
    unconfigured = TestClient(create_app(make_settings(tmp_path)))
    assert unconfigured.get("/api/auth/zhihu/start", follow_redirects=False).status_code == 503

    configured = TestClient(create_app(make_settings(tmp_path, oauth_configured=True)))
    response = configured.get("/api/auth/zhihu/start", follow_redirects=False)
    assert response.status_code == 302
    location = response.headers["location"]
    assert location.startswith("https://openapi.zhihu.com/authorize?")
    assert "app_id=test-app-id" in location
    assert "state=" in location
    assert "thinkspace_oauth_tx" in response.headers["set-cookie"]


def test_canonicalization_rejects_unrelated_urls() -> None:
    try:
        canonicalize_zhihu_url("https://example.com/question/1/answer/2")
    except ValueError:
        pass
    else:
        raise AssertionError("非知乎链接不应被接受")


def test_demo_pagination_load_more(client: TestClient) -> None:
    login_demo(client)
    first = client.get("/api/zhihu/followees?offset=0&limit=5")
    assert first.status_code == 200
    body = first.json()
    assert len(body["Items"]) == 5
    assert body["Paging"]["IsEnd"] is False
    assert body["Paging"]["NextOffset"] == "5"
    second = client.get("/api/zhihu/followees?offset=5&limit=5")
    second_body = second.json()
    assert len(second_body["Items"]) == 3
    assert second_body["Paging"]["IsEnd"] is True

    page1 = client.get("/api/zhihu/contents?content_type=all&offset=0&limit=5")
    assert len(page1.json()["Items"]) == 5
    assert page1.json()["Paging"]["NextOffset"] == "5"
    page2 = client.get("/api/zhihu/contents?content_type=all&offset=10&limit=5")
    assert len(page2.json()["Items"]) == 2
    assert page2.json()["Paging"]["IsEnd"] is True
