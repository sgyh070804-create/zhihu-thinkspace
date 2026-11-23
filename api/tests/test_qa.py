from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from conftest import make_settings
from app.qa import retrieve_sources


def login_demo(client: TestClient) -> None:
    response = client.post("/api/auth/demo")
    assert response.status_code == 200, response.text


def create_session(
    client: TestClient, token: int = 90001, title: str = "演示收藏夹"
) -> dict:
    response = client.post(
        "/api/qa/sessions",
        json={"favlist_url_token": token, "favlist_title": title},
    )
    assert response.status_code in (200, 201), response.text
    return response.json()


def ask(client: TestClient, session_id: str, question: str) -> dict:
    response = client.post(
        f"/api/qa/sessions/{session_id}/messages", json={"question": question}
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_create_and_ask_persists_messages_and_citations(client: TestClient) -> None:
    login_demo(client)
    session = create_session(client)

    body = ask(client, session["id"], "为什么阅读时需要记录疑问？")
    assert body["question"]["role"] == "user"
    assert body["answer"]["role"] == "assistant"
    assert body["answer"]["citations"], "命中的收藏摘要应作为引用返回"
    citation = body["answer"]["citations"][0]
    assert citation["source_url"].startswith("https://www.zhihu.com/")
    assert citation["snippet"]
    assert "摘要" in body["answer"]["body"]
    assert "不是全文" in body["answer"]["body"]
    assert body["session"]["message_count"] == 2

    detail = client.get(f"/api/qa/sessions/{session['id']}").json()
    assert [message["role"] for message in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][1]["citations"][0]["rank"] == 1


def test_no_match_is_explicit_and_has_no_citations(client: TestClient) -> None:
    login_demo(client)
    session = create_session(client)

    body = ask(client, session["id"], "量子纠缠和超导体的关系是什么？")
    assert body["answer"]["citations"] == []
    assert "没有找到" in body["answer"]["body"]
    assert "不能给出有依据的回答" in body["answer"]["body"]


def test_session_is_reused_per_favlist(client: TestClient) -> None:
    login_demo(client)
    first = create_session(client)
    second = create_session(client, title="演示收藏夹")
    assert second["id"] == first["id"]
    assert second["favlist_title"] == "演示收藏夹"


def test_qa_is_isolated_between_users(client: TestClient) -> None:
    login_demo(client)
    session = create_session(client)
    ask(client, session["id"], "为什么阅读时需要记录疑问？")

    other = TestClient(client.app)
    login_demo(other)
    assert other.get(f"/api/qa/sessions/{session['id']}").status_code == 404
    assert other.get("/api/qa/sessions").json()["items"] == []
    assert (
        other.post(
            f"/api/qa/sessions/{session['id']}/messages",
            json={"question": "为什么阅读时需要记录疑问？"},
        ).status_code
        == 404
    )


def test_qa_requires_login(client: TestClient) -> None:
    assert client.post("/api/qa/sessions", json={"favlist_url_token": 90001}).status_code == 401
    assert client.get("/api/qa/sessions").status_code == 401


def test_qa_history_survives_new_app_instance(client: TestClient, tmp_path) -> None:
    login_demo(client)
    session = create_session(client)
    ask(client, session["id"], "为什么阅读时需要记录疑问？")
    cookie = client.cookies.get("thinkspace_session")
    assert cookie

    reopened = TestClient(create_app(make_settings(tmp_path)))
    reopened.cookies.set("thinkspace_session", cookie)
    detail = reopened.get(f"/api/qa/sessions/{session['id']}")
    assert detail.status_code == 200, detail.text
    assert len(detail.json()["messages"]) == 2


def test_question_validation(client: TestClient) -> None:
    login_demo(client)
    session = create_session(client)
    response = client.post(
        f"/api/qa/sessions/{session['id']}/messages", json={"question": "   "}
    )
    assert response.status_code == 422


def test_retrieve_prefers_title_matches() -> None:
    items = [
        {"Title": "AI 与人的判断", "Summary": "关于判断的讨论", "Url": "https://www.zhihu.com/p/1"},
        {"Title": "完全无关", "Summary": "别的内容", "Url": "https://www.zhihu.com/p/2"},
    ]
    sources = retrieve_sources("人的判断", items)
    assert len(sources) >= 1
    assert sources[0]["source_url"] == "https://www.zhihu.com/p/1"
