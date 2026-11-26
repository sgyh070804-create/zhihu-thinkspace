import json
from dataclasses import replace
from uuid import uuid4

import httpx

from fastapi.testclient import TestClient

from app.main import create_app
from conftest import make_settings


def sign_in(client: TestClient) -> None:
    assert client.post("/api/auth/demo").status_code == 200


def save(client: TestClient, body: str, **fields):
    return client.post("/api/thoughts", json={"request_id": str(uuid4()), "body": body, **fields})


def test_reading_notes_and_library_thoughts_share_ids_and_keep_provenance_after_restart(tmp_path):
    settings = make_settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        sign_in(client)
        bubble = client.post("/api/bubbles", json={
            "source_url": "https://zhuanlan.zhihu.com/p/12345?utm_source=demo",
            "title": "阅读原文", "body": "这是原始手记", "quote": "一段引用",
        }).json()
        original = client.get(f"/api/thoughts/{bubble['id']}").json()
        assert original["id"] == bubble["id"]
        assert original["article_key"] == bubble["article_key"]
        assert original["source_title"] == "阅读原文"
        assert original["quote"] == "一段引用"
        assert original["kind"] == "reading"

        manual = save(client, "来自资料库的新想法", title="资料库记录").json()
        fusion_response = save(client, "两个想法汇在一起", kind="fusion", parent_ids=[bubble["id"], manual["id"]])
        assert fusion_response.status_code == 201
        fusion = fusion_response.json()
        assert fusion["source_url"] == "https://zhuanlan.zhihu.com/p/12345"
        assert fusion["parent_ids"] == [bubble["id"], manual["id"]]
        branch = save(client, "改变条件后的判断", kind="branch", parent_ids=[fusion["id"]]).json()
        discussion = save(client, "讨论形成的想法", kind="discussion", parent_ids=[branch["id"]]).json()
        revision = save(client, "重新整理讨论结果", kind="revision", parent_ids=[discussion["id"]]).json()
        cookies = dict(client.cookies)

    with TestClient(create_app(settings), cookies=cookies) as client:
        records = {item["id"]: item for item in client.get("/api/thoughts").json()["items"]}
        assert set(records) == {bubble["id"], manual["id"], fusion["id"], branch["id"], discussion["id"], revision["id"]}
        assert records[discussion["id"]]["parent_ids"] == [branch["id"]]
        assert records[discussion["id"]]["source_url"] == original["source_url"]
        assert records[discussion["id"]]["body"] == "讨论形成的想法"
        assert records[revision["id"]]["parent_ids"] == [discussion["id"]]


def test_thought_ownership_and_save_retries(client, tmp_path):
    assert client.get("/api/thoughts").status_code == 401
    sign_in(client)
    key = str(uuid4())
    first = save(client, "私有思绪", request_id=key)
    assert first.status_code == 201
    thought = first.json()
    assert save(client, "私有思绪", request_id=key).json()["id"] == thought["id"]
    assert len(client.get("/api/thoughts").json()["items"]) == 1
    assert save(client, "无效融合", kind="fusion", parent_ids=[thought["id"], thought["id"]]).status_code == 422

    with TestClient(create_app(make_settings(tmp_path))) as other:
        sign_in(other)
        assert other.get("/api/thoughts").json() == {"items": []}
        assert other.get(f"/api/thoughts/{thought['id']}").status_code == 404
        assert save(other, "跨账号引用", kind="branch", parent_ids=[thought["id"]]).status_code == 404


def test_fusion_draft_calls_flash_and_only_saves_after_confirmation(tmp_path, monkeypatch):
    replies = []

    def post(url, **kwargs):
        assert url == "https://api.deepseek.com/chat/completions"
        assert kwargs["headers"]["Authorization"] == "Bearer test-only"
        assert kwargs["follow_redirects"] is False
        payload = kwargs["json"]
        assert payload["model"] == "deepseek-flash"
        assert "thinking" not in payload
        contents = json.loads(payload["messages"][1]["content"])
        assert contents["messages"] == [{"body": "先验证假设"}, {"body": "再逐步投入"}]
        replies.append(payload)
        return httpx.Response(200, request=httpx.Request("POST", url), json={"choices": [{
            "finish_reason": "stop", "message": {"content": "用最低成本验证关键假设，再逐步加大投入。"},
        }]})

    monkeypatch.setattr("app.providers.model.httpx.post", post)
    settings = replace(make_settings(tmp_path), deepseek_api_key="test-only")
    with TestClient(create_app(settings)) as client:
        sign_in(client)
        parents = [save(client, text).json()["id"] for text in ("先验证假设", "再逐步投入")]
        payload = {"parent_ids": parents}
        response = client.post("/api/thoughts/fusion-draft", json=payload)
        assert response.status_code == 200
        assert response.json()["body"] == "用最低成本验证关键假设，再逐步加大投入。"
        assert len(client.get("/api/thoughts").json()["items"]) == 2

        with TestClient(create_app(settings)) as other:
            assert other.post("/api/thoughts/fusion-draft", json=payload).status_code == 401
            sign_in(other)
            assert other.post("/api/thoughts/fusion-draft", json=payload).status_code == 404
        assert client.post("/api/thoughts/fusion-draft", json={"parent_ids": [parents[0]] * 2}).status_code == 422
        assert len(replies) == 1

        saved = save(client, "我修改了 AI 的草稿。", kind="fusion", parent_ids=parents)
        assert saved.status_code == 201
        assert saved.json()["parent_ids"] == parents


def test_fusion_draft_unavailable_leaves_manual_save_usable(tmp_path, monkeypatch):
    def unavailable(url, **kwargs):
        return httpx.Response(429, request=httpx.Request("POST", url))

    monkeypatch.setattr("app.providers.model.httpx.post", unavailable)
    settings = make_settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        sign_in(client)
        parents = [save(client, text).json()["id"] for text in ("先验证", "再行动")]
        cookies = dict(client.cookies)
        assert client.post("/api/thoughts/fusion-draft", json={"parent_ids": parents}).status_code == 503

    with TestClient(create_app(replace(settings, deepseek_api_key="test-only")), cookies=cookies) as client:
        assert client.post("/api/thoughts/fusion-draft", json={"parent_ids": parents}).status_code == 502
        assert save(client, "手工合成", kind="fusion", parent_ids=parents).status_code == 201
