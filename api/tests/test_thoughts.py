from uuid import uuid4

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
