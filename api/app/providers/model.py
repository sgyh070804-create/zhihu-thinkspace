from __future__ import annotations

from typing import Protocol

from ..config import Settings


class ModelError(Exception):
    """模型调用失败。

    编排层（E）会把它翻译成 502 `MODEL_ERROR`，并且不往讨论里写消息——
    不把失败伪装成一条“AI 说错了”，也不留半条残缺发言。
    """


class ModelClient(Protocol):
    """生成式模型的统一入口。

    C（观点融合）和 E（讨论编排）只依赖这个接口，不直接依赖任何厂商 SDK。
    以后接知乎直答时，新增一个实现并在 `build_model` 里切换即可。
    """

    def complete(
        self,
        *,
        role_id: str,
        system: str,
        topic: str,
        conversation: list[dict[str, str]],
        max_chars: int,
    ) -> str: ...


# 假模型的固定句式。故意保持短、具体、不常用力过猛，接近产品文档里的语气要求。
_TEMPLATES = {
    "explorer": (
        "如果换个角度，{hint} 也许还有另一条路径："
        "先把它放进一个具体情境里看看，结论可能会不一样。"
    ),
    "skeptic": (
        "我想先追问：{hint} 在什么条件下会失效？"
        "如果能举出一个反例，边界会更清楚。"
    ),
    "weaver": (
        "把 {hint} 和前面的线索放在一起："
        "目前能确认的是一部分，还需要验证的是另一部分。"
    ),
}


class FakeModel:
    """确定性假模型：不联网、不随机，用于跑通调度链路和测试。

    它只做两件事：从最近一条用户发言里取一个短片段，套进对应角色的固定句式。
    这不是“假装有 AI”，而是让调度、轮次、事件和停止逻辑可以在没有额度的环境下
    被完整验证；真实模型接入前，界面上应当明确这是本地模拟。
    """

    def complete(
        self,
        *,
        role_id: str,
        system: str,
        topic: str,
        conversation: list[dict[str, str]],
        max_chars: int,
    ) -> str:
        last_user = ""
        for item in reversed(conversation):
            if item.get("role_id") == "user":
                last_user = item.get("body", "")
                break
        hint = self._hint(last_user or topic)
        template = _TEMPLATES.get(role_id, _TEMPLATES["weaver"])
        return template.format(hint=hint)[:max_chars]

    @staticmethod
    def _hint(text: str) -> str:
        cleaned = " ".join(text.split())
        if not cleaned:
            return "这个问题"
        return cleaned if len(cleaned) <= 28 else cleaned[:28] + "…"


def build_model(settings: Settings) -> ModelClient:
    """按配置选择模型实现。

    目前只有 fake；接知乎直答时在这里加分支，不让调用方感知具体厂商。
    """
    provider = (settings.model_provider or "fake").strip().lower()
    if provider == "fake":
        return FakeModel()
    raise RuntimeError(f"未知的模型提供方：{provider}（目前只实现 fake）")
