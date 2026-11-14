from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from urllib.parse import urlsplit, urlunsplit


@dataclass(frozen=True)
class SourceInfo:
    article_key: str
    source_url: str
    content_type: str
    content_id: str

    def to_dict(self) -> dict:
        return asdict(self)


def canonicalize_zhihu_url(raw_url: str) -> SourceInfo:
    """只接受可明确识别内容的知乎 HTTPS 地址，并移除追踪参数。"""
    try:
        parsed = urlsplit(raw_url.strip())
    except ValueError as exc:
        raise ValueError("文章来源链接格式不正确。") from exc
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or parsed.username or parsed.password:
        raise ValueError("文章来源必须是知乎内容的 HTTPS 链接。")

    answer = re.fullmatch(r"/question/(\d+)/answer/(\d+)/?", parsed.path)
    article = re.fullmatch(r"/p/(\d+)/?", parsed.path)
    pin = re.fullmatch(r"/pin/(\d+)/?", parsed.path)
    video = re.fullmatch(r"/zvideo/(\d+)/?", parsed.path)

    if host == "www.zhihu.com" and answer:
        question_id, content_id = answer.groups()
        path = f"/question/{question_id}/answer/{content_id}"
        content_type = "answer"
    elif host == "zhuanlan.zhihu.com" and article:
        content_id = article.group(1)
        path = f"/p/{content_id}"
        content_type = "article"
    elif host == "www.zhihu.com" and pin:
        content_id = pin.group(1)
        path = f"/pin/{content_id}"
        content_type = "pin"
    elif host == "www.zhihu.com" and video:
        content_id = video.group(1)
        path = f"/zvideo/{content_id}"
        content_type = "zvideo"
    else:
        raise ValueError("目前支持知乎回答、专栏文章、想法和视频的完整内容链接。")

    return SourceInfo(
        article_key=f"{content_type}:{content_id}",
        source_url=urlunsplit(("https", host, path, "", "")),
        content_type=content_type,
        content_id=content_id,
    )
