from __future__ import annotations

from fastapi.testclient import TestClient


def login_demo(client: TestClient) -> None:
    response = client.post("/api/auth/demo")
    assert response.status_code == 200, response.text


def save(client: TestClient, url: str, **extra) -> dict:
    response = client.post(
        "/api/saved",
        json={"source_url": url, **extra},
    )
    assert response.status_code in (200, 201), response.text
    return response.json()["article"]


def test_save_normalizes_url_and_lists(client: TestClient) -> None:
    login_demo(client)
    article = save(
        client,
        "https://www.zhihu.com/question/10001/answer/20001?utm_source=share",
        title="一篇文章",
        author_name="作者",
    )
    assert article["article_key"] == "answer:20001"
    assert article["source_url"] == "https://www.zhihu.com/question/10001/answer/20001"
    assert article["title"] == "一篇文章"

    listing = client.get("/api/saved").json()
    assert listing["total"] == 1
    assert listing["items"][0]["article_key"] == article["article_key"]

    status = client.get(
        "/api/saved/status",
        params={"source_url": "https://www.zhihu.com/question/10001/answer/20001"},
    ).json()
    assert status["saved"] is True
    assert status["article_key"] == "answer:20001"


def test_repeat_save_is_idempotent(client: TestClient) -> None:
    login_demo(client)
    url = "https://zhuanlan.zhihu.com/p/30001"
    first = save(client, url)
    second = save(client, url, title="补全标题")
    assert second["article_key"] == first["article_key"]
    assert second["saved_at"] == first["saved_at"], "重复收藏不应刷新首次收藏时间"
    assert second["title"] == "补全标题"
    assert client.get("/api/saved").json()["total"] == 1


def test_remove_saved_article(client: TestClient) -> None:
    login_demo(client)
    article = save(client, "https://www.zhihu.com/pin/40001")
    response = client.delete(f"/api/saved/{article['article_key']}")
    assert response.status_code == 204
    assert client.get("/api/saved").json()["items"] == []
    assert client.delete(f"/api/saved/{article['article_key']}").status_code == 404


def test_saved_articles_are_isolated(client: TestClient) -> None:
    login_demo(client)
    save(client, "https://www.zhihu.com/zvideo/50001")

    other = TestClient(client.app)
    login_demo(other)
    assert other.get("/api/saved").json()["items"] == []
    assert other.delete("/api/saved/zvideo:50001").status_code == 404


def test_saved_article_survives_bubble_deletion(client: TestClient) -> None:
    login_demo(client)
    url = "https://www.zhihu.com/question/10002/answer/20002"
    save(client, url)
    bubble = client.post("/api/bubbles", json={"source_url": url, "body": "一条想法"})
    assert bubble.status_code == 201
    assert client.delete(f"/api/bubbles/{bubble.json()['id']}").status_code == 204
    # 收藏和泡泡是两件事：删泡泡不能把收藏一起删掉。
    assert client.get("/api/saved").json()["total"] == 1


def test_extension_token_can_save(client: TestClient) -> None:
    login_demo(client)
    pair = client.post("/api/extension/pair").json()
    token = client.post(
        "/api/extension/exchange", json={"code": pair["code"]}
    ).json()["extension_token"]
    response = client.post(
        "/api/saved",
        json={"source_url": "https://www.zhihu.com/question/10003/answer/20003"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201, response.text


def test_invalid_url_and_auth(client: TestClient) -> None:
    assert client.post("/api/saved", json={"source_url": "https://example.com/x"}).status_code == 401
    login_demo(client)
    assert client.post("/api/saved", json={"source_url": "https://example.com/x"}).status_code == 422
