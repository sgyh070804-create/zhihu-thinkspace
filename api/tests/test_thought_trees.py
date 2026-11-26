from __future__ import annotations

import json
import threading
import time
from dataclasses import replace
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.deps import SESSION_COOKIE
from app.main import create_app
from app.providers.zhihu import ZhihuClient
from conftest import make_settings


CANDIDATE = {
    "title": "做一次小规模试验",
    "content": "先用一个可逆的小实验验证最不确定的假设。",
    "relation": "把原先的判断转成可观察的检验。",
    "type": "projection",
}


def new_tree(client: TestClient, **data) -> dict:
    response = client.post("/api/thought-trees", json={"request_id": str(uuid4()), **data})
    assert response.status_code == 201, response.text
    return response.json()


def child(parent_id: str, title: str, content: str) -> dict:
    return {"id": uuid4().hex, "parent_id": parent_id, "title": title, "content": content}


def update(client: TestClient, tree: dict, nodes: list[dict]):
    return client.post(f"/api/thought-trees/{tree['id']}", json={"version": tree["version"], "nodes": nodes})


def request_candidates(client: TestClient, tree: dict, node_id: str, references: str = ""):
    return client.post(
        f"/api/thought-trees/{tree['id']}/nodes/{node_id}/candidates",
        json={"version": tree["version"], "references": references},
    )


def fixture_app(tmp_path, upstream, **config):
    settings = replace(
        make_settings(tmp_path),
        access_secret="mock-platform-credential",
        branch_ai_allow_demo=True,
        branch_ai_min_interval=0,
        **config,
    )
    app = create_app(settings)
    app.state.zhihu = ZhihuClient(settings, transport=httpx.MockTransport(upstream))
    return app


def quota(remaining: int = 50):
    return httpx.Response(200, json={
        "Code": 0, "Data": [{"APIID": "zhida_openai", "RemainingQuota": remaining}],
    })


def completion(text: str):
    return httpx.Response(200, json={"choices": [{
        "message": {"content": text, "reasoning_content": "禁止把这段思考作为正式分支"},
        "finish_reason": "stop",
    }]})


def test_tree_from_bubble_versions_identity_undo_and_export(tmp_path):
    settings = make_settings(tmp_path)
    app = create_app(settings)

    def login_zhihu(client: TestClient):
        session, _ = client.app.state.store.create_zhihu_session(
            {"uid": "fixture-identity"}, "fixture-oauth", int(time.time()) + 3600,
        )
        client.cookies.set(SESSION_COOKIE, session)

    with TestClient(app) as client:
        assert client.get("/api/thought-trees").status_code == 401
        login_zhihu(client)
        origin = client.post("/api/bubbles", json={
            "source_url": "https://zhuanlan.zhihu.com/p/12345",
            "title": "阅读资料",
            "body": "原始阅读思绪",
            "quote": "手动选中的原文",
        }).json()
        tree = new_tree(client, source_id=origin["id"])
        assert tree["source_id"] == origin["id"]
        assert tree == new_tree(client, source_id=origin["id"])
        root = tree["nodes"][0]
        assert root["content"] == origin["body"]
        left = child(root["id"], "第一条", "一个独立方向")
        right = child(root["id"], "第二条", "另一个独立方向")
        first_snapshot = [root, left, right]
        first = update(client, tree, first_snapshot).json()
        assert first["version"] == 2
        assert update(client, tree, first_snapshot).status_code == 409
        assert update(client, first, [{**root, "content": "伪造原始思绪"}]).status_code == 422
        assert update(client, first, [root, {**left, "parent_id": left["id"]}]).status_code == 422
        leaf = {**child(left["id"], "继续探索", "历史节点继续生长"), "annotation": "我的补充"}
        current = update(client, first, [*first_snapshot, leaf]).json()
        assert current["nodes"][-1]["parent_id"] == left["id"]
        assert current["nodes"][2]["id"] == right["id"]
        save_path = f"/api/thought-trees/{tree['id']}/nodes/{leaf['id']}/thought"
        save_payload = {"version": current["version"]}
        saved = client.post(save_path, json=save_payload).json()
        assert saved["parent_ids"] == [origin["id"]]
        assert saved["source_url"] == origin["source_url"]
        assert saved["body"].endswith("我的补充")
        assert client.post(save_path, json=save_payload).json()["id"] == saved["id"]
        removed = update(client, current, [root, right]).json()
        assert client.get(f"/api/thoughts/{saved['id']}").status_code == 200
        restored = update(client, removed, [*first_snapshot, leaf]).json()
        assert restored["links"][leaf["id"]] == saved["id"]
        assert client.post("/api/auth/logout").status_code == 200

    with TestClient(create_app(settings)) as client:
        login_zhihu(client)
        reopened = client.get(f"/api/thought-trees/{tree['id']}").json()
        assert reopened == restored

    with TestClient(create_app(settings)) as other:
        other.post("/api/auth/demo")
        assert other.get("/api/thought-trees").json() == {"items": []}
        assert other.get(f"/api/thought-trees/{tree['id']}").status_code == 404
        assert other.post("/api/thought-trees", json={"source_id": origin["id"], "request_id": str(uuid4())}).status_code == 404
        assert other.post(save_path, json=save_payload).status_code == 404


def test_model_context_is_local_to_node_and_cache_survives_restarts(tmp_path):
    calls = []
    duplicate = {**CANDIDATE, "title": "已有：方向"}
    def upstream(request: httpx.Request):
        assert request.headers["Authorization"] == "Bearer mock-platform-credential"
        assert abs(int(request.headers["X-Request-Timestamp"]) - int(time.time())) < 10
        assert "x-oauth-token" not in request.headers
        assert request.headers["Content-Type"] == "application/json"
        calls.append(request)
        if request.url.path == "/api/v1/quota":
            assert request.method == "GET" and request.url.params["APIIDs"] == "zhida_openai"
            return quota()
        assert request.method == "POST" and request.url.path == "/v1/chat/completions"
        payload = json.loads(request.content)
        assert set(payload) == {"model", "messages", "stream"}
        assert payload["model"] == "zhida-thinking-1p5" and payload["stream"] is False
        context = json.loads(payload["messages"][1]["content"])
        assert context["root"]["content"] == "根思绪"
        assert context["current"]["content"] == "当前节点全文"
        assert [node["content"] for node in context["ancestors"]] == ["上一层的想法"]
        assert context["existing_children"][0]["title"] == "已有方向"
        assert context["user_references"] == "用户授权的参考材料"
        assert "兄弟节点私有想法" not in request.content.decode()
        return completion("结果如下\n" + json.dumps({"branches": [duplicate, CANDIDATE]}, ensure_ascii=False) + "\n")

    app = fixture_app(tmp_path, upstream, zhida_model="zhida-thinking-1p5")
    with TestClient(app) as client:
        client.post("/api/auth/demo")
        tree = new_tree(client, content="根思绪")
        root = tree["nodes"][0]
        previous = child(root["id"], "上一层", "上一层的想法")
        sibling = child(root["id"], "另一树枝", "兄弟节点私有想法")
        current = child(previous["id"], "本层", "当前节点全文")
        existing = child(current["id"], "已有方向", "此前已探索")
        tree = update(client, tree, [root, previous, sibling, current, existing]).json()
        ready = request_candidates(client, tree, current["id"], "用户授权的参考材料")
        assert ready.status_code == 200, ready.text
        assert ready.json() == {"branches": [CANDIDATE], "cached": False}
        assert len(calls) == 2
        assert client.get(f"/api/thought-trees/{tree['id']}").json()["nodes"] == tree["nodes"]
        cookies = dict(client.cookies)
        tree = update(client, tree, [root, previous, {**sibling, "annotation": "旁支修改"}, current, existing]).json()

    with TestClient(fixture_app(tmp_path, upstream, zhida_model="zhida-thinking-1p5"), cookies=cookies) as client:
        cached = request_candidates(client, tree, current["id"], "用户授权的参考材料")
        assert cached.json() == {"branches": [CANDIDATE], "cached": True}
        assert len(calls) == 2
        adopted = {**child(current["id"], CANDIDATE["title"], "用户编辑后的候选内容"),
                   "relation": CANDIDATE["relation"], "type": CANDIDATE["type"]}
        adopted_tree = update(client, tree, [*tree["nodes"], adopted]).json()
        assert adopted_tree["nodes"][-1]["content"] == "用户编辑后的候选内容"
        refreshed = request_candidates(client, adopted_tree, current["id"], "用户授权的参考材料")
        assert refreshed.json() == {"branches": [], "cached": False}
        assert request_candidates(client, adopted_tree, current["id"], "用户授权的参考材料").json() == {"branches": [], "cached": True}
        assert len(calls) == 4


@pytest.mark.parametrize(("failure", "error_code", "posts"), [
    ("unauthorized", "ZHIDA_AUTH", 1),
    ("rate", "ZHIDA_RATE_LIMIT", 1),
    ("timeout", "ZHIDA_TIMEOUT", 1),
    ("quota", "ZHIDA_QUOTA_EXHAUSTED", 0),
    ("quota_unknown", "ZHIDA_QUOTA_UNKNOWN", 0),
    ("format", "ZHIDA_INVALID_BRANCHES", 1),
    ("too_many", "ZHIDA_INVALID_BRANCHES", 1),
    ("length", "ZHIDA_INVALID_BRANCHES", 1),
    ("type", "ZHIDA_INVALID_BRANCHES", 1),
])
def test_failures_keep_manual_path_and_charge_a_bounded_attempt(tmp_path, failure, error_code, posts):
    methods = []
    def upstream(request: httpx.Request):
        methods.append(request.method)
        if request.method == "GET":
            if failure == "quota":
                return quota(1)
            if failure == "quota_unknown":
                return httpx.Response(200, json={"Code": 0, "Data": []})
            return quota()
        if failure == "unauthorized":
            return httpx.Response(403, text="mock-platform-credential")
        if failure == "rate":
            return httpx.Response(429)
        if failure == "timeout":
            raise httpx.ReadTimeout("test only")
        if failure == "format":
            return completion("不是 JSON 的回复")
        if failure == "too_many":
            return completion(json.dumps({"branches": [CANDIDATE] * 4}))
        candidate = {**CANDIDATE, **({"title": "一" * 65} if failure == "length" else {"type": "unknown"})}
        return completion(json.dumps({"branches": [candidate]}))

    with TestClient(fixture_app(tmp_path, upstream, branch_ai_daily_budget=1)) as client:
        client.post("/api/auth/demo")
        tree = new_tree(client, content="我的问题")
        root = tree["nodes"][0]
        response = request_candidates(client, tree, root["id"])
        assert response.json()["detail"]["code"] == error_code
        assert "mock-platform-credential" not in response.text
        second = request_candidates(client, tree, root["id"])
        assert second.json()["detail"]["code"] == "BRANCH_AI_BUDGET"
        assert methods.count("POST") == posts and methods.count("GET") == 1
        assert update(client, tree, [root, child(root["id"], "手动分支", "继续探索")]).status_code == 200


def test_overlapping_generation_uses_only_one_upstream_request(tmp_path):
    entered, release = threading.Event(), threading.Event()
    methods = []
    def upstream(request: httpx.Request):
        methods.append(request.method)
        if request.method == "GET":
            return quota()
        entered.set()
        assert release.wait(timeout=4)
        return completion(json.dumps({"branches": [CANDIDATE]}))

    with TestClient(fixture_app(tmp_path, upstream)) as first:
        first.post("/api/auth/demo")
        tree = new_tree(first, content="任意问题")
        responses = []
        worker = threading.Thread(target=lambda: responses.append(request_candidates(first, tree, tree["id"])))
        worker.start()
        try:
            assert entered.wait(timeout=4)
            with TestClient(first.app, cookies=dict(first.cookies)) as second:
                assert request_candidates(second, tree, tree["id"]).json()["detail"]["code"] == "BRANCH_AI_BUSY"
        finally:
            release.set()
            worker.join(timeout=5)
        assert responses[0].status_code == 200
        assert methods == ["GET", "POST"]
