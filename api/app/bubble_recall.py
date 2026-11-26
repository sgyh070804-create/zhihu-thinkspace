from __future__ import annotations

import re
import unicodedata

_WORDS = re.compile(r"[\u3400-\u9fff]+|[a-z0-9]+")
_COMMON = {"一个", "自己", "我们", "什么", "如何", "不是", "可以", "这个", "问题", "内容", "知乎", "文章"}


def _terms(text: str) -> set[str]:
    terms: set[str] = set()
    for word in _WORDS.findall(unicodedata.normalize("NFKC", text).lower()):
        if word.isascii():
            if len(word) >= 3:
                terms.add(word)
        else:
            terms.update(word[index:index + 2] for index in range(len(word) - 1))
    return terms - _COMMON


def recall_bubbles(bubbles: list[dict], article_key: str, title: str, selection: str, limit: int = 3) -> list[dict]:
    title_terms, selection_terms = _terms(title), _terms(selection)
    ranked = []
    for bubble in bubbles:
        same_article = bubble["article_key"] == article_key
        if same_article:
            ranked.append((True, 0, bubble))
            continue
        candidates = _terms(" ".join((bubble["title"][:500], bubble["body"], bubble["quote"])))
        in_title, in_selection = candidates & title_terms, candidates & selection_terms
        matched = in_title | in_selection
        if len(matched) < 2 and not any(term.isascii() and len(term) >= 5 for term in matched):
            continue
        ranked.append((False, len(in_title) * 2 + len(in_selection) * 3, bubble))

    ranked.sort(key=lambda result: (result[0], result[1], result[2]["created_at"], result[2]["id"]), reverse=True)
    return [{
        "id": bubble["id"],
        "title": bubble["title"],
        "body": bubble["body"][:240],
        "created_at": bubble["created_at"],
        "match": "same_article" if same_article else "related",
    } for same_article, _, bubble in ranked[:limit]]
