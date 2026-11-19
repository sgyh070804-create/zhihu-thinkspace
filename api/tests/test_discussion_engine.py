from __future__ import annotations

import threading

from fastapi.testclient import TestClient

from app.discussion_engine import build_context, select_role
from app.providers.model import ModelError
from app.main import create_app
from conftest import make_settings

AI_ROLES = {"explorer", "skeptic", "weaver"}


# ---------------- 辅助 ----------------


def login_demo(client: TestClient) -> None:
    response = client.post("/api/auth/demo")
    assert response.status_code == 200, response.text


def new_discussion(client: TestClient, **payload) -> dict:
    body = {"topic": "AI 应该替我们做决定吗？", **payload}
    response = client.post("/api/discussions", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def send(client: TestClient, discussion_id: str, body: str, **extra) -> dict:
    response = client.post(
        f"/api/discussions/{discussion_id}/messages", json={"body": body, **extra}
    )
    assert response.status_code in (200, 201), response.text
    return response.json()


def advance(client: TestClient, discussion_id: str):
    return client.post(f"/api/discussions/{discussion_id}/advance")


def messages(client: TestClient, discussion_id: str) -> list[dict]:
    response = client.get(f"/api/discussions/{discussion_id}/messages")
    assert response.status_code == 200, response.text
    return response.json()["items"]


def user_id_of(client: TestClient) -> str:
    response = client.get("/api/auth/status")
    assert response.status_code == 200
    return response.json()["user_id"]


class BlockingModel:
    """在 complete 里停住，用来验证并发锁和生成期间的停止。"""

    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()

    def complete(self, **_: object) -> str:
        self.started.set()
        if not self.release.wait(5):
            raise ModelError("测试等待超时")
        return "这是一条生成中的测试发言。"


class FailingModel:
    def complete(self, **_: object) -> str:
        raise ModelError("模拟模型失败")


class OneShotBlockingModel:
    """第一次调用停住，之后立即返回；用于验证自动推进的排队行为。"""

    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()
        self.calls = 0

    def complete(self, **_: object) -> str:
        self.calls += 1
        if self.calls == 1:
            self.started.set()
            if not self.release.wait(5):
                raise ModelError("测试等待超时")
        return f"第 {self.calls} 条自动发言。"


# ---------------- 推进与轮次 ----------------


def test_advance_appends_one_ai_message_and_turn(client: TestClient) -> None:
    login_demo(client)
    discussion = new_discussion(client)

    response = advance(client, discussion["id"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["advanced"] is True
    assert body["role_id"] in AI_ROLES
    assert body["message"]["role_id"] == body["role_id"]
    assert body["message"]["body"]
    assert body["discussion"]["turn_index"] == 1

    items = messages(client, discussion["id"])
    assert len(items) == 1
    assert items[0]["role_id"] in AI_ROLES


def test_auto_advance_after_user_message(client: TestClient) -> None:
    login_demo(client)
    discussion = new_discussion(client)

    send(client, discussion["id"], "我想先区分：替我们分析，和替我们决定。", advance=True)

    items = messages(client, discussion["id"])
    assert [item["role_id"] for item in items][0] == "user"
    assert len(items) == 2
    assert items[1]["role_id"] in AI_ROLES


def test_idempotent_retry_does_not_generate_twice(client: TestClient) -> None:
    login_demo(client)
    discussion = new_discussion(client)

    first = send(
        client,
        discussion["id"],
        "同一个请求重试两次。",
        advance=True,
        client_msg_id="retry-1",
    )
    second = send(
        client,
        discussion["id"],
        "同一个请求重试两次。",
        advance=True,
        client_msg_id="retry-1",
    )
    assert first["created"] is True
    assert second["created"] is False

    items = messages(client, discussion["id"])
    assert len(items) == 2, "幂等重试不能多生成一条 AI 发言"
    assert items[0]["role_id"] == "user"


def test_max_turns_finishes_discussion(client: TestClient) -> None:
    login_demo(client)
    discussion = new_discussion(client, max_turns=1)

    first = advance(client, discussion["id"])
    assert first.status_code == 200
    assert first.json()["discussion"]["turn_index"] == 1

    second = advance(client, discussion["id"])
    assert second.status_code == 200
    body = second.json()
    assert body["advanced"] is False
    assert body["reason"] == "max_turns"
    assert body["discussion"]["status"] == "finished"
    assert len(messages(client, discussion["id"])) == 1


def test_no_ai_roles_skips_without_error(client: TestClient) -> None:
    login_demo(client)
    discussion = new_discussion(client, role_ids=["user"])

    response = advance(client, discussion["id"])
    assert response.status_code == 200
    body = response.json()
    assert body["advanced"] is False
    assert body["reason"] == "no_ai_roles"
    assert body["discussion"]["turn_index"] == 0
    assert messages(client, discussion["id"]) == []


def test_paused_discussion_does_not_advance(client: TestClient) -> None:
    login_demo(client)
    discussion = new_discussion(client)
    client.post(f"/api/discussions/{discussion['id']}/pause")

    response = advance(client, discussion["id"])
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "DISCUSSION_PAUSED"
    assert messages(client, discussion["id"]) == []

    # 暂停期间用户仍然可以补充，但自动推进不应写入 AI 发言。
    send(client, discussion["id"], "暂停时补充一句。", advance=True)
    items = messages(client, discussion["id"])
    assert [item["role_id"] for item in items] == ["user"]


# ---------------- 角色选择 ----------------


def test_role_mention_wins(client: TestClient) -> None:
    login_demo(client)
    discussion = new_discussion(client)

    send(client, discussion["id"], "质疑者，你怎么看这个前提？", advance=True)
    items = messages(client, discussion["id"])
    assert items[-1]["role_id"] == "skeptic"


def test_select_role_uses_keywords_and_avoids_repeating() -> None:
    discussion = {
        "topic": "测试",
        "participants": [
            {"role_id": "explorer", "display_name": "探索者", "seat": 0},
            {"role_id": "skeptic", "display_name": "质疑者", "seat": 1},
            {"role_id": "weaver", "display_name": "归纳者", "seat": 2},
            {"role_id": "user", "display_name": "你", "seat": 3},
        ],
    }
    assert select_role(discussion, [{"role_id": "user", "body": "这个结论的证据是什么？"}]) == "skeptic"
    assert select_role(discussion, [{"role_id": "user", "body": "先总结一下刚才的线索"}]) == "weaver"
    assert select_role(discussion, [{"role_id": "user", "body": "如果换一种假设呢？"}]) == "explorer"

    # 没有关键词时选最久没说话的角色：归纳者上一轮刚说过，应轮到探索者。
    history = [
        {"role_id": "weaver", "body": "上一条"},
        {"role_id": "user", "body": "随便说点"},
    ]
    assert select_role(discussion, history) == "explorer"


def test_build_context_keeps_topic_and_recent_messages() -> None:
    discussion = {
        "topic": "阅读与判断",
        "participants": [
            {"role_id": "explorer", "display_name": "探索者", "seat": 0},
            {"role_id": "user", "display_name": "你", "seat": 3},
        ],
    }
    history = [
        {"role_id": "user", "body": f"第 {index} 条" + "很长的内容" * 20}
        for index in range(10)
    ]
    system, conversation = build_context(
        discussion, history, "explorer", max_messages=4, max_chars=200
    )
    assert "阅读与判断" in system
    assert "探索者" in system
    assert len(conversation) <= 4
    assert conversation[-1]["role_id"] == "user"


# ---------------- 并发、停止、失败 ----------------


def test_concurrent_advance_is_rejected(client: TestClient) -> None:
    login_demo(client)
    discussion = new_discussion(client)
    engine = client.app.state.engine
    blocker = BlockingModel()
    engine.model = blocker

    results: dict[str, dict] = {}
    uid = user_id_of(client)
    thread = threading.Thread(
        target=lambda: results.update(result=engine.advance(uid, discussion["id"]))
    )
    thread.start()
    assert blocker.started.wait(5), "生成没有开始"

    response = advance(client, discussion["id"])
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ENGINE_BUSY"

    blocker.release.set()
    thread.join(5)
    assert results["result"]["advanced"] is True
    assert len(messages(client, discussion["id"])) == 1


def test_stop_during_generation_discards_result(client: TestClient) -> None:
    login_demo(client)
    discussion = new_discussion(client)
    engine = client.app.state.engine
    blocker = BlockingModel()
    engine.model = blocker

    results: dict[str, dict] = {}
    uid = user_id_of(client)
    thread = threading.Thread(
        target=lambda: results.update(result=engine.advance(uid, discussion["id"]))
    )
    thread.start()
    assert blocker.started.wait(5), "生成没有开始"

    stopped = client.post(f"/api/discussions/{discussion['id']}/stop")
    assert stopped.status_code == 200

    blocker.release.set()
    thread.join(5)
    assert results["result"]["advanced"] is False
    assert results["result"]["reason"] == "stopped"
    assert messages(client, discussion["id"]) == []


def test_auto_advance_waits_for_previous_generation(client: TestClient) -> None:
    """前一轮还在生成时，自动推进应排队而不是直接丢弃。"""
    login_demo(client)
    discussion = new_discussion(client)
    engine = client.app.state.engine
    model = OneShotBlockingModel()
    engine.model = model
    uid = user_id_of(client)

    first: dict = {}
    worker = threading.Thread(
        target=lambda: first.update(result=engine.advance(uid, discussion["id"]))
    )
    worker.start()
    assert model.started.wait(5), "第一轮生成没有开始"

    queued = threading.Thread(
        target=lambda: engine.advance_safely(uid, discussion["id"])
    )
    queued.start()

    model.release.set()
    worker.join(5)
    queued.join(5)

    items = messages(client, discussion["id"])
    assert len(items) == 2, "排队后的自动推进应生成第二条 AI 发言"
    assert {item["role_id"] for item in items} <= AI_ROLES
    assert client.get(f"/api/discussions/{discussion['id']}").json()["turn_index"] == 2


def test_model_error_returns_502_and_writes_nothing(client: TestClient) -> None:
    login_demo(client)
    discussion = new_discussion(client)
    client.app.state.engine.model = FailingModel()

    response = advance(client, discussion["id"])
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "MODEL_ERROR"
    assert messages(client, discussion["id"]) == []
    assert client.get(f"/api/discussions/{discussion['id']}").json()["turn_index"] == 0


def test_unknown_discussion_and_auth(client: TestClient) -> None:
    response = client.post("/api/discussions/not-a-real-id/advance")
    assert response.status_code == 401

    login_demo(client)
    response = advance(client, "not-a-real-id")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "DISCUSSION_NOT_FOUND"


def test_engine_is_per_app_not_global(tmp_path) -> None:
    """两个 app 实例各自持有引擎，不能共享锁或模型状态。"""
    first = TestClient(create_app(make_settings(tmp_path)))
    second = TestClient(create_app(make_settings(tmp_path)))
    assert first.app.state.engine is not second.app.state.engine
