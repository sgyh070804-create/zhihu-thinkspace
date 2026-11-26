from __future__ import annotations

import asyncio
import hashlib
import json
import unicodedata
from typing import Annotated, Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError, model_validator
from starlette.concurrency import run_in_threadpool

from .branch_prompt import branch_messages
from .deps import current_identity, settings_of, store_of
from .providers.zhihu import ZhihuError
from .thoughts import ThoughtID, missing_thought

router = APIRouter(prefix="/api/thought-trees", tags=["thought-trees"])
BranchType = Literal["analysis", "association", "hypothesis", "counterexample", "projection"]
NodeBody = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class Node(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: ThoughtID
    parent_id: ThoughtID | None
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=180)]
    content: NodeBody
    annotation: str = Field(default="", max_length=2000)
    relation: str = Field(default="", max_length=240)
    type: BranchType | None = None


class TreeCreate(BaseModel):
    request_id: UUID
    source_id: ThoughtID | None = None
    content: NodeBody | None = None

    @model_validator(mode="after")
    def exactly_one_source(self):
        if bool(self.source_id) == bool(self.content):
            raise ValueError("请选择一条已有思绪，或填写新的根节点。")
        return self


class TreeUpdate(BaseModel):
    version: int = Field(ge=1)
    nodes: list[Node] = Field(min_length=1, max_length=96)

    @model_validator(mode="after")
    def valid_tree(self):
        seen = set()
        for index, node in enumerate(self.nodes):
            if node.id in seen or (index == 0 and node.parent_id is not None) or (
                index > 0 and node.parent_id not in seen
            ):
                raise ValueError("节点需要唯一标识，且子节点必须连接到现有父节点。")
            seen.add(node.id)
        return self


class VersionedInput(BaseModel):
    version: int = Field(ge=1)


class GenerateInput(VersionedInput):
    references: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)] = ""


class Candidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
    content: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=600)]
    relation: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=240)]
    type: BranchType


class CandidateList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    branches: list[Candidate] = Field(max_length=3)


def read_tree(request: Request, user_id: str, tree_id: str, version: int | None = None) -> dict:
    tree = store_of(request).get_tree(user_id, tree_id)
    if tree is None:
        raise HTTPException(404, detail="思想树不存在或不属于当前账号。")
    if version is not None and tree["version"] != version:
        raise HTTPException(409, detail="思想树已在别处更新，请重新载入后继续。")
    return tree


def read_node(tree: dict, node_id: str) -> dict:
    for node in tree["nodes"]:
        if node["id"] == node_id:
            return node
    raise HTTPException(404, detail="该节点已不存在。")


@router.get("")
def list_trees(request: Request) -> dict:
    identity = current_identity(request)
    return {"items": store_of(request).list_trees(identity.user_id)}


@router.post("", status_code=201)
def create_tree(payload: TreeCreate, request: Request) -> dict:
    identity = current_identity(request)
    store = store_of(request)
    if payload.source_id:
        source = store.get_thought(identity.user_id, payload.source_id)
        if source is None:
            raise missing_thought()
        content, title = source["body"], source["title"]
        key = f"source:{payload.source_id}"
    else:
        content = payload.content or ""
        title = content.splitlines()[0][:64]
        key = f"draft:{payload.request_id}"
    tree_id = uuid5(NAMESPACE_URL, f"thinkspace:tree:{identity.user_id}:{key}").hex
    try:
        node = Node(id=tree_id, parent_id=None, title=title.strip() or "未命名思绪", content=content)
    except ValidationError:
        raise HTTPException(422, detail="请先补全原思绪，再创建思想树。") from None
    return store.create_tree(identity.user_id, tree_id, payload.source_id, node.model_dump())


@router.get("/{tree_id}")
def get_tree(tree_id: ThoughtID, request: Request) -> dict:
    return read_tree(request, current_identity(request).user_id, tree_id)


@router.post("/{tree_id}")
def update_tree(tree_id: ThoughtID, payload: TreeUpdate, request: Request) -> dict:
    identity = current_identity(request)
    tree = read_tree(request, identity.user_id, tree_id, payload.version)
    root = tree["nodes"][0]
    incoming = payload.nodes[0]
    if (incoming.id, incoming.title, incoming.content) != (root["id"], root["title"], root["content"]):
        raise HTTPException(422, detail="原始思绪保留在根节点，可以补充想法。")
    updated = store_of(request).update_tree(identity.user_id, tree_id, payload.version, [
        node.model_dump() for node in payload.nodes
    ])
    if updated is None:
        raise HTTPException(409, detail="思想树已在别处更新，请重新载入后继续。")
    return updated


@router.post("/{tree_id}/nodes/{node_id}/thought")
def save_node(tree_id: ThoughtID, node_id: ThoughtID, payload: VersionedInput, request: Request) -> dict:
    identity = current_identity(request)
    tree = read_tree(request, identity.user_id, tree_id, payload.version)
    node = read_node(tree, node_id)
    store = store_of(request)
    lookup = {item["id"]: item for item in tree["nodes"]}
    parent_id = node["parent_id"]
    origin = None
    while parent_id:
        linked = tree["links"].get(parent_id)
        if linked:
            origin = linked
            break
        parent_id = lookup[parent_id]["parent_id"]
    if origin is None and tree["source_id"] and store.get_thought(identity.user_id, tree["source_id"]):
        origin = tree["source_id"]
    body = node["content"]
    if node["annotation"].strip():
        body = body + "\n\n补充想法\n" + node["annotation"].strip()
    if len(body) > 4000:
        raise HTTPException(422, detail="正文和补充想法合计超过资料库的 4000 字上限。")
    kind = "branch" if origin else "library"
    digest = hashlib.sha256(f'{node["title"]}\n{body}'.encode()).hexdigest()
    request_id = str(uuid5(NAMESPACE_URL, f"thinkspace:tree-node:{tree_id}:{node_id}:{digest}:{origin}"))
    current, thought = store.save_tree_export(
        identity.user_id, tree_id, payload.version, node_id, request_id, node["title"], body,
        kind, [origin] if origin else [],
    )
    if not current:
        raise HTTPException(409, detail="思想树已在别处更新，请重新载入后继续。")
    if thought is None:
        raise missing_thought()
    return thought


def comparable(value: str) -> str:
    return "".join(char for char in unicodedata.normalize("NFKC", value).casefold() if char.isalnum())


def parse_candidates(text: str, existing: list[dict]) -> list[dict]:
    if len(text) > 24000:
        raise ZhihuError("知乎直答的回复超过长度限制。", 502, "ZHIDA_INVALID_BRANCHES")
    decoder = json.JSONDecoder()
    # Some replies wrap the JSON in Markdown fences or prepend a short sentence.
    start = text.find("{")
    attempts = 0
    while start >= 0 and attempts < 32:
        try:
            value, end = decoder.raw_decode(text, start)
        except (ValueError, RecursionError):
            start = text.find("{", start + 1)
        else:
            if isinstance(value, dict) and "branches" in value:
                try:
                    validated = CandidateList.model_validate(value)
                except ValidationError:
                    break
                titles = {comparable(child["title"]) for child in existing}
                contents = {comparable(child["content"]) for child in existing}
                result = []
                for branch in validated.branches:
                    title, content = comparable(branch.title), comparable(branch.content)
                    if not title or not content or title in titles or content in contents:
                        continue
                    titles.add(title)
                    contents.add(content)
                    result.append(branch.model_dump())
                return result
            start = text.find("{", end)
        attempts += 1
    raise ZhihuError("知乎直答未返回符合格式的候选分支，可重试或手动继续。", 502, "ZHIDA_INVALID_BRANCHES")


@router.post("/{tree_id}/nodes/{node_id}/candidates")
async def generate(tree_id: ThoughtID, node_id: ThoughtID, payload: GenerateInput, request: Request) -> dict:
    identity = await run_in_threadpool(current_identity, request)
    settings = settings_of(request)
    if identity.via_extension:
        raise HTTPException(403, detail="请在网页端生成思想分支。")
    if not settings.access_secret:
        raise ZhihuError("尚未配置知乎开放平台凭证，仍可手动添加分支。", 503, "ZHIHU_NOT_CONFIGURED")
    if identity.mode == "demo" and not settings.branch_ai_allow_demo:
        raise HTTPException(403, detail="演示账号可以手动探索，AI 生成需使用正式账号。")

    tree = await run_in_threadpool(read_tree, request, identity.user_id, tree_id, payload.version)
    read_node(tree, node_id)
    messages = branch_messages(tree["nodes"], node_id, payload.references)
    context_key = json.dumps([tree_id, node_id, settings.zhida_model, messages], ensure_ascii=False)
    key = hashlib.sha256(context_key.encode()).hexdigest()
    store = store_of(request)
    status, value = await run_in_threadpool(
        store.reserve_branch_request, identity.user_id, key,
        total=settings.branch_ai_daily_budget, per_user=settings.branch_ai_user_budget,
        interval=settings.branch_ai_min_interval, concurrency=settings.branch_ai_concurrency,
    )
    if status == "cached":
        return {"branches": value, "cached": True}
    if status == "busy":
        raise ZhihuError("有分支正在生成，请稍后再请求。", 429, "BRANCH_AI_BUSY")
    if status == "frequency":
        raise ZhihuError("请求太频繁，请稍等几秒。", 429, "BRANCH_AI_FREQUENCY")
    if status == "budget":
        raise ZhihuError("今日思想分支生成预算已用完。", 429, "BRANCH_AI_BUDGET")

    provider = request.app.state.zhihu

    async def complete() -> str:
        remaining = await provider.zhida_remaining()
        threshold = settings.branch_ai_quota_reserve + settings.branch_ai_concurrency - 1
        if remaining <= threshold:
            raise ZhihuError("知乎直答剩余额度已达到保护线，仍可手动继续。", 429, "ZHIDA_QUOTA_EXHAUSTED")
        return await provider.zhida_complete(messages)

    branches = None
    try:
        try:
            text = await asyncio.wait_for(complete(), timeout=45)
        except asyncio.TimeoutError:
            raise ZhihuError("知乎直答请求超时，可稍后重试。", 504, "ZHIDA_TIMEOUT") from None
        children = [node for node in tree["nodes"] if node["parent_id"] == node_id]
        branches = parse_candidates(text, children)
    finally:
        await run_in_threadpool(store.finish_branch_request, value, branches)
    return {"branches": branches, "cached": False}
