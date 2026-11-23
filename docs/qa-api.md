# 收藏问答（首版）

日期：2026-11-23。状态：**后端本地实现完成，网页「收藏」标签已接通**；回答仍是摘要抽取，不调用生成模型。

实现：`api/app/qa_store.py`（落库）、`api/app/qa.py`（取收藏、检索、回答、引用）、`api/app/qa_api.py`（HTTP）、`api/tests/test_qa.py`（8 个用例）。

## 这版做了什么

- 按“用户 + 收藏夹”创建或复用问答会话；
- 每次提问只在对应收藏夹内检索摘要，返回最多 5 条来源；
- 用户问题、助手回答、引用来源全部写入 SQLite，不再依赖 `localStorage`；
- 没有命中时明确返回“资料不足”，不拿不相关的内容凑数；
- 所有读写按 `user_id` 隔离，扩展 Bearer 身份不能使用问答。

## 这版刻意没做

- **不调用生成模型**：回答由命中的收藏摘要拼成，并明确标注“摘要、不是全文，也没有调用生成模型”。接知乎直答时只替换 `SummaryAnswerModel`，接口和表结构不变。
- **没有全文**：官方收藏接口只返回 `Summary`，引用片段也只能来自摘要；不能把它当逐字原文。
- **没有流式输出、点赞、重新生成、删除会话**。

## 数据表

```sql
qa_sessions(id, user_id, favlist_url_token, favlist_title, created_at, updated_at)
qa_messages(id, session_id, role, body, created_at, seq)
qa_citations(id, message_id, source_url, title, author_name, snippet, content_type, rank, created_at)
```

- 同一用户在同一收藏夹下只保留一个会话，避免每次提问都新建；
- 一轮问答的“用户消息 + 助手消息 + 引用”在同一个事务里写入；
- `qa_sessions.user_id` 引用 `users(id)`，用户删除时级联清理。

## 接口

所有接口都需要网页登录（演示身份或知乎 OAuth）；扩展 token 返回 `401 AUTH_REQUIRED`。

| 方法 | 路径 | 作用 |
|---|---|---|
| POST | `/api/qa/sessions` | 创建或复用会话；新建 `201`，复用 `200` |
| GET | `/api/qa/sessions` | 会话列表（`limit` / `offset`） |
| GET | `/api/qa/sessions/{id}` | 会话详情，含全部消息与引用 |
| POST | `/api/qa/sessions/{id}/messages` | 在收藏夹内提问 |

### 创建会话

```json
POST /api/qa/sessions
{"favlist_url_token": 90001, "favlist_title": "演示收藏夹"}
```

响应：

```json
{
  "id": "…",
  "favlist_url_token": 90001,
  "favlist_title": "演示收藏夹",
  "created_at": 1794900000,
  "updated_at": 1794900000,
  "message_count": 0
}
```

### 提问

```json
POST /api/qa/sessions/{id}/messages
{"question": "为什么阅读时需要记录疑问？"}
```

响应：

```json
{
  "session": {"id": "…", "message_count": 2, "updated_at": 1794900010},
  "question": {"id": "…", "role": "user", "body": "为什么阅读时需要记录疑问？", "citations": []},
  "answer": {
    "id": "…",
    "role": "assistant",
    "body": "根据收藏夹里的摘要，找到 1 条可能相关的资料：…",
    "citations": [
      {
        "source_url": "https://www.zhihu.com/question/10001/answer/20001",
        "title": "演示：为什么阅读时需要记录疑问？",
        "author_name": "演示作者",
        "snippet": "这是本地演示摘要…",
        "content_type": "answer",
        "rank": 1
      }
    ]
  }
}
```

### 读取会话

```json
{
  "id": "…",
  "favlist_url_token": 90001,
  "favlist_title": "演示收藏夹",
  "message_count": 2,
  "messages": [
    {"id": "…", "role": "user", "body": "…", "created_at": 1794900010, "citations": []},
    {"id": "…", "role": "assistant", "body": "…", "created_at": 1794900010, "citations": ["…"]}
  ]
}
```

## 网页接入

[App.vue](../web/src/App.vue) 的「收藏」标签：

- 选中一个收藏夹后，下方出现「问『收藏夹名』」面板；
- 首次选中会创建或复用该收藏夹的会话，并拉取历史消息；
- 提问后把用户消息和回答追加到列表，引用显示标题、作者和摘要，可点开原文；
- 回答区明确标注“只基于收藏摘要，不是全文，当前不调用生成模型”；
- 切换收藏夹会切换到对应会话；退出登录会清空页面状态。

## 检索规则

- 把问题和收藏项的标题/摘要做字符二元组匹配；
- 标题命中权重高于摘要；
- 至少命中两个二元组（短问题除外），避免“什么”“的是”这类常见词带进无关内容；
- 按分数取前 5 条，按 URL 去重；
- 全部不命中时返回空引用和“资料不足”的回答。

这是**字符匹配，不是语义检索**。后续可以换向量检索或知乎知识库检索，接口不变。

## 演示模式

- 演示身份用 `api/app/demo.py` 的虚构收藏；
- 收藏夹按 `Favlists[].UrlToken` 过滤，找不到时回退到全部演示文章；
- 真实知乎身份走 `/api/v1/user/favlist_contents`，最多取 60 条，按 `Paging.NextOffset` 翻页。

## 已验证

`pytest api/tests/test_qa.py`：8 项通过。全量 `pytest api/tests`：**91 passed**。

- 创建/复用会话；
- 提问落库、回答带引用；
- 无命中时明确资料不足且无引用；
- 跨用户读/写/列表全部 404/空；
- 未登录 401；
- 同一数据库换新 app 实例后历史仍在；
- 空问题 422；
- 检索优先标题命中。

## 已知边界

- 收藏摘要不是全文，引用不能当逐字原文；
- 没有限流，单用户可无限提问；
- 真实知乎链路需要 OAuth token，尚未用真实收藏验收；
- 没有删除会话/消息接口，数据只增不减。
