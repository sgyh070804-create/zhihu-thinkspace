"""收藏问答的编排层。

首版刻意不调用生成模型：先把“取收藏 → 检索摘要 → 保存问答与引用”这条链路做通，
回答由收藏摘要拼成，并明确标注“摘要、不是全文”。以后接知乎直答时，只需替换
`SummaryAnswerModel`，接口和落库结构不变。
"""

from __future__ import annotations

import re
from typing import Protocol

from . import demo
from .deps import Identity
from .providers.zhihu import ZhihuClient
from .qa_store import QASessionNotFound, QAStore

MAX_ITEMS = 60
TOP_K = 5
MAX_ANSWER_CHARS = 1200


class QAModel(Protocol):
    def answer(self, *, question: str, sources: list[dict]) -> str: ...


def _normalize(text: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", text or "").lower()


def _bigrams(text: str) -> set[str]:
    cleaned = _normalize(text)
    if not cleaned:
        return set()
    if len(cleaned) <= 2:
        return {cleaned}
    return {cleaned[index : index + 2] for index in range(len(cleaned) - 1)}


def retrieve_sources(question: str, items: list[dict], top_k: int = TOP_K) -> list[dict]:
    """按问题与标题/摘要的二元组重合度排序，返回可核对来源。

    不做向量检索：首版数据只有收藏摘要，字符级重合足够把明显相关的几条挑出来。
    没有命中时返回空列表，由回答层明确说“资料不足”，不拿不相关的内容凑数。
    """
    question_grams = _bigrams(question)
    if not question_grams:
        return []

    scored: list[tuple[int, int, dict]] = []
    # 至少命中两个二元组（短问题除外），避免“什么”“的是”这类常见词把无关内容带进来。
    minimum_matches = min(2, len(question_grams))
    for index, item in enumerate(items):
        title = _normalize(item.get("Title", ""))
        summary = _normalize(item.get("Summary", ""))
        if not title and not summary:
            continue
        matched = {
            gram for gram in question_grams if gram in title or gram in summary
        }
        if len(matched) < minimum_matches:
            continue
        score = 0
        for gram in matched:
            score += title.count(gram) * 3
            score += summary.count(gram)
        if score > 0:
            scored.append((score, index, item))

    scored.sort(key=lambda entry: (-entry[0], entry[1]))
    sources: list[dict] = []
    seen_urls: set[str] = set()
    for _, _, item in scored:
        url = str(item.get("Url") or "")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        author = item.get("Author") or {}
        summary = str(item.get("Summary") or "").strip()
        sources.append(
            {
                "source_url": url,
                "title": str(item.get("Title") or "").strip(),
                "author_name": str(author.get("Name") or "").strip(),
                "snippet": (summary or str(item.get("Title") or "").strip())[:300],
                "content_type": str(item.get("ContentType") or ""),
            }
        )
        if len(sources) >= top_k:
            break
    return sources


class SummaryAnswerModel:
    """基于收藏摘要的抽取式回答。

    这不是生成式模型，也不是对原文的总结：它只把命中的摘要列出来，并提示回原文核对。
    """

    def answer(self, *, question: str, sources: list[dict]) -> str:
        if not sources:
            return (
                "这个收藏夹里没有找到与问题直接相关的摘要，暂时不能给出有依据的回答。"
                "可以换一种问法，或先确认收藏夹里是否收藏了相关资料。"
            )
        lines = [f"根据收藏夹里的摘要，找到 {len(sources)} 条可能相关的资料：", ""]
        for index, source in enumerate(sources, start=1):
            author = source["author_name"] or "未标注作者"
            lines.append(f"{index}. 《{source['title']}》（{author}）")
            lines.append(f"   {source['snippet']}")
            lines.append("")
        lines.append("以上只基于收藏摘要，不是全文，也没有调用生成模型；请打开原文核对后再下判断。")
        return "\n".join(lines)[:MAX_ANSWER_CHARS]


class QAService:
    def __init__(
        self,
        store: QAStore,
        zhihu: ZhihuClient,
        model: QAModel,
        *,
        max_items: int = MAX_ITEMS,
        top_k: int = TOP_K,
    ) -> None:
        self.store = store
        self.zhihu = zhihu
        self.model = model
        self.max_items = max_items
        self.top_k = top_k

    async def _contents(self, identity: Identity, favlist_url_token: int) -> list[dict]:
        if identity.mode == "demo":
            filtered = [
                item
                for item in demo.ARTICLES
                if any(
                    int(favlist.get("UrlToken", 0)) == favlist_url_token
                    for favlist in item.get("Favlists", [])
                )
            ]
            return filtered or demo.ARTICLES

        items: list[dict] = []
        offset = 0
        while len(items) < self.max_items:
            data = await self.zhihu.user_get(
                "/api/v1/user/favlist_contents",
                {
                    "FavlistUrlToken": favlist_url_token,
                    "Offset": offset,
                    "Limit": min(20, self.max_items - len(items)),
                },
                identity.oauth_token or "",
            )
            page = data.get("Items") or []
            if not isinstance(page, list):
                break
            items.extend(item for item in page if isinstance(item, dict))
            paging = data.get("Paging") or {}
            if paging.get("IsEnd") or not page:
                break
            next_offset = paging.get("NextOffset")
            try:
                offset = int(next_offset) if next_offset is not None else offset + len(page)
            except (TypeError, ValueError):
                offset += len(page)
            if offset <= 0:
                break
        return items[: self.max_items]

    async def ask(self, identity: Identity, session_id: str, question: str) -> dict:
        session = self.store.get_session(identity.user_id, session_id)
        if session is None:
            raise QASessionNotFound("问答会话不存在或不属于当前用户。")

        contents = await self._contents(identity, int(session["favlist_url_token"]))
        sources = retrieve_sources(question, contents, self.top_k)
        answer = self.model.answer(question=question, sources=sources)
        question_message, answer_message = self.store.add_exchange(
            identity.user_id, session_id, question, answer, sources
        )
        updated = self.store.get_session(identity.user_id, session_id)
        if updated is None:  # pragma: no cover - 刚写入就读不到属于存储故障
            raise QASessionNotFound("问答会话不存在或不属于当前用户。")
        return {
            "session": updated,
            "question": question_message,
            "answer": answer_message,
        }
