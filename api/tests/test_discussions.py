from __future__ import annotations

import asyncio
import ast
import sqlite3
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import discussion_store
from app.discussion_store import DiscussionNotFound, DiscussionStore
from app.main import create_app
from app.store import Store
from conftest import make_settings

DEFAULT_ROLES = {"explorer", "skeptic", "weaver", "user"}


# ---------------- 辅助 ----------------


def login_demo(client: TestClient) -> None:
    response = client.post("/api/auth/demo")
    assert response.status_code == 200, response.text


def new_discussion(client: TestClient, topic: str = "AI 应该替我们做决定吗？") -> dict:
    response = client.post("/api/discussions", json={"topic": topic})
    assert response.status_code == 201, response.text
    return response.json()


def send(client: TestClient, discussion_id: str, body: str, **extra) -> dict:
    response = client.post(f"/api/discussions/{discussion_id}/messages", json={"body": body, **extra})
    assert response.status_code in (200, 201), response.text
    return response.json()


# ---------------- 创建与查询 ----------------


def test_create_discussion_seats_default_roles(client: TestClient) -> None:
    login_demo(client)
    discussion = new_discussion(client)
    assert discussion["status"] == "active"
    assert discussion["max_turns"] == 6
    assert discussion["turn_index"] == 0
    assert discussion["message_seq"] == 0
    assert discussion["message_count"] == 0
    assert discussion["paused_at"] is None and discussion["stopped_at"] is None
    assert {item["role_id"] for item in discussion["participants"]} == DEFAULT_ROLES
    seats = [item["seat"] for item in discussion["participants"]]
    assert seats == sorted(seats)
    explorer = next(p for p in discussion["participants"] if p["role_id"] == "explorer")
    assert explorer["display_name"] == "探索者"
    assert explorer["title"] == "寻找另一种可能"


def test_create_discussion_role_subset_keeps_user(client: TestClient) -> None:
    login_demo(client)
    response = client.post("/api/discussions", json={"topic": "只请探索者", "role_ids": ["explorer"]})
    assert response.status_code == 201
    roles = {p["role_id"] for p in response.json()["participants"]}
    assert roles == {"explorer", "user"}, "用户必须始终在座，否则无法发言"


def test_create_discussion_rejects_unknown_role(client: TestClient) -> None:
    login_demo(client)
    response = client.post(
        "/api/discussions", json={"topic": "角色校验", "role_ids": ["explorer", "ghost"]}
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "UNKNOWN_ROLE"
    assert "ghost" in detail["message"]
    assert "explorer" in detail["known_roles"]


def test_create_discussion_validates_topic(client: TestClient) -> None:
    login_demo(client)
    assert client.post("/api/discussions", json={"topic": ""}).status_code == 422
    assert client.post("/api/discussions", json={"topic": "   "}).status_code == 422
    assert client.post("/api/discussions", json={"topic": "\n\t "}).status_code == 422
    assert client.post("/api/discussions", json={"topic": "x" * 201}).status_code == 422
    assert client.post("/api/discussions", json={"topic": "主题\x00空字符"}).status_code == 422

    padded = client.post("/api/discussions", json={"topic": "  有内容的主题  "})
    assert padded.status_code == 201
    assert padded.json()["topic"] == "有内容的主题", "首尾空白应被去掉"


def test_create_discussion_validates_max_turns(client: TestClient) -> None:
    login_demo(client)
    assert client.post("/api/discussions", json={"topic": "x", "max_turns": 0}).status_code == 422
    assert client.post("/api/discussions", json={"topic": "x", "max_turns": 21}).status_code == 422
    assert client.post("/api/discussions", json={"topic": "x", "max_turns": 20}).status_code == 201


def test_endpoints_require_login(client: TestClient) -> None:
    assert client.get("/api/discussions").status_code == 401
    assert client.get("/api/discussions/x").status_code == 401
    assert client.get("/api/discussions/x/messages").status_code == 401
    assert client.get("/api/discussions/x/events").status_code == 401
    assert client.get("/api/discussions/x/stream").status_code == 401
    assert client.post("/api/discussions", json={"topic": "x"}).status_code == 401
    assert client.post("/api/discussions/x/messages", json={"body": "x"}).status_code == 401
    assert client.post("/api/discussions/x/pause").status_code == 401
    assert client.post("/api/discussions/x/resume").status_code == 401
    assert client.post("/api/discussions/x/stop").status_code == 401
    assert client.post("/api/discussions/x/finish").status_code == 401


def test_get_unknown_discussion_returns_404(client: TestClient) -> None:
    login_demo(client)
    assert client.get("/api/discussions/not-a-real-id").status_code == 404
    assert client.get("/api/discussions/not-a-real-id").json()["detail"]["code"] == (
        "DISCUSSION_NOT_FOUND"
    )


def test_list_discussions_pagination(client: TestClient) -> None:
    login_demo(client)
    for index in range(3):
        new_discussion(client, topic=f"话题 {index}")

    first_page = client.get("/api/discussions", params={"limit": 2}).json()
    assert first_page["total"] == 3
    assert len(first_page["items"]) == 2
    assert first_page["has_more"] is True
    assert first_page["next_cursor"], "还有更多时应返回游标"

    second_page = client.get(
        "/api/discussions", params={"limit": 2, "cursor": first_page["next_cursor"]}
    ).json()
    assert len(second_page["items"]) == 1
    assert second_page["has_more"] is False
    assert second_page["next_cursor"] is None
    assert second_page["items"][0]["topic"] == "话题 0", "按创建时间倒序，最早的在最后"

    # offset 仍然可用，兼容旧调用
    legacy = client.get("/api/discussions", params={"limit": 2, "offset": 2}).json()
    assert [item["id"] for item in legacy["items"]] == [
        item["id"] for item in second_page["items"]
    ]

    assert client.get("/api/discussions", params={"limit": 0}).status_code == 422
    assert client.get("/api/discussions", params={"limit": 101}).status_code == 422


def test_cursor_pagination_returns_every_item_exactly_once(client: TestClient) -> None:
    """走完所有页，ID 序列必须和一次性读取完全一致：不重、不漏、顺序相同。

    只断言「两页不重复」是不够的——第二页返回空列表也能通过。
    """
    login_demo(client)
    for index in range(7):
        new_discussion(client, topic=f"项目 {index}")

    expected = [
        item["id"]
        for item in client.get("/api/discussions", params={"limit": 100}).json()["items"]
    ]
    assert len(expected) == 7

    collected, cursor, pages = [], None, 0
    while True:
        params = {"limit": 2}
        if cursor:
            params["cursor"] = cursor
        data = client.get("/api/discussions", params=params).json()
        collected += [item["id"] for item in data["items"]]
        pages += 1
        assert pages < 20, "翻页次数异常，可能游标没有推进"
        cursor = data["next_cursor"]
        if not cursor:
            break

    assert collected == expected, "完整翻页应与一次性读取得到相同序列"
    assert len(set(collected)) == 7


def test_invalid_cursor_is_rejected_not_silently_reset(client: TestClient) -> None:
    """游标非法时返回 422，不能静默回退第一页——否则客户端会一直翻同一页。"""
    import base64

    login_demo(client)
    new_discussion(client)

    def encode(raw: str) -> str:
        return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")

    bad_cursors = [
        "not-a-cursor",
        "",
        encode("abc"),
        encode("1:2:3"),
        encode(f"{2**63}:0"),      # 超出 SQLite INTEGER
        encode("-1:0"),             # 负数
    ]
    for bad in bad_cursors:
        response = client.get("/api/discussions", params={"cursor": bad})
        assert response.status_code == 422, f"游标 {bad!r} 应被拒绝"
        assert response.json()["detail"]["code"] == "INVALID_CURSOR"


def test_legacy_database_with_data_is_upgraded_in_place(tmp_path: Path) -> None:
    """已有数据、没有 schema_migrations 记录的旧库：数据保留，只补写版本。"""
    path = str(tmp_path / "legacy-v3.db")
    legacy = Store(path, "test-secret")
    _, user_id = legacy.create_session(demo=True)

    store = DiscussionStore(path)
    discussion = store.create_discussion(user_id, "旧库里的讨论")

    # 模拟旧版库：没有 schema_migrations 记录，只有全局 user_version
    connection = sqlite3.connect(path)
    try:
        connection.execute("DELETE FROM schema_migrations")
        connection.execute("PRAGMA user_version = 3")
        connection.commit()
    finally:
        connection.close()

    reopened = DiscussionStore(path)
    kept = reopened.get_discussion(user_id, discussion["id"])
    assert kept is not None, "升级不应清掉已有数据"
    assert kept["topic"] == "旧库里的讨论"

    connection = sqlite3.connect(path)
    try:
        row = connection.execute(
            "SELECT version FROM schema_migrations WHERE module = 'discussions'"
        ).fetchone()
    finally:
        connection.close()
    assert row is not None and row[0] == 3


def test_list_pagination_is_stable_when_new_discussion_inserted(
    client: TestClient,
) -> None:
    """翻页期间有人新建讨论时，游标分页不应重复或漏项。

    这正是 OFFSET 分页的问题：新记录插到最前面，第二页的 OFFSET 会整体后移一位，
    导致原来第二页的第一条被跳过。
    """
    login_demo(client)
    for index in range(4):
        new_discussion(client, topic=f"原有 {index}")

    first_page = client.get("/api/discussions", params={"limit": 2}).json()
    first_ids = [item["id"] for item in first_page["items"]]
    assert first_page["next_cursor"]

    # 在第一页和第二页之间插入一条新讨论（会排到列表最前面）
    new_discussion(client, topic="插队的新讨论")

    second_page = client.get(
        "/api/discussions", params={"limit": 2, "cursor": first_page["next_cursor"]}
    ).json()
    second_ids = [item["id"] for item in second_page["items"]]

    assert not set(first_ids) & set(second_ids), "两页不应出现重复项"
    topics = [item["topic"] for item in second_page["items"]]
    assert "插队的新讨论" not in topics, "比游标更新的记录不应出现在后续页"


# ---------------- 消息 ----------------


def test_message_sequence_and_order(client: TestClient) -> None:
    login_demo(client)
    discussion = new_discussion(client)
    first = send(client, discussion["id"], "第一句")
    assert first["created"] is True
    assert first["message"]["seq"] == 1
    assert first["message"]["role_id"] == "user"
    assert first["message"]["status"] == "completed"
    second = send(client, discussion["id"], "第二句")
    assert second["message"]["seq"] == 2

    detail = client.get(f"/api/discussions/{discussion['id']}").json()
    assert detail["message_seq"] == 2
    assert detail["message_count"] == 2

    items = client.get(f"/api/discussions/{discussion['id']}/messages").json()["items"]
    assert [item["seq"] for item in items] == [1, 2]
    assert [item["body"] for item in items] == ["第一句", "第二句"]


def test_message_idempotency(client: TestClient) -> None:
    login_demo(client)
    discussion = new_discussion(client)
    url = f"/api/discussions/{discussion['id']}/messages"
    payload = {"body": "网络抖动时重复提交的那句话", "client_msg_id": "local-1"}

    first = client.post(url, json=payload)
    assert first.status_code == 201

    second = client.post(url, json=payload)
    assert second.status_code == 200, "幂等命中应返回 200 而不是 201"
    assert second.json()["created"] is False
    assert second.json()["message"]["id"] == first.json()["message"]["id"]

    third = client.post(url, json={"body": "内容被改过", "client_msg_id": "local-1"})
    assert third.status_code == 200
    assert third.json()["message"]["body"] == "网络抖动时重复提交的那句话", "幂等键代表同一次提交"

    items = client.get(url).json()["items"]
    assert len(items) == 1


def test_message_without_client_id_is_not_deduplicated(client: TestClient) -> None:
    login_demo(client)
    discussion = new_discussion(client)
    send(client, discussion["id"], "同样的话")
    send(client, discussion["id"], "同样的话")
    items = client.get(f"/api/discussions/{discussion['id']}/messages").json()["items"]
    assert len(items) == 2, "没有幂等键时，内容相同也是两次独立发言"


def test_message_empty_client_id_behaves_like_absent(client: TestClient) -> None:
    login_demo(client)
    discussion = new_discussion(client)
    url = f"/api/discussions/{discussion['id']}/messages"
    first = client.post(url, json={"body": "第一条", "client_msg_id": ""})
    second = client.post(url, json={"body": "第二条", "client_msg_id": "   "})
    assert first.status_code == 201
    assert second.status_code == 201, "空幂等键应按未提供处理，不能撞唯一索引"
    items = client.get(url).json()["items"]
    assert len(items) == 2
    assert [item["client_msg_id"] for item in items] == [None, None]


def test_message_validates_body(client: TestClient) -> None:
    login_demo(client)
    discussion = new_discussion(client)
    url = f"/api/discussions/{discussion['id']}/messages"
    assert client.post(url, json={"body": ""}).status_code == 422
    assert client.post(url, json={"body": "   "}).status_code == 422
    assert client.post(url, json={"body": "x" * 4001}).status_code == 422
    # 空字符本身能完整存取（已实测），但会让 SQL 的 length()/LIKE 等函数计数错乱，
    # 接口层直接拒绝，避免下游踩坑——这是接口规范，不是“数据库会截断”。
    assert client.post(url, json={"body": "前半段\x00后半段"}).status_code == 422
    padded = client.post(url, json={"body": "  真正的内容  "})
    assert padded.status_code == 201
    assert padded.json()["message"]["body"] == "真正的内容"


def test_message_preserves_special_characters(client: TestClient) -> None:
    login_demo(client)
    discussion = new_discussion(client)
    cases = [
        "第一行\n第二行\n\t缩进行",
        "emoji 😀🎉 与中文混排",
        "引号 ' \" 和反斜杠 \\ 和百分号 %",
        "'; DROP TABLE messages; --",
        "<script>alert('xss')</script>",
        "x" * 4000,
    ]
    for body in cases:
        send(client, discussion["id"], body)

    items = client.get(f"/api/discussions/{discussion['id']}/messages").json()["items"]
    assert [item["body"] for item in items] == [case.strip() for case in cases]
    # 注入串只是普通文本，表结构和后续写入都正常。
    send(client, discussion["id"], "注入之后再写一条")
    assert len(client.get(f"/api/discussions/{discussion['id']}/messages").json()["items"]) == 7


def test_message_reply_to_validation(client: TestClient) -> None:
    login_demo(client)
    discussion = new_discussion(client)
    target = send(client, discussion["id"], "被引用的那句")["message"]["id"]

    quoted = send(client, discussion["id"], "我回应上一句", in_reply_to=target)
    assert quoted["message"]["in_reply_to"] == target

    url = f"/api/discussions/{discussion['id']}/messages"
    bad = client.post(url, json={"body": "引用不存在的消息", "in_reply_to": "missing-id"})
    assert bad.status_code == 422
    assert bad.json()["detail"]["code"] == "INVALID_REFERENCE"

    # 不能引用别的讨论里的消息
    other = new_discussion(client, topic="另一条讨论")
    other_message = send(client, other["id"], "别处的消息")["message"]["id"]
    crossed = client.post(url, json={"body": "跨讨论引用", "in_reply_to": other_message})
    assert crossed.status_code == 422


def test_message_pagination(client: TestClient) -> None:
    login_demo(client)
    discussion = new_discussion(client)
    for index in range(3):
        send(client, discussion["id"], f"第 {index + 1} 句")
    base = f"/api/discussions/{discussion['id']}/messages"

    first_page = client.get(base, params={"limit": 2}).json()
    assert [item["seq"] for item in first_page["items"]] == [1, 2]
    assert first_page["has_more"] is True

    second_page = client.get(base, params={"after_seq": 2, "limit": 2}).json()
    assert [item["seq"] for item in second_page["items"]] == [3]
    assert second_page["has_more"] is False

    beyond = client.get(base, params={"after_seq": 99}).json()
    assert beyond["items"] == []
    assert beyond["message_seq"] == 3


def test_message_newest_first_paging_walks_backwards(client: TestClient) -> None:
    """往回翻历史必须能一页页翻到底。只测第一页是不够的——上一版的 has_more 就是空承诺。"""
    login_demo(client)
    discussion = new_discussion(client)
    for index in range(5):
        send(client, discussion["id"], f"第 {index + 1} 句")
    base = f"/api/discussions/{discussion['id']}/messages"

    page1 = client.get(base, params={"newest_first": True, "limit": 2}).json()
    assert [item["seq"] for item in page1["items"]] == [4, 5], "第一页取最新两条，仍按升序返回"
    assert page1["has_more"] is True

    page2 = client.get(
        base, params={"newest_first": True, "limit": 2, "before_seq": 4}
    ).json()
    assert [item["seq"] for item in page2["items"]] == [2, 3], "第二页应能继续往前翻"
    assert page2["has_more"] is True

    page3 = client.get(
        base, params={"newest_first": True, "limit": 2, "before_seq": 2}
    ).json()
    assert [item["seq"] for item in page3["items"]] == [1]
    assert page3["has_more"] is False, "翻到底后必须明确告知没有更多"


def test_message_newest_first_ignores_after_seq(client: TestClient) -> None:
    """两种游标不混用：newest_first 只认 before_seq。"""
    login_demo(client)
    discussion = new_discussion(client)
    for index in range(4):
        send(client, discussion["id"], f"第 {index + 1} 句")
    base = f"/api/discussions/{discussion['id']}/messages"

    result = client.get(
        base, params={"newest_first": True, "limit": 2, "after_seq": 99}
    ).json()
    assert [item["seq"] for item in result["items"]] == [3, 4], "after_seq 不该影响往回翻的结果"


def test_message_quota(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(discussion_store, "MAX_MESSAGES_PER_DISCUSSION", 2)
    login_demo(client)
    discussion = new_discussion(client)
    send(client, discussion["id"], "第一条")
    send(client, discussion["id"], "第二条")
    blocked = client.post(
        f"/api/discussions/{discussion['id']}/messages", json={"body": "第三条"}
    )
    assert blocked.status_code == 429
    assert blocked.json()["detail"]["code"] == "MESSAGE_QUOTA_EXCEEDED"


# ---------------- 状态机 ----------------


def test_pause_and_resume(client: TestClient) -> None:
    login_demo(client)
    discussion = new_discussion(client)
    base = f"/api/discussions/{discussion['id']}"

    paused = client.post(f"{base}/pause")
    assert paused.status_code == 200
    assert paused.json()["status"] == "paused"
    assert paused.json()["paused_at"] is not None

    resumed = client.post(f"{base}/resume")
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "active"
    assert resumed.json()["paused_at"] is None, "恢复后不应残留暂停时间"


def test_pause_is_idempotent(client: TestClient) -> None:
    login_demo(client)
    discussion = new_discussion(client)
    base = f"/api/discussions/{discussion['id']}"
    first = client.post(f"{base}/pause").json()
    second = client.post(f"{base}/pause")
    assert second.status_code == 200
    assert second.json()["paused_at"] == first["paused_at"]


def test_message_allowed_while_paused(client: TestClient) -> None:
    login_demo(client)
    discussion = new_discussion(client)
    client.post(f"/api/discussions/{discussion['id']}/pause")
    response = client.post(
        f"/api/discussions/{discussion['id']}/messages", json={"body": "暂停期间也能补充"}
    )
    assert response.status_code == 201, "暂停只是停止推进，不禁止用户补充发言"


def test_stop_blocks_further_messages(client: TestClient) -> None:
    login_demo(client)
    discussion = new_discussion(client)
    base = f"/api/discussions/{discussion['id']}"
    stopped = client.post(f"{base}/stop")
    assert stopped.status_code == 200
    assert stopped.json()["status"] == "stopped"
    assert stopped.json()["stopped_at"] is not None

    again = client.post(f"{base}/stop")
    assert again.status_code == 200, "重复停止应幂等"
    assert again.json()["stopped_at"] == stopped.json()["stopped_at"]

    blocked = client.post(f"{base}/messages", json={"body": "停止后还想说"})
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "DISCUSSION_CLOSED"


def test_finish_blocks_further_messages(client: TestClient) -> None:
    login_demo(client)
    discussion = new_discussion(client)
    base = f"/api/discussions/{discussion['id']}"
    finished = client.post(f"{base}/finish")
    assert finished.status_code == 200
    assert finished.json()["status"] == "finished"
    assert finished.json()["finished_at"] is not None

    blocked = client.post(f"{base}/messages", json={"body": "结束后还想说"})
    assert blocked.status_code == 409


def test_invalid_transitions_after_closed(client: TestClient) -> None:
    login_demo(client)
    discussion = new_discussion(client)
    base = f"/api/discussions/{discussion['id']}"
    client.post(f"{base}/stop")

    for action in ("pause", "resume"):
        response = client.post(f"{base}/{action}")
        assert response.status_code == 409, f"{action} 不应作用在已停止的讨论上"
        assert response.json()["detail"]["code"] == "INVALID_STATE"
        assert response.json()["detail"]["current_status"] == "stopped"

    # 已结束的讨论不能再停止（终态不同）
    finished = new_discussion(client, topic="另一条")
    fbase = f"/api/discussions/{finished['id']}"
    client.post(f"{fbase}/finish")
    assert client.post(f"{fbase}/stop").status_code == 409


# ---------------- 事件 ----------------


def test_events_cover_creation_and_messages(client: TestClient) -> None:
    login_demo(client)
    discussion = new_discussion(client)
    base = f"/api/discussions/{discussion['id']}"
    send(client, discussion["id"], "第一句")

    payload = client.get(f"{base}/events").json()
    types = [event["type"] for event in payload["events"]]
    assert types == ["discussion.created", "message.created"]
    assert payload["events"][0]["message"] is None
    assert payload["events"][1]["message"]["body"] == "第一句"
    assert payload["status"] == "active"


def test_events_cover_state_changes(client: TestClient) -> None:
    login_demo(client)
    discussion = new_discussion(client)
    base = f"/api/discussions/{discussion['id']}"
    client.post(f"{base}/pause")
    client.post(f"{base}/resume")
    client.post(f"{base}/stop")

    types = [event["type"] for event in client.get(f"{base}/events").json()["events"]]
    assert types == [
        "discussion.created",
        "discussion.paused",
        "discussion.resumed",
        "discussion.stopped",
    ]


def test_event_seq_is_independent_from_message_seq(client: TestClient) -> None:
    """这是事件表存在的理由：两套序号各自计数，不能混用。"""
    login_demo(client)
    discussion = new_discussion(client)
    assert discussion["event_seq"] == 1, "创建本身就是一个事件"
    assert discussion["message_seq"] == 0

    send(client, discussion["id"], "第一句")
    detail = client.get(f"/api/discussions/{discussion['id']}").json()
    assert detail["message_seq"] == 1
    assert detail["event_seq"] == 2
    assert detail["event_seq"] != detail["message_seq"]


def test_events_incremental_and_pagination(client: TestClient) -> None:
    login_demo(client)
    discussion = new_discussion(client)
    base = f"/api/discussions/{discussion['id']}"
    for index in range(3):
        send(client, discussion["id"], f"第 {index + 1} 句")

    full = client.get(f"{base}/events").json()
    assert [event["seq"] for event in full["events"]] == [1, 2, 3, 4]

    resumed = client.get(f"{base}/events", params={"after_seq": 2}).json()
    assert [event["seq"] for event in resumed["events"]] == [3, 4]

    page = client.get(f"{base}/events", params={"limit": 2}).json()
    assert len(page["events"]) == 2
    assert page["has_more"] is True
    assert page["event_seq"] == 4


# ---------------- SSE ----------------


def _collect_stream(client: TestClient, url: str, **kwargs) -> str:
    """把 SSE 流读到关闭，返回拼接后的原文。只用于讨论已进入终态的场景。"""
    chunks: list[str] = []
    with client.stream("GET", url, **kwargs) as response:
        assert response.status_code == 200, response.read()
        assert response.headers["content-type"].startswith("text/event-stream")
        for line in response.iter_lines():
            chunks.append(line)
    return "\n".join(chunks)


def test_stream_replays_events_then_closes(client: TestClient) -> None:
    login_demo(client)
    discussion = new_discussion(client)
    base = f"/api/discussions/{discussion['id']}"
    send(client, discussion["id"], "流里应该能看到的这句")
    client.post(f"{base}/stop")

    text = _collect_stream(client, f"{base}/stream")
    assert "event: discussion.created" in text
    assert "event: message.created" in text
    assert "流里应该能看到的这句" in text
    assert "event: discussion.stopped" in text
    assert "event: stream.end" in text


def test_stream_respects_last_event_id(client: TestClient) -> None:
    login_demo(client)
    discussion = new_discussion(client)
    base = f"/api/discussions/{discussion['id']}"
    send(client, discussion["id"], "第一句")
    send(client, discussion["id"], "第二句")
    # 事件：1 创建、2 第一句、3 第二句
    client.post(f"{base}/stop")  # 4 停止

    text = _collect_stream(client, f"{base}/stream", headers={"Last-Event-ID": "2"})
    assert "\nid: 1\n" not in text and not text.startswith("id: 1\n")
    assert "id: 3" in text
    assert "第一句" not in text, "Last-Event-ID 之前的消息不应重发"
    assert "第二句" in text


def test_stream_respects_after_seq(client: TestClient) -> None:
    login_demo(client)
    discussion = new_discussion(client)
    base = f"/api/discussions/{discussion['id']}"
    send(client, discussion["id"], "只发这一句")
    client.post(f"{base}/stop")

    text = _collect_stream(client, f"{base}/stream", params={"after_seq": 2})
    assert "只发这一句" not in text, "after_seq 之前的消息不应重发"
    assert "event: discussion.stopped" in text


def test_stream_unknown_discussion_returns_404(client: TestClient) -> None:
    login_demo(client)
    assert client.get("/api/discussions/nope/stream").status_code == 404


def test_stream_sends_heartbeat_when_idle(client: TestClient, monkeypatch) -> None:
    """活跃但长时间没有新事件时，应按间隔发 keep-alive 注释，否则中间层会掐断连接。

    把心跳间隔压到 0.1 秒来验证，避免真的等 15 秒。Starlette 的 TestClient 会把
    流式响应缓冲到应用结束，所以用定时器在 0.35 秒后停止讨论，让流正常收尾。
    """
    from app import discussions

    monkeypatch.setattr(discussions, "HEARTBEAT_SECONDS", 0.1)
    monkeypatch.setattr(discussions, "POLL_INTERVAL_SECONDS", 0.02)
    login_demo(client)
    discussion = new_discussion(client)  # active 状态，流不会自己结束
    base = f"/api/discussions/{discussion['id']}"
    user_id = client.get("/api/auth/status").json()["user_id"]
    store = client.app.state.discussions

    stopper = threading.Timer(
        0.35, lambda: store.stop_discussion(user_id, discussion["id"])
    )
    stopper.start()
    try:
        text = _collect_stream(client, f"{base}/stream")
    finally:
        stopper.cancel()

    assert ": keep-alive" in text, "空闲连接应收到心跳帧"
    assert "stream.end" in text


def test_stream_times_out_and_closes(client: TestClient, monkeypatch) -> None:
    """单连接超过存活上限时，应发 stream.timeout 并主动关闭，不能无限占用线程。"""
    from app import discussions

    monkeypatch.setattr(discussions, "STREAM_MAX_SECONDS", 0.3)
    monkeypatch.setattr(discussions, "POLL_INTERVAL_SECONDS", 0.02)
    login_demo(client)
    discussion = new_discussion(client)
    base = f"/api/discussions/{discussion['id']}"

    frames = []
    with client.stream("GET", f"{base}/stream") as response:
        assert response.status_code == 200
        for line in response.iter_lines():
            if line:
                frames.append(line)
    text = "\n".join(frames)
    assert "stream.timeout" in text
    assert "retry: 60000" in text, "超时收尾也应提示客户端放慢重连"


def test_stream_releases_slot_after_client_disconnects(client: TestClient, monkeypatch) -> None:
    """客户端断开后必须归还订阅名额，否则连几次就把所有名额占死。

    Starlette 的 TestClient 会把流缓冲到应用结束，无法在测试里真正“中途断开”，
    所以直接驱动异步生成器：收到第一帧后 `aclose()`，再检查信号量是否归还。
    """
    from app import discussions

    slots = threading.BoundedSemaphore(1)
    monkeypatch.setattr(discussions, "_STREAM_SLOTS", slots)
    monkeypatch.setattr(discussions, "POLL_INTERVAL_SECONDS", 0.02)
    login_demo(client)
    discussion = new_discussion(client)
    user_id = client.get("/api/auth/status").json()["user_id"]
    store = client.app.state.discussions

    # 模拟 endpoint 已经占用了唯一的名额。
    assert slots.acquire(blocking=False)

    async def read_one_then_disconnect() -> None:
        frames = discussions._stream_frames(store, user_id, discussion["id"], 0)
        await frames.__anext__()  # 至少收到一帧
        await frames.aclose()  # 模拟客户端断开

    asyncio.run(read_one_then_disconnect())
    assert slots.acquire(blocking=False), "断开后名额没有被归还"


# ---------------- 隔离 ----------------


def test_discussions_are_isolated_between_users(client: TestClient) -> None:
    login_demo(client)
    discussion = new_discussion(client)
    base = f"/api/discussions/{discussion['id']}"
    send(client, discussion["id"], "只属于当前用户")

    other = TestClient(client.app)
    login_demo(other)

    assert other.get(base).status_code == 404
    assert other.get(f"{base}/messages").status_code == 404
    assert other.get(f"{base}/events").status_code == 404
    assert other.get(f"{base}/stream").status_code == 404
    assert other.post(f"{base}/messages", json={"body": "越权发言"}).status_code == 404
    assert other.post(f"{base}/pause").status_code == 404
    assert other.post(f"{base}/stop").status_code == 404
    assert other.get("/api/discussions").json()["items"] == []


def test_extension_token_can_use_discussions(client: TestClient) -> None:
    login_demo(client)
    discussion = new_discussion(client)
    pair = client.post("/api/extension/pair")
    token = client.post("/api/extension/exchange", json={"code": pair.json()["code"]}).json()[
        "extension_token"
    ]
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get(f"/api/discussions/{discussion['id']}", headers=headers)
    assert response.status_code == 200
    assert response.json()["id"] == discussion["id"]


# ---------------- 持久化 ----------------


def test_survives_service_restart(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)

    first = TestClient(create_app(settings))
    login_demo(first)
    discussion = new_discussion(first)
    base = f"/api/discussions/{discussion['id']}"
    send(first, discussion["id"], "重启之前说的话")
    session = first.cookies.get("thinkspace_session")
    assert session
    first.close()

    second = TestClient(create_app(settings))
    headers = {"Cookie": f"thinkspace_session={session}"}

    detail = second.get(base, headers=headers)
    assert detail.status_code == 200
    assert detail.json()["message_seq"] == 1
    assert detail.json()["event_seq"] == 2

    items = second.get(f"{base}/messages", headers=headers).json()["items"]
    assert [item["body"] for item in items] == ["重启之前说的话"]

    resumed = second.post(f"{base}/messages", headers=headers, json={"body": "重启之后接着说"})
    assert resumed.status_code == 201
    assert resumed.json()["message"]["seq"] == 2
    second.close()


# ---------------- 并发 ----------------


def _prepare_store(tmp_path: Path) -> tuple[Store, DiscussionStore, str]:
    path = str(tmp_path / "concurrency.db")
    legacy = Store(path, "test-secret")
    _, user_id = legacy.create_session(demo=True)
    store = DiscussionStore(path)
    return legacy, store, user_id


def test_concurrent_writes_keep_message_seq_unique(tmp_path: Path) -> None:
    _, store, user_id = _prepare_store(tmp_path)
    discussion = store.create_discussion(user_id, "并发写入")

    seqs: list[int] = []
    errors: list[BaseException] = []
    lock = threading.Lock()

    def worker(index: int) -> None:
        try:
            message, _ = store.append_message(user_id, discussion["id"], "user", f"并发消息 {index}")
            with lock:
                seqs.append(message["seq"])
        except BaseException as exc:  # noqa: BLE001 - 线程里的异常要带回主线程
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors, f"并发写入不应报错: {errors[:2]}"
    assert sorted(seqs) == list(range(1, 21)), "20 条消息的序号必须严格连续且不重复"


def test_concurrent_idempotent_submits_create_once(tmp_path: Path) -> None:
    _, store, user_id = _prepare_store(tmp_path)
    discussion = store.create_discussion(user_id, "幂等并发")

    flags: list[bool] = []
    errors: list[BaseException] = []
    lock = threading.Lock()

    def worker(_: int) -> None:
        try:
            _, created = store.append_message(
                user_id, discussion["id"], "user", "重复提交的一句话", client_msg_id="dup-1"
            )
            with lock:
                flags.append(created)
        except BaseException as exc:  # noqa: BLE001
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors, f"并发幂等提交不应报错: {errors[:2]}"
    assert flags.count(True) == 1, "只能有一次真正创建"
    items, _, _ = store.list_messages(user_id, discussion["id"], limit=100)
    assert len(items) == 1


# ---------------- 列表带角色、WAL、消息状态 ----------------


def test_list_discussions_includes_participants(client: TestClient) -> None:
    """列表页要显示在座角色，否则前端得为每条讨论再请求一次详情。"""
    login_demo(client)
    new_discussion(client, topic="甲")
    new_discussion(client, topic="乙")

    items = client.get("/api/discussions").json()["items"]
    assert len(items) == 2
    for item in items:
        assert {p["role_id"] for p in item["participants"]} == DEFAULT_ROLES
        seats = [p["seat"] for p in item["participants"]]
        assert seats == sorted(seats)


def test_database_uses_wal_mode(tmp_path: Path) -> None:
    """WAL 让读不阻塞写：SSE 反复读事件时，用户发言不会被卡住。"""
    _, store, _ = _prepare_store(tmp_path)
    connection = sqlite3.connect(store.database_path)
    try:
        mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
    finally:
        connection.close()
    assert mode.lower() == "wal"


def test_schema_version_is_recorded(tmp_path: Path) -> None:
    """版本记在 schema_migrations 表里，按模块分开，不再占用全库唯一的 user_version。"""
    _, store, _ = _prepare_store(tmp_path)
    connection = sqlite3.connect(store.database_path)
    try:
        row = connection.execute(
            "SELECT version FROM schema_migrations WHERE module = ?",
            (discussion_store.SCHEMA_MODULE,),
        ).fetchone()
        legacy = connection.execute("PRAGMA user_version").fetchone()[0]
    finally:
        connection.close()
    assert row is not None, "schema_migrations 里应有本模块的记录"
    assert row[0] == discussion_store.SCHEMA_VERSION
    assert legacy == 0, "不应再写全局 user_version，避免和别的模块抢"


def test_event_payload_is_a_snapshot_not_a_reference(tmp_path: Path) -> None:
    """事件里的消息内容是写入时的副本：之后无论怎么改消息，历史事件都不受影响。"""
    _, store, user_id = _prepare_store(tmp_path)
    discussion = store.create_discussion(user_id, "快照验证")
    message, _ = store.append_message(user_id, discussion["id"], "skeptic", "原始内容")

    before, _, _, _ = store.list_events(user_id, discussion["id"])
    created = next(event for event in before if event["type"] == "message.created")
    assert created["message"]["body"] == "原始内容"

    # 绕过存储层直接改消息表，模拟任何后续修改
    connection = sqlite3.connect(store.database_path)
    try:
        connection.execute("UPDATE messages SET body = '被改过了' WHERE id = ?", (message["id"],))
        connection.commit()
    finally:
        connection.close()

    after, _, _, _ = store.list_events(user_id, discussion["id"])
    same = next(event for event in after if event["seq"] == created["seq"])
    assert same["message"]["body"] == "原始内容", "历史事件应保持写入时的快照"


def test_append_message_accepts_final_status(tmp_path: Path) -> None:
    """D 只存定型消息：落库时状态就是最终态，没有 streaming 这种中间态。"""
    _, store, user_id = _prepare_store(tmp_path)
    discussion = store.create_discussion(user_id, "状态落库")

    failed, _ = store.append_message(
        user_id, discussion["id"], "skeptic", "生成失败的回复", status="failed"
    )
    assert failed["status"] == "failed"

    with pytest.raises(ValueError, match="消息状态只能是"):
        store.append_message(
            user_id, discussion["id"], "skeptic", "不该存在的中间态", status="streaming"
        )


def test_append_message_rejects_role_not_seated(tmp_path: Path) -> None:
    """只有在这条讨论里落座的角色才能发言，否则编排模块可以让不在场的人插话。"""
    _, store, user_id = _prepare_store(tmp_path)
    discussion = store.create_discussion(user_id, "落座校验", role_ids=["explorer"])

    with pytest.raises(ValueError, match="没有在这条讨论中落座"):
        store.append_message(user_id, discussion["id"], "skeptic", "我不在场")

    # 在座的角色可以正常发言
    message, _ = store.append_message(user_id, discussion["id"], "explorer", "我在场")
    assert message["role_id"] == "explorer"


def test_append_message_wakes_waiter_within_a_second(tmp_path: Path) -> None:
    """一次真实写入就应唤醒订阅者，且耗时远小于兜底超时。

    不用“重复通知 20 次、总有一次成功”的宽松判断：那种写法证明不了单次写入有效。
    """
    _, store, user_id = _prepare_store(tmp_path)
    discussion = store.create_discussion(user_id, "写入唤醒")

    ready = threading.Event()
    woke = threading.Event()

    def waiter() -> None:
        ready.set()
        store.wait_for_change(discussion["id"], timeout=5)
        woke.set()

    thread = threading.Thread(target=waiter)
    thread.start()
    assert ready.wait(2), "等待线程未启动"
    time.sleep(0.1)  # 从 set 到真正进入 wait 之间的间隙

    wrote_at = time.monotonic()
    store.append_message(user_id, discussion["id"], "user", "这一句应该触发唤醒")
    assert woke.wait(2), "写入后订阅者没有被唤醒"
    elapsed_ms = (time.monotonic() - wrote_at) * 1000
    thread.join(timeout=2)

    assert elapsed_ms < 500, f"唤醒耗时 {elapsed_ms:.0f}ms，说明在等兜底轮询而不是即时唤醒"


def test_watermark_never_lags_messages_under_concurrent_writes(tmp_path: Path) -> None:
    """水位与数据必须来自同一快照：并发写入时，返回的最大 seq 不能超过水位。"""
    _, store, user_id = _prepare_store(tmp_path)
    discussion = store.create_discussion(user_id, "并发水位")

    stop = threading.Event()
    violations: list[tuple[int, int]] = []

    def writer() -> None:
        for index in range(60):
            store.append_message(user_id, discussion["id"], "user", f"写入 {index}")

    def reader() -> None:
        while not stop.is_set():
            items, _, watermark = store.list_messages(user_id, discussion["id"], limit=200)
            if items and items[-1]["seq"] > watermark:
                violations.append((items[-1]["seq"], watermark))

    write_thread = threading.Thread(target=writer)
    read_thread = threading.Thread(target=reader)
    write_thread.start()
    read_thread.start()
    write_thread.join()
    stop.set()
    read_thread.join()

    assert not violations, f"出现水位落后于返回消息的情况：{violations[:3]}"


def test_legacy_schema_is_rebuilt_when_tables_are_empty(tmp_path: Path) -> None:
    """v2 结构（缺 message_seq 等列）且表为空时，启动应自动重建，不能直接崩。"""
    path = str(tmp_path / "legacy.db")
    legacy = Store(path, "test-secret")
    _, user_id = legacy.create_session(demo=True)

    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE discussions (id TEXT PRIMARY KEY, user_id TEXT, topic TEXT);
            CREATE TABLE discussion_events (seq INTEGER PRIMARY KEY, discussion_id TEXT, type TEXT);
            PRAGMA user_version = 2;
            """
        )
        connection.commit()
    finally:
        connection.close()

    store = DiscussionStore(path)
    discussion = store.create_discussion(user_id, "迁移之后")
    assert discussion["event_seq"] == 1
    events, _, _, _ = store.list_events(user_id, discussion["id"])
    assert [event["type"] for event in events] == ["discussion.created"]


def test_legacy_schema_with_data_refuses_to_start(tmp_path: Path) -> None:
    """旧结构里已经有数据时必须拒绝启动，不能静默 DROP 掉别人的数据。"""
    path = str(tmp_path / "legacy-data.db")
    legacy = Store(path, "test-secret")
    _, user_id = legacy.create_session(demo=True)

    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE discussions (id TEXT PRIMARY KEY, user_id TEXT, topic TEXT);
            PRAGMA user_version = 2;
            """
        )
        connection.execute(
            "INSERT INTO discussions VALUES ('old-1', ?, '旧数据')", (user_id,)
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(RuntimeError, match="旧表结构"):
        DiscussionStore(path)


def test_stream_returns_503_when_slots_exhausted(client: TestClient, monkeypatch) -> None:
    """验证端点真的返回 503，而不是只验证信号量本身。"""
    from app import discussions

    monkeypatch.setattr(discussions, "_STREAM_SLOTS", threading.BoundedSemaphore(1))
    login_demo(client)
    discussion = new_discussion(client)
    base = f"/api/discussions/{discussion['id']}"
    client.post(f"{base}/stop")

    assert discussions._STREAM_SLOTS.acquire(blocking=False) is True
    try:
        response = client.get(f"{base}/stream")
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "STREAM_BUSY"
    finally:
        discussions._STREAM_SLOTS.release()


def test_oversized_sequence_values_do_not_crash(client: TestClient) -> None:
    """SQLite 的 INTEGER 是 64 位，超出范围的序号必须被挡住，不能冒成 500。"""
    login_demo(client)
    discussion = new_discussion(client)
    base = f"/api/discussions/{discussion['id']}"
    send(client, discussion["id"], "一句话")
    client.post(f"{base}/stop")

    oversized = 2**63 + 1
    assert client.get(f"{base}/messages", params={"after_seq": oversized}).status_code == 422
    assert (
        client.get(
            f"{base}/messages", params={"newest_first": True, "before_seq": oversized}
        ).status_code
        == 422
    )
    assert client.get(f"{base}/events", params={"after_seq": oversized}).status_code == 422
    assert client.get("/api/discussions", params={"offset": oversized}).status_code == 422
    assert client.get(f"{base}/stream", params={"after_seq": oversized}).status_code == 422

    # Header 不受 Query 的 le 约束，应被收敛到 64 位范围内而不是抛 OverflowError
    with client.stream(
        "GET", f"{base}/stream", headers={"Last-Event-ID": str(oversized)}
    ) as response:
        assert response.status_code == 200
        body = "\n".join(line for line in response.iter_lines() if line)
    assert "stream.end" in body


def test_connection_context_closes_the_connection(tmp_path: Path) -> None:
    """`_connection()` 必须真正关闭连接。

    `with sqlite3.connect(...) as conn` 只提交事务、不关闭连接，依赖 GC 会拖延
    Windows 上的文件句柄释放。这里验证关闭后连接已不可用。
    """
    _, store, _ = _prepare_store(tmp_path)
    with store._connection() as connection:
        assert connection.execute("SELECT 1").fetchone()[0] == 1
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")


def test_create_discussion_translates_database_busy(client: TestClient, monkeypatch) -> None:
    """创建也是写库，同样要翻译成 503，不能只有其他写接口有这个保护。"""
    login_demo(client)

    def busy(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(DiscussionStore, "create_discussion", busy)
    response = client.post("/api/discussions", json={"topic": "锁冲突"})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "DATABASE_BUSY"


def test_no_read_path_uses_the_unclosed_pattern() -> None:
    """用 AST 检查而不是字符串匹配：换个变量名、换个换行写法也照样能抓住。"""
    source = (
        Path(__file__).resolve().parents[1] / "app" / "discussion_store.py"
    ).read_text(encoding="utf-8")
    offenders = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.With):
            continue
        for item in node.items:
            call = item.context_expr
            if (
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute)
                and call.func.attr == "_connect"
            ):
                offenders.append(node.lineno)
    assert not offenders, (
        "sqlite3 连接的上下文管理器只提交事务、不关闭连接；"
        f"这些行应改用 _connection() 或 _write()：{offenders}"
    )
