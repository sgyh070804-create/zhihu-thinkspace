from fastapi.testclient import TestClient

from app.main import create_app
from conftest import make_settings


def add_bubble(client, number, title, body, quote=""):
    response = client.post("/api/bubbles", json={
        "source_url": f"https://zhuanlan.zhihu.com/p/{number}",
        "title": title, "body": body, "quote": quote,
    })
    assert response.status_code == 201
    return response.json()["id"]


def test_reading_recall_prioritizes_exact_match_and_uses_selected_text(client):
    assert client.post("/api/auth/demo").status_code == 200
    exact = add_bubble(client, 1001, "当前文章", "同篇记录即使没有关键词也要出现")
    adjacent = add_bubble(client, 1002, "页边记录", "读后心得", "主动回忆能够促进长期记忆")
    add_bubble(client, 1003, "山地自行车", "检查刹车和轮胎")
    response = client.post("/api/bubbles/recall", json={
        "source_url": "https://zhuanlan.zhihu.com/p/1001?utm_source=demo",
        "title": "关于阅读", "selection": "为什么主动回忆可以促进长期记忆？",
    })
    assert response.status_code == 200
    assert [(item["id"], item["match"]) for item in response.json()["items"]] == [
        (exact, "same_article"), (adjacent, "related"),
    ]


def test_recall_uses_paired_account_and_omits_unrelated_matches(client, tmp_path):
    query = {"source_url": "https://zhuanlan.zhihu.com/p/1001", "title": "证据检验与反例"}
    assert client.post("/api/bubbles/recall", json=query).status_code == 401
    client.post("/api/auth/demo")
    owned = add_bubble(client, 1001, "证据检验", "私有泡泡")
    pair_code = client.post("/api/extension/pair").json()["code"]
    token = client.post("/api/extension/exchange", json={"code": pair_code}).json()["extension_token"]
    with TestClient(create_app(make_settings(tmp_path))) as other:
        assert other.post("/api/auth/demo").status_code == 200
        add_bubble(other, 1002, "自行车", "刹车与变速")
        assert other.post("/api/bubbles/recall", json=query).json() == {"items": []}
        paired = other.post("/api/bubbles/recall", json=query, headers={"Authorization": f"Bearer {token}"})
        assert paired.status_code == 200
        assert [item["id"] for item in paired.json()["items"]] == [owned]
        assert other.post("/api/bubbles/recall", json={**query, "source_url": "https://example.com/"}).status_code == 422
