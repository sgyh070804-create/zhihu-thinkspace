"""E 模块：有限轮次的角色调度。

这一层只回答两个问题：**下一句该谁说、说什么**。它不拥有讨论状态：

- 读讨论和消息走 `DiscussionStore` 的公开方法；
- 写回走 `append_message`，消息状态在落库时确定，不产生流式中间态；
- 只生成 AI 角色的发言，绝不伪造用户发言，也不替用户确认观点。

D 模块（`discussion_store.py` / `discussions.py`）保持只负责存储和 HTTP；
模型调用放在 `providers/model.py`，这里只依赖 `ModelClient` 协议。
"""

from __future__ import annotations

import logging
import threading

from .discussion_store import (
    CLOSED_STATUSES,
    STATUS_ACTIVE,
    STATUS_PAUSED,
    USER_ROLE,
    DiscussionClosed,
    DiscussionNotFound,
    DiscussionStore,
)
from .providers.model import ModelClient, ModelError

logger = logging.getLogger("thinkspace.discussion_engine")

# 拼上下文时最多带多少条消息、总共多少字。不做 token 估算：字数上限更容易解释和测试。
MAX_CONTEXT_MESSAGES = 12
MAX_CONTEXT_CHARS = 4000
# 单条 AI 发言的字数上限。短是刻意的：讨论室不是长文生成器。
MAX_REPLY_CHARS = 220

# 三个角色共用同一套行为约束，差异只在职责。真实模型接入后这些就是系统提示词。
ROLE_PROMPTS = {
    "explorer": (
        "你是这场讨论的探索者。职责是寻找另一种可能：提出具体情境、替代解释或"
        "尚未被提到的角度。语气轻、短、留白，不替用户下结论。"
    ),
    "skeptic": (
        "你是这场讨论的质疑者。职责是检查前提、给出反例、指出证据缺口。"
        "提问要具体，不为反对而反对，也不把改变立场当作胜利。"
    ),
    "weaver": (
        "你是这场讨论的归纳者。职责是收拢线索，区分已确认、待验证和仍有分歧的部分。"
        "不强行达成共识，也不替用户做最终判断。"
    ),
}

STYLE_RULES = (
    "通用要求：用中文，1 到 3 句，不超过 120 字；不要写标题、列表或 Markdown；"
    "不要编造原文引用；不要把推测说成事实；不要每轮都追问；"
    "可以有保留地赞同、修正或指出分歧。"
)


class EngineBusy(Exception):
    """同一条讨论正在生成，拒绝并发推进。"""


class EnginePaused(Exception):
    """讨论处于暂停状态，不推进 AI 发言。暂停的是编排，不是用户补充。"""


def select_role(discussion: dict, messages: list[dict]) -> str | None:
    """选下一位发言的 AI 角色；没有可发言角色时返回 None。

    规则顺序（可测试，不依赖模型）：

    1. 用户最后一条消息里点名了某个角色（显示名或 role_id）→ 选它；
    2. 否则按关键词给在座角色打分：问句/证据偏向质疑者，总结/收敛偏向归纳者，
       假设/另一种可能偏向探索者；
    3. 仍不明显时，选最久没说过话的角色，避免同一个人连说两轮。
    """
    seated = [
        item
        for item in discussion.get("participants", [])
        if item.get("role_id") != USER_ROLE
    ]
    if not seated:
        return None

    last_user = next(
        (item for item in reversed(messages) if item.get("role_id") == USER_ROLE), None
    )
    text = (last_user or {}).get("body", "")

    # 1. 点名优先：用户说“质疑者，你怎么看”时，不要让启发式覆盖他的选择。
    for item in seated:
        role_id = item["role_id"]
        display_name = item.get("display_name", "")
        if (display_name and display_name in text) or role_id in text:
            return role_id

    # 2. 关键词打分。每组最多加 2 分，避免“为什么”和“反例”同时出现时把分数堆爆。
    scores = {item["role_id"]: 0 for item in seated}
    keyword_groups = {
        "skeptic": ("为什么", "证据", "依据", "反例", "凭什么", "真的"),
        "weaver": ("总结", "归纳", "所以", "因此", "整体", "共同", "收拢", "梳理"),
        "explorer": ("如果", "假设", "另一种", "可能", "换个角度", "会不会", "也许"),
    }
    for role_id, keywords in keyword_groups.items():
        if role_id in scores and any(keyword in text for keyword in keywords):
            scores[role_id] += 2
    if text and text.rstrip().endswith(("？", "?")):
        # 问号是弱信号，只加 1 分，避免所有提问都被质疑者接走。
        if "skeptic" in scores:
            scores["skeptic"] += 1

    best = max(scores.values())
    if best > 0:
        for item in seated:  # 按座位顺序打破平局，结果稳定
            if scores[item["role_id"]] == best:
                return item["role_id"]

    # 3. 兜底：最久没说话的角色；没说过话的排最前。
    last_spoken: dict[str, int] = {}
    for index, message in enumerate(messages):
        last_spoken[message["role_id"]] = index
    return min(
        seated,
        key=lambda item: (last_spoken.get(item["role_id"], -1), item["seat"]),
    )["role_id"]


def build_context(
    discussion: dict,
    messages: list[dict],
    role_id: str,
    *,
    max_messages: int = MAX_CONTEXT_MESSAGES,
    max_chars: int = MAX_CONTEXT_CHARS,
) -> tuple[str, list[dict[str, str]]]:
    """拼出系统提示和最近对话，返回 (system, conversation)。

    从最新往回保留消息，超预算就从最旧的一条开始丢；至少保留一条用户发言，
    否则模型会失去当前问题的锚点。
    """
    names = {
        item["role_id"]: item.get("display_name", item["role_id"])
        for item in discussion.get("participants", [])
    }
    names.setdefault(USER_ROLE, "你")

    system = (
        f"{ROLE_PROMPTS.get(role_id, ROLE_PROMPTS['weaver'])}\n"
        f"{STYLE_RULES}\n"
        f"讨论主题：{discussion['topic']}"
    )

    selected = list(messages[-max_messages:])
    if not selected:
        return system, []

    def total_chars(items: list[dict]) -> int:
        return len(system) + sum(len(item.get("body", "")) for item in items)

    while len(selected) > 1 and total_chars(selected) > max_chars:
        selected.pop(0)

    conversation: list[dict[str, str]] = []
    for item in selected:
        body = item.get("body", "").strip()
        # 单条超长发言按字符截断，保留开头，避免一条消息吃掉整个上下文预算。
        if len(body) > 800:
            body = body[:800] + "…"
        conversation.append(
            {
                "role_id": item["role_id"],
                "display_name": names.get(item["role_id"], item["role_id"]),
                "body": body,
            }
        )
    return system, conversation


class DiscussionEngine:
    """把“选角色 → 拼上下文 → 调模型 → 写回消息”串起来。"""

    def __init__(
        self,
        store: DiscussionStore,
        model: ModelClient,
        *,
        max_context_messages: int = MAX_CONTEXT_MESSAGES,
        max_context_chars: int = MAX_CONTEXT_CHARS,
        max_reply_chars: int = MAX_REPLY_CHARS,
        wait_timeout: float = 5.0,
    ) -> None:
        self.store = store
        self.model = model
        self.max_context_messages = max_context_messages
        self.max_context_chars = max_context_chars
        self.max_reply_chars = max_reply_chars
        # 自动推进时最多排队等这么久；超过仍视为忙碌，避免后台线程无限阻塞。
        self.wait_timeout = wait_timeout
        # 每条讨论一把进程内锁：同一讨论同时只允许一个生成任务。
        # 多进程部署时锁不跨进程，这一点与 D 模块的 SSE 通知限制一致。
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def _lock_for(self, discussion_id: str) -> threading.Lock:
        with self._locks_guard:
            lock = self._locks.get(discussion_id)
            if lock is None:
                lock = threading.Lock()
                self._locks[discussion_id] = lock
            return lock

    def advance(self, user_id: str, discussion_id: str, *, wait: bool = False) -> dict:
        """推进一位 AI 角色发言，返回结果字典。

        返回结构：`{"advanced", "reason", "role_id", "message", "discussion"}`。
        暂停、结束、没有可发言角色、达到轮次上限都属于“没推进”，不算错误；
        只有并发冲突、模型失败、讨论不存在等才抛异常。

        `wait=True` 用于自动推进：前一轮还在生成时排队等一会儿，而不是直接丢弃。
        手动接口保持非阻塞，正在生成时立刻返回 409。
        """
        lock = self._lock_for(discussion_id)
        if wait:
            acquired = lock.acquire(timeout=self.wait_timeout)
        else:
            acquired = lock.acquire(blocking=False)
        if not acquired:
            raise EngineBusy("这条讨论正在生成回复，请稍后再试。")
        try:
            return self._advance_locked(user_id, discussion_id)
        finally:
            lock.release()

    def _advance_locked(self, user_id: str, discussion_id: str) -> dict:
        discussion = self.store.get_discussion(user_id, discussion_id)
        if discussion is None:
            raise DiscussionNotFound("讨论不存在或不属于当前用户。")
        if discussion["status"] in CLOSED_STATUSES:
            state = "停止" if discussion["status"] == "stopped" else "结束"
            raise DiscussionClosed(f"讨论已{state}，不能再推进发言。")
        if discussion["status"] == STATUS_PAUSED:
            raise EnginePaused("讨论已暂停，恢复后才能推进 AI 发言。")

        if int(discussion["turn_index"]) >= int(discussion["max_turns"]):
            # 轮次上限到了就自动收尾，避免前端一直等下一句。
            finished = self.store.finish_discussion(user_id, discussion_id)
            return self._skipped("max_turns", finished)

        messages, _, _ = self.store.list_messages(
            user_id,
            discussion_id,
            newest_first=True,
            limit=self.max_context_messages,
        )
        role_id = select_role(discussion, messages)
        if role_id is None:
            return self._skipped("no_ai_roles", discussion)

        system, conversation = build_context(
            discussion,
            messages,
            role_id,
            max_messages=self.max_context_messages,
            max_chars=self.max_context_chars,
        )
        try:
            text = self.model.complete(
                role_id=role_id,
                system=system,
                topic=discussion["topic"],
                conversation=conversation,
                max_chars=self.max_reply_chars,
            )
        except ModelError:
            raise
        text = (text or "").strip()
        if not text:
            raise ModelError("模型返回了空内容。")
        # 真实模型不一定遵守 max_chars，这里统一兜底，避免一条发言把讨论室刷屏。
        text = text[: self.max_reply_chars].strip()

        # 生成期间用户可能已经暂停或停止；以写回前的状态为准，旧结果直接丢弃。
        current = self.store.get_discussion(user_id, discussion_id)
        if current is None:
            raise DiscussionNotFound("讨论不存在或不属于当前用户。")
        if current["status"] != STATUS_ACTIVE:
            return self._skipped(current["status"], current)

        message, _ = self.store.append_message(
            user_id,
            discussion_id,
            role_id,
            text,
            turn_index=int(current["turn_index"]) + 1,
        )
        updated = self.store.get_discussion(user_id, discussion_id)
        if updated is None:  # pragma: no cover - 刚写入就读不到属于存储故障
            raise DiscussionNotFound("讨论不存在或不属于当前用户。")
        return {
            "advanced": True,
            "reason": None,
            "role_id": role_id,
            "message": message,
            "discussion": updated,
        }

    @staticmethod
    def _skipped(reason: str, discussion: dict) -> dict:
        return {
            "advanced": False,
            "reason": reason,
            "role_id": None,
            "message": None,
            "discussion": discussion,
        }

    def advance_safely(self, user_id: str, discussion_id: str) -> None:
        """后台任务入口：吞掉可预期异常，只记录日志，不影响用户请求。

        自动推进是在用户发言之后触发的；如果讨论被暂停、停止或模型失败，
        用户请求本身已经成功，不应该再抛错。手动 `/advance` 走 `advance`，
        由接口层把异常翻译成明确的状态码。
        """
        try:
            result = self.advance(user_id, discussion_id, wait=True)
        except (DiscussionNotFound, DiscussionClosed, EnginePaused, EngineBusy) as exc:
            logger.info("讨论 %s 未推进：%s", discussion_id, exc)
        except ModelError as exc:
            logger.warning("讨论 %s 模型调用失败：%s", discussion_id, exc)
        except Exception:  # pragma: no cover - 后台任务不能把异常抛回请求
            logger.exception("讨论 %s 自动推进失败", discussion_id)
        else:
            if not result["advanced"]:
                logger.info("讨论 %s 未推进：%s", discussion_id, result["reason"])
