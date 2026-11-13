#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""知乎官方知识库 RAG 验证工具（命令行）。

依据 2026-11-13 实测核对的知乎开放平台接口实现：

  POST /api/v1/knowledge/files    multipart/form-data: KnowledgeBaseID + File
  POST /api/v1/knowledge/search   JSON: Query / KnowledgeBaseIDs / Limit
  GET  /api/v1/knowledge/bases    Query: Scope
  POST /v1/chat/completions       JSON: model / messages / stream

鉴权统一使用 Header:
  Authorization: Bearer <ZHIHU_ACCESS_SECRET>
  X-Request-Timestamp: <秒级 Unix 时间戳>

设计约束（刻意不做的事）：
  * 凭证只从环境变量 ZHIHU_ACCESS_SECRET 读取，不写入代码、manifest、报告或日志；
    所有输出都经过脱敏，凭证字面量一旦出现会被替换为 ***REDACTED***。
  * ask 子命令只传 KnowledgeBaseIDs，绝不传 RecallScopes，避免把召回范围
    扩大到 personal / subscription / public。
  * 检索无命中时直接返回「资料不足」，不调用生成模型。
  * 不做网页抓取、OAuth 授权、收藏同步，也不引入任何向量数据库；
    检索与召回全部由知乎服务端完成。
  * upload 默认按内容哈希去重，不自动重复上传。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime

API_BASE = os.environ.get("ZHIHU_OPENAPI_BASE_URL", "https://developer.zhihu.com").rstrip("/")
SECRET_ENV = "ZHIHU_ACCESS_SECRET"

UPLOAD_PATH = "/api/v1/knowledge/files"
SEARCH_PATH = "/api/v1/knowledge/search"
BASES_PATH = "/api/v1/knowledge/bases"
CHAT_PATH = "/v1/chat/completions"

DEFAULT_MODEL = "zhida-fast-1p5"
ALLOWED_MODELS = ("zhida-fast-1p5", "zhida-thinking-1p5", "zhida-agent")
INSUFFICIENT = "资料不足"
MAX_SEARCH_LIMIT = 10
MAX_UPLOAD_BYTES = 100 * 1024 * 1024

DEFAULT_MANIFEST = "upload_manifest.json"
DEFAULT_REPORT_DIR = "reports"

SYSTEM_PROMPT = (
    "你是严格基于给定资料回答的问答助手。\n"
    "规则：\n"
    "1. 只能使用【资料片段】中的内容作答，不得补充片段之外的知识、推测或常识。\n"
    "2. 每一个结论后面必须用 [编号] 标注依据的片段，编号只能是给定片段的编号。\n"
    "3. 多篇片段观点不同时，分别说明各自主张及其成立条件，不要合并成一个结论。\n"
    f"4. 片段无法支撑问题时，只回答「{INSUFFICIENT}」四个字，不要给出任何推测。\n"
)


class ToolError(Exception):
    """可预期的工具错误，用于向用户输出简洁原因而非堆栈。"""


# --------------------------------------------------------------------------
# 凭证与脱敏
# --------------------------------------------------------------------------
def load_secret() -> str:
    secret = (os.environ.get(SECRET_ENV) or "").strip()
    if not secret:
        raise ToolError(
            f"未检测到环境变量 {SECRET_ENV}。请先在当前终端设置 Access Secret 后重试"
            "（获取地址：https://developer.zhihu.com/profile）。"
        )
    return secret


def redact(text: str, secret: str | None) -> str:
    """从任意输出中擦除凭证字面量。"""
    out = "" if text is None else str(text)
    if secret:
        out = out.replace(secret, "***REDACTED***")
        if len(secret) > 12:
            out = out.replace(secret[:12], "***REDACTED***")
    return out


def now_iso() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z")


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------
def _headers(secret: str, content_type: str) -> dict:
    return {
        "Authorization": f"Bearer {secret}",
        "X-Request-Timestamp": str(int(time.time())),
        "Content-Type": content_type,
    }


def _request(req: urllib.request.Request, secret: str, timeout: int) -> dict:
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            status = resp.status
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        raise ToolError(
            f"HTTP {exc.code} {req.get_method()} {req.selector}："
            f"{redact(raw.strip()[:600], secret)}"
        ) from None
    except urllib.error.URLError as exc:
        raise ToolError(
            f"网络请求失败 {req.get_method()} {req.selector}：{redact(str(exc.reason), secret)}"
        ) from None

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        raise ToolError(
            f"服务端返回非 JSON 内容（HTTP {status}）：{redact(raw.strip()[:400], secret)}"
        ) from None

    code = payload.get("Code")
    if code not in (None, 0):
        raise ToolError(
            f"接口返回业务错误 Code={code} Message="
            f"{redact(str(payload.get('Message')), secret)}"
        )
    if isinstance(payload.get("error"), dict):
        err = payload["error"]
        raise ToolError(
            f"接口返回错误 code={err.get('code')} message={redact(str(err.get('message')), secret)}"
        )
    return payload


def api_post_json(path: str, body: dict, secret: str, timeout: int = 120) -> dict:
    req = urllib.request.Request(
        API_BASE + path,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers=_headers(secret, "application/json"),
        method="POST",
    )
    return _request(req, secret, timeout)


def api_get(path: str, params: dict, secret: str, timeout: int = 30) -> dict:
    query = urllib.parse.urlencode({k: v for k, v in params.items() if v not in (None, "")})
    url = API_BASE + path + (f"?{query}" if query else "")
    req = urllib.request.Request(url, headers=_headers(secret, "application/json"), method="GET")
    return _request(req, secret, timeout)


def api_upload_file(kb_id: str, file_path: str, secret: str, timeout: int = 300) -> dict:
    """以 multipart/form-data 上传单个本地文件。字段名经实测核对：KnowledgeBaseID / File。"""
    with open(file_path, "rb") as fh:
        content = fh.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise ToolError(f"文件超过 100 MiB 上限：{file_path}")

    boundary = uuid.uuid4().hex
    file_name = os.path.basename(file_path)
    body = b"".join(
        [
            f'--{boundary}\r\nContent-Disposition: form-data; name="KnowledgeBaseID"\r\n\r\n'
            f"{kb_id}\r\n".encode("utf-8"),
            f'--{boundary}\r\nContent-Disposition: form-data; name="File"; '
            f'filename="{file_name}"\r\nContent-Type: text/markdown\r\n\r\n'.encode("utf-8"),
            content,
            b"\r\n",
            f"--{boundary}--\r\n".encode("utf-8"),
        ]
    )
    req = urllib.request.Request(
        API_BASE + UPLOAD_PATH,
        data=body,
        headers=_headers(secret, f"multipart/form-data; boundary={boundary}"),
        method="POST",
    )
    return _request(req, secret, timeout)


# --------------------------------------------------------------------------
# Markdown 解析：标题 / 作者 / 原文 URL
# --------------------------------------------------------------------------
def parse_markdown(path: str) -> dict:
    """读取本地 Markdown，抽取标题、作者、原文 URL 与正文。

    支持两种来源：
      1. YAML front matter（title / author / url 或 source_url）；
      2. 正文首个一级标题，以及 `作者：xxx`、`原文：http...` 这类行。
    """
    if not os.path.isfile(path):
        raise ToolError(f"找不到文件：{path}")
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()

    meta = {"title": "", "author": "", "source_url": ""}
    body = text

    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            front = text[3:end]
            body = text[end + 4 :].lstrip("\n")
            for line in front.splitlines():
                if ":" not in line:
                    continue
                key, _, value = line.partition(":")
                key = key.strip().lower()
                value = value.strip().strip("\"'")
                if key == "title":
                    meta["title"] = value
                elif key in ("author", "作者"):
                    meta["author"] = value
                elif key in ("url", "source_url", "原文", "原文链接"):
                    meta["source_url"] = value

    if not meta["title"]:
        m = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
        meta["title"] = m.group(1).strip() if m else os.path.splitext(os.path.basename(path))[0]
    if not meta["author"]:
        m = re.search(r"^\s*(?:作者|Author)\s*[：:]\s*(.+)$", body, re.MULTILINE | re.IGNORECASE)
        meta["author"] = m.group(1).strip() if m else ""
    if not meta["source_url"]:
        m = re.search(
            r"^\s*(?:原文(?:链接)?|Source|URL)\s*[：:]\s*(\S+)$", body, re.MULTILINE | re.IGNORECASE
        )
        meta["source_url"] = m.group(1).strip() if m else ""

    meta["body"] = body
    meta["sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    meta["path"] = os.path.abspath(path)
    meta["file_name"] = os.path.basename(path)
    return meta


# --------------------------------------------------------------------------
# 上传映射表（内容 ID ↔ 来源）
# --------------------------------------------------------------------------
def load_manifest(path: str) -> dict:
    if not os.path.isfile(path):
        return {"version": 1, "entries": []}
    with open(path, "r", encoding="utf-8") as fh:
        try:
            data = json.load(fh)
        except json.JSONDecodeError:
            raise ToolError(f"映射文件损坏，无法解析：{path}") from None
    data.setdefault("version", 1)
    data.setdefault("entries", [])
    return data


def save_manifest(path: str, data: dict) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def find_entry(manifest: dict, kb_id: str, sha256: str) -> dict | None:
    for entry in manifest["entries"]:
        if entry.get("knowledge_base_id") == kb_id and entry.get("sha256") == sha256:
            return entry
    return None


def source_index(manifest: dict) -> dict:
    """RecallContentID -> 来源信息，用于把检索结果映射回标题 / 作者 / 原文。"""
    index = {}
    for entry in manifest["entries"]:
        cid = entry.get("recall_content_id")
        if cid:
            index[cid] = entry
    return index


# --------------------------------------------------------------------------
# upload 子命令
# --------------------------------------------------------------------------
def cmd_upload(args: argparse.Namespace) -> int:
    secret = load_secret()
    manifest_path = args.manifest
    manifest = load_manifest(manifest_path)
    kb_id = args.kb_id.strip()
    if not kb_id:
        raise ToolError("--kb-id 不能为空。")

    results = []
    exit_code = 0
    for path in args.files:
        try:
            meta = parse_markdown(path)
        except ToolError as exc:
            print(f"[跳过] {path}：{exc}")
            results.append({"file": path, "status": "error", "error": str(exc)})
            exit_code = 1
            continue

        existing = find_entry(manifest, kb_id, meta["sha256"])
        if existing and not args.force:
            print(
                f"[已存在] {meta['file_name']} 内容未变化，跳过上传"
                f"（RecallContentID={existing['recall_content_id']}）。"
                " 需要强制重传请加 --force。"
            )
            results.append({"file": path, "status": "skipped", "entry": existing})
            continue

        print(f"[上传] {meta['file_name']} -> 知识库 {kb_id} ...")
        try:
            resp = api_upload_file(kb_id, meta["path"], secret)
        except ToolError as exc:
            print(f"[失败] {meta['file_name']}：{exc}")
            results.append({"file": path, "status": "error", "error": str(exc)})
            exit_code = 1
            continue

        data = resp.get("Data") or {}
        entry = {
            "knowledge_base_id": data.get("KnowledgeBaseID", kb_id),
            "recall_content_id": data.get("RecallContentID", ""),
            "remote_file_name": data.get("FileName", meta["file_name"]),
            "remote_title": data.get("Title", ""),
            "file_size": data.get("FileSize"),
            "local_path": meta["path"],
            "sha256": meta["sha256"],
            "title": meta["title"],
            "author": meta["author"],
            "source_url": meta["source_url"],
            "uploaded_at": now_iso(),
        }
        manifest["entries"] = [
            e
            for e in manifest["entries"]
            if not (
                e.get("knowledge_base_id") == entry["knowledge_base_id"]
                and e.get("sha256") == entry["sha256"]
            )
        ]
        manifest["entries"].append(entry)
        save_manifest(manifest_path, manifest)
        print(
            f"[成功] {entry['title']}｜作者：{entry['author'] or '未标注'}"
            f"｜RecallContentID={entry['recall_content_id']}"
        )
        results.append({"file": path, "status": "uploaded", "entry": entry})

    ok = sum(1 for r in results if r["status"] == "uploaded")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    failed = sum(1 for r in results if r["status"] == "error")
    print(
        f"\n上传完成：成功 {ok}，跳过 {skipped}，失败 {failed}。"
        f"\n内容 ID 与来源映射已保存到：{manifest_path}"
    )
    if ok:
        print("提示：知识库需要服务端解析入库，刚上传的文档可能需要数分钟才能被检索到。")
    return exit_code


def cmd_bases(args: argparse.Namespace) -> int:
    secret = load_secret()
    resp = api_get(BASES_PATH, {"Scope": args.scope}, secret)
    items = (resp.get("Data") or {}).get("Items") or []
    if not items:
        print("当前账号下没有可访问的知识库。")
        return 0
    print(f"可访问知识库（Scope={args.scope}）：")
    for item in items:
        flag = "（默认）" if item.get("IsDefault") else ""
        print(
            f"  - {item.get('KnowledgeBaseID')}  {item.get('Name')}{flag}"
            f"  内容数={item.get('ContentCount')}  关系={item.get('Relation')}"
            f"  可见性={item.get('Visibility')}"
        )
    return 0


# --------------------------------------------------------------------------
# 检索与片段整理
# --------------------------------------------------------------------------
def kb_search(query: str, kb_ids: list[str], limit: int, secret: str) -> dict:
    """只按 KnowledgeBaseIDs 检索；刻意不传 RecallScopes，避免扩大召回范围。"""
    body = {"Query": query, "KnowledgeBaseIDs": kb_ids, "Limit": limit}
    assert "RecallScopes" not in body, "ask 命令不得传 RecallScopes"
    return api_post_json(SEARCH_PATH, body, secret, timeout=60)


def build_passages(resp: dict, kb_ids: list[str], sources: dict) -> tuple[list[dict], list[str]]:
    """把服务端返回整理成带编号的片段，并校验每条结果的知识库 ID。"""
    items = (resp.get("Data") or {}).get("Items") or []
    allowed = set(kb_ids)
    passages, violations = [], []
    number = 0
    for item in items:
        kb_id = str(item.get("KnowledgeBaseID") or "")
        if kb_id and kb_id not in allowed:
            violations.append(
                f"返回片段的 KnowledgeBaseID={kb_id} 不在请求范围 {sorted(allowed)} 内，已丢弃。"
            )
            continue
        chunks = item.get("Content")
        if isinstance(chunks, str):
            chunks = [chunks]
        text = "\n".join(c.strip() for c in (chunks or []) if str(c).strip()).strip()
        if not text:
            continue
        number += 1
        cid = item.get("RecallContentID") or ""
        src = sources.get(cid, {})
        passages.append(
            {
                "number": number,
                "knowledge_base_id": kb_id,
                "recall_content_id": cid,
                "doc_name": item.get("DocName") or src.get("remote_file_name") or "",
                "title": src.get("title") or item.get("DocName") or "",
                "author": src.get("author", ""),
                "source_url": src.get("source_url", ""),
                "text": text,
            }
        )
    return passages, violations


def format_context(passages: list[dict]) -> str:
    blocks = []
    for p in passages:
        head = f"[{p['number']}] 标题：{p['title'] or p['doc_name'] or '未命名文档'}"
        if p["author"]:
            head += f"｜作者：{p['author']}"
        if p["source_url"]:
            head += f"｜原文：{p['source_url']}"
        blocks.append(f"{head}\n{p['text']}")
    return "【资料片段】\n" + "\n\n".join(blocks)


def ask_model(question: str, passages: list[dict], model: str, secret: str) -> dict:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"{format_context(passages)}\n\n【问题】\n{question}\n\n"
            f"请只依据上面的片段回答，并在结论后标注 [编号]。若片段无法支撑，只回答「{INSUFFICIENT}」。",
        },
    ]
    resp = api_post_json(
        CHAT_PATH, {"model": model, "messages": messages, "stream": False}, secret, timeout=180
    )
    choices = resp.get("choices") or []
    message = (choices[0].get("message") or {}) if choices else {}
    return {
        "content": (message.get("content") or "").strip(),
        "model": resp.get("model", model),
        "id": resp.get("id", ""),
        "finish_reason": choices[0].get("finish_reason") if choices else "",
    }


def check_citations(answer: str, passages: list[dict]) -> tuple[list[int], list[str]]:
    """校验回答中的引用编号必须落在检索片段编号范围内。"""
    cited = sorted({int(n) for n in re.findall(r"\[(\d{1,2})\]", answer)})
    valid = {p["number"] for p in passages}
    problems = []
    bad = [n for n in cited if n not in valid]
    if bad:
        problems.append(f"回答引用了不存在的片段编号 {bad}，有效编号为 {sorted(valid)}。")
    if not cited and INSUFFICIENT not in answer:
        problems.append("回答给出了结论但没有标注任何片段编号。")
    return cited, problems


# --------------------------------------------------------------------------
# 报告
# --------------------------------------------------------------------------
def write_report(path: str, record: dict) -> str:
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    lines = [
        "# 知乎知识库检索验证报告",
        "",
        f"- 生成时间：{record['generated_at']}",
        f"- 问题：{record['question']}",
        f"- 检索知识库：{', '.join(record['knowledge_base_ids'])}",
        f"- 召回范围参数：未传 RecallScopes（严格限定在上述知识库）",
        f"- 检索片段数：{len(record['passages'])}",
        f"- 生成模型：{record.get('model') or '未调用（资料不足）'}",
        "",
        "## 检索结果",
        "",
    ]
    if record["passages"]:
        for p in record["passages"]:
            lines += [
                f"### [{p['number']}] {p['title'] or p['doc_name'] or '未命名文档'}",
                "",
                f"- KnowledgeBaseID：{p['knowledge_base_id']}",
                f"- RecallContentID：{p['recall_content_id']}",
                f"- 作者：{p['author'] or '未标注'}",
                f"- 原文 URL：{p['source_url'] or '未标注'}",
                "",
                "```text",
                p["text"],
                "```",
                "",
            ]
    else:
        lines += ["无命中片段。", ""]

    lines += ["## 回答", "", record["answer"] or "（无）", "", "## 校验", ""]
    lines.append(f"- 返回知识库 ID 校验：{record['kb_check']}")
    lines.append(f"- 回答引用编号：{record['citations'] or '无'}")
    lines.append(f"- 引用编号校验：{record['citation_check']}")
    lines += ["", "## 来源", ""]
    if record["passages"]:
        for p in record["passages"]:
            lines.append(
                f"- [{p['number']}] {p['title'] or p['doc_name']}"
                f"｜作者：{p['author'] or '未标注'}"
                f"｜原文：{p['source_url'] or '未标注'}"
            )
    else:
        lines.append("- 无")

    lines += ["", "## 错误与告警", ""]
    if record["errors"]:
        lines += [f"- {e}" for e in record["errors"]]
    else:
        lines.append("- 无")
    lines.append("")

    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return path


def default_report_path(directory: str, question: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = re.sub(r"[^\w\u4e00-\u9fff]+", "-", question)[:24].strip("-") or "query"
    return os.path.join(directory, f"{stamp}-{slug}.md")


# --------------------------------------------------------------------------
# ask 子命令
# --------------------------------------------------------------------------
def cmd_ask(args: argparse.Namespace) -> int:
    secret = load_secret()
    kb_ids = [k.strip() for k in args.kb_id if k.strip()]
    if not kb_ids:
        raise ToolError("至少需要一个 --kb-id。")
    limit = max(1, min(args.limit, MAX_SEARCH_LIMIT))
    manifest = load_manifest(args.manifest)
    sources = source_index(manifest)

    record = {
        "generated_at": now_iso(),
        "question": args.question,
        "knowledge_base_ids": kb_ids,
        "passages": [],
        "answer": "",
        "model": "",
        "citations": [],
        "kb_check": "未执行",
        "citation_check": "未执行",
        "errors": [],
    }

    print(f"问题：{args.question}")
    print(f"检索知识库：{', '.join(kb_ids)}（不传 RecallScopes）")

    try:
        resp = kb_search(args.question, kb_ids, limit, secret)
    except ToolError as exc:
        record["errors"].append(f"检索失败：{exc}")
        record["answer"] = f"{INSUFFICIENT}（检索接口调用失败）"
        report = write_report(
            args.report or default_report_path(args.report_dir, args.question), record
        )
        print(f"检索失败：{exc}")
        print(f"报告已写入：{report}")
        return 1

    passages, violations = build_passages(resp, kb_ids, sources)
    record["passages"] = passages
    record["errors"].extend(violations)
    record["kb_check"] = (
        "通过：所有片段均来自指定知识库"
        if not violations
        else f"不通过：{len(violations)} 条片段超出指定知识库，已丢弃"
    )

    print(f"\n检索到 {len(passages)} 条片段：")
    if not passages:
        print("  （无命中）")
    for p in passages:
        preview = p["text"].replace("\n", " ")
        preview = preview[:160] + ("..." if len(preview) > 160 else "")
        print(f"\n  [{p['number']}] {p['title'] or p['doc_name'] or '未命名文档'}")
        print(f"      KnowledgeBaseID：{p['knowledge_base_id']}")
        print(f"      作者：{p['author'] or '未标注'}｜原文：{p['source_url'] or '未标注'}")
        print(f"      片段：{preview}")

    if not passages:
        record["answer"] = INSUFFICIENT
        record["citation_check"] = "跳过：无命中片段，未调用生成模型"
        print(f"\n回答：{INSUFFICIENT}")
        print("（指定知识库内没有相关资料，未调用生成模型。）")
        report = write_report(
            args.report or default_report_path(args.report_dir, args.question), record
        )
        print(f"\n报告已写入：{report}")
        return 0

    try:
        result = ask_model(args.question, passages, args.model, secret)
    except ToolError as exc:
        record["errors"].append(f"生成失败：{exc}")
        record["answer"] = f"{INSUFFICIENT}（检索成功但生成接口调用失败）"
        record["citation_check"] = "未执行：生成失败"
        report = write_report(
            args.report or default_report_path(args.report_dir, args.question), record
        )
        print(f"\n生成失败：{exc}")
        print(f"报告已写入：{report}")
        return 1

    record["answer"] = result["content"]
    record["model"] = result["model"]
    cited, problems = check_citations(result["content"], passages)
    record["citations"] = cited
    record["citation_check"] = "通过" if not problems else "不通过：" + "；".join(problems)
    record["errors"].extend(problems)

    print(f"\n回答（{result['model']}）：\n{result['content']}")
    print(f"\n校验：知识库 ID {record['kb_check']}｜引用编号 {record['citation_check']}")

    report = write_report(args.report or default_report_path(args.report_dir, args.question), record)
    print(f"报告已写入：{report}")
    return 0 if not record["errors"] else 2


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="zhihu_kb_cli.py",
        description="知乎官方知识库上传 / 检索 / 直答验证工具（凭证仅从环境变量 ZHIHU_ACCESS_SECRET 读取）。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例：\n"
            "  python zhihu_kb_cli.py bases\n"
            "  python zhihu_kb_cli.py upload --kb-id 7707197405756222000 articles/a.md articles/b.md\n"
            "  python zhihu_kb_cli.py ask --kb-id 7707197405756222000 --question \"意义来自哪里？\"\n"
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_bases = sub.add_parser("bases", help="列出当前账号可访问的知识库 ID")
    p_bases.add_argument(
        "--scope", default="all", choices=["all", "created", "subscribed"], help="默认 all"
    )
    p_bases.set_defaults(func=cmd_bases)

    p_up = sub.add_parser("upload", help="上传本地 Markdown 并保存内容 ID 与来源映射")
    p_up.add_argument("files", nargs="+", help="一个或多个本地 Markdown 文件")
    p_up.add_argument("--kb-id", required=True, help="目标知识库 ID")
    p_up.add_argument("--manifest", default=DEFAULT_MANIFEST, help=f"映射文件，默认 {DEFAULT_MANIFEST}")
    p_up.add_argument(
        "--force", action="store_true", help="内容未变化时也强制重传（默认按 sha256 去重，不重复上传）"
    )
    p_up.set_defaults(func=cmd_upload)

    p_ask = sub.add_parser("ask", help="只检索指定知识库并基于片段生成带引用的回答")
    p_ask.add_argument("--question", required=True, help="要验证的问题")
    p_ask.add_argument("--kb-id", action="append", required=True, help="知识库 ID，可重复传入")
    p_ask.add_argument("--limit", type=int, default=5, help=f"检索片段数 1-{MAX_SEARCH_LIMIT}，默认 5")
    p_ask.add_argument("--model", default=DEFAULT_MODEL, choices=list(ALLOWED_MODELS))
    p_ask.add_argument("--manifest", default=DEFAULT_MANIFEST, help="来源映射文件")
    p_ask.add_argument("--report", default="", help="报告输出路径；省略则自动命名")
    p_ask.add_argument("--report-dir", default=DEFAULT_REPORT_DIR, help=f"报告目录，默认 {DEFAULT_REPORT_DIR}")
    p_ask.set_defaults(func=cmd_ask)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    secret = os.environ.get(SECRET_ENV)
    try:
        return args.func(args)
    except ToolError as exc:
        print(f"错误：{redact(str(exc), secret)}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n已取消。", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
