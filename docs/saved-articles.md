# 文章收藏（扩展 + 网页）

日期：2026-11-23。状态：**扩展采集、后端落库、网页列表已完成**；泡泡仍是演示页，本功能不依赖泡泡。

## 这是什么

“文章收藏”收藏的是**稍后还想回来看的知乎内容**，和知乎自己的收藏夹不是同一件事：

- 不写入知乎收藏夹（官方没有写接口，也不调私有接口）；
- 不依赖泡泡；删掉某篇文章的所有泡泡，收藏仍然保留；
- 数据存在 ThinkSpace 的 SQLite，不读知乎 Cookie。

## 使用

1. 扩展配对完成后，打开知乎回答、专栏文章、想法或视频页；
2. 点右下角「想法」打开面板；
3. 点「收藏这篇文章」；已收藏时按钮变为「已收藏 · 点击取消」；
4. 网页登录后，在「文章收藏」标签查看列表，可打开原文或取消收藏。

## 数据表

```sql
saved_articles (
    user_id, article_key, source_url, content_type,
    content_id, title, author_name, saved_at,
    PRIMARY KEY (user_id, article_key)
)
```

- 按 `(user_id, article_key)` 唯一；重复收藏保持首次 `saved_at`，只补全标题/作者；
- `user_id` 引用 `users(id)`，删除用户时级联清理；
- 与 `articles`、`bubbles` 无外键关系，删泡泡不会删收藏。

## 接口

| 方法 | 路径 | 作用 |
|---|---|---|
| POST | `/api/saved` | 收藏文章（已存在返回 200，新建 201） |
| GET | `/api/saved` | 收藏列表（`limit` / `offset`） |
| GET | `/api/saved/status?source_url=...` | 查询当前文章是否已收藏 |
| DELETE | `/api/saved/{article_key}` | 取消收藏（204 / 404） |

`POST /api/saved`：

```json
{
  "source_url": "https://www.zhihu.com/question/10001/answer/20001",
  "title": "文章标题",
  "author_name": "作者"
}
```

响应：

```json
{
  "saved": true,
  "article": {
    "article_key": "answer:20001",
    "source_url": "https://www.zhihu.com/question/10001/answer/20001",
    "content_type": "answer",
    "content_id": "20001",
    "title": "文章标题",
    "author_name": "作者",
    "saved_at": 1794900000
  }
}
```

`source_url` 必须是知乎回答、专栏文章、想法或视频的完整 HTTPS 链接；追踪参数会被去掉，非法链接返回 `422 INVALID_SOURCE_URL`。

## 扩展改动

- `content.js`：面板新增「收藏这篇文章」；打开面板、切换页面时查询收藏状态；点击后收藏/取消。
- `background.js`：新增 `saveArticle` / `unsaveArticle` / `getSaved` 三个消息处理。
- `content.css`：收藏按钮样式。

扩展仍然只使用 `storage` 权限和本地 API，不读取知乎 Cookie。

## 网页改动

- [App.vue](../web/src/App.vue) 新增「文章收藏」标签；
- 列表展示标题、作者、收藏时间，可打开原文或取消收藏；
- 与「文章泡泡」是两个独立标签。

## 验证

- `api/tests/test_saved.py`：7 项通过；
- 全量 `pytest api/tests`：**98 passed**；
- `npm --prefix web run build`：类型检查与构建通过。

覆盖：URL 规范化、重复收藏幂等、列表/状态/取消、跨用户隔离、扩展 token 可收藏、非法 URL、未登录、删泡泡不影响收藏。

## 边界

- 不支持收藏到知乎收藏夹；
- 不支持笔记/标签/稍后读分类；
- 未做收藏时间修改、批量操作、离线队列；
- 扩展尚未做自动化测试，需手动加载验证。
