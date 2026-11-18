# 讨论室接口（D 模块）

日期：2026-11-17。状态：**后端本地实现完成，尚未与前端联调**。

实现：`api/app/discussion_store.py`（数据层）、`api/app/discussions.py`（接口）、`api/tests/test_discussions.py`（56 个用例）。

**本模块只负责存储与推送，不产生任何 AI 内容，也不处理流式生成。** 消息在落库时状态就已确定，之后不会改变。探索者、质疑者、归纳者的回复由 E 模块生成完毕后调用存储层写入，D 不伪造、不做增量。

## 1. 三个容易搞混的概念

| 概念 | 是什么 | 用在哪 |
|---|---|---|
| `message.seq` | 消息在**这条讨论内**的顺序号，从 1 连续递增 | 排序、分页 |
| `event.seq` | 事件在**这条讨论内**的序号，从 1 连续递增 | 断线补发、SSE 的 `Last-Event-ID` |
| `message.id` | 全局唯一的 UUID | 客户端去重、引用 |

**两套序号不相等，不能混用。** 举例：创建一条讨论后 `event_seq = 1`、`message_seq = 0`，因为"创建"本身是一个事件，但还不是一句话。

前端 `engine.mjs` 原来用 `serial` 一个字段同时承担这三件事，接后端时必须拆开：去重看 `id`，排序看 `seq`，补发看 `event.seq`。

## 2. 设计要点

| 问题 | 决定 | 原因 |
|---|---|---|
| 事件为什么单独建表 | `discussion_events` 独立存储 | 讨论状态变化需要一条带序号的记录；塞进消息表就表达不了「不是消息的变化」 |
| 事件快照怎么存 | 写入时**固化 JSON**，不读时回查消息表 | 事件是不可变历史；回查会让"改状态"改写过去的事件（已修复，见第 10 节） |
| 断线补发 | SSE（`/stream`）+ 轮询（`/events`）双通道 | SSE 实时，轮询兜底；两者共用同一套事件结构 |
| SSE 怎么等新事件 | 进程内条件变量，写入即唤醒 | 实测发言到订阅端收到 **11 ms**；死等轮询要 1000 ms |
| SSE 用什么生成器 | **异步生成器**（数据库查询放 `anyio.to_thread`） | 同步生成器阻塞在线程里，客户端断开时关闭信号传不进去，`finally` 不执行，名额和线程会永久泄漏——这一点是测试抓出来的 |
| 重复提交 | `client_msg_id` 幂等键 + 部分唯一索引 | 网络抖动重试不能变成两条发言 |
| 角色权限 | 用户端只能以 `user` 发言 | 防止前端伪造"质疑者说过某句话" |
| 并发写序号 | `BEGIN IMMEDIATE` 写锁 + 唯一约束双保险 | 20 线程实测无重号 |
| 分页游标 | 正向用 `after_seq`，往回翻用 `before_seq` | 一个游标扛不了两个方向：`seq > N` 永远取不到比 N 更早的消息 |
| 水位与数据 | 两条查询放在同一个 `BEGIN DEFERRED` 快照里 | 否则并发写入时会返回新消息、却给出旧水位 |
| 连接管理 | 读操作走 `_connection()`，写入走 `_write()`，两者都显式 `close()` | `with sqlite3.connect()` **只提交事务不关闭连接**，靠 GC 会拖延文件句柄释放 |
| 序号范围 | 外部传入的 `after_seq` / `offset` 限制在 64 位有符号整数内 | SQLite 的 INTEGER 是 64 位，超大值会在绑定参数时抛 `OverflowError`（500） |
| 读被写阻塞 | 开启 **WAL** 模式 | SSE 反复读事件时，用户发言不会被卡住；实测连续写入全部成功 |
| 空间归属 | `discussions.space_id` 已建但恒为空 | A 模块空间上线后补一条 `UPDATE`，不必改表 |

## 3. 与前端 `engine.mjs` 的字段映射

| engine.mjs | 后端 | 处理方式 |
|---|---|---|
| `role` | `role_id` | 改名，取值一致 |
| `text` | `body` | 改名 |
| `done` | `status === "completed"` | 布尔改为状态枚举 |
| `serial` | `seq`（排序）/ `event.seq`（补发） | 拆成两个，去重用 `id` |
| `visible` | — | 打字机效果，前端本地计算 |
| `gesture` | — | 动画表现，按 `role_id` 查前端表 |

## 4. 状态机

```
                  ┌──────────┐
      创建 ──────▶ │  active  │
                  └────┬─────┘
             pause │   │ stop / finish
                   ▼   ▼
              ┌────────┐   ┌──────────┐   ┌──────────┐
              │ paused │──▶│ stopped  │   │ finished │
              └────┬───┘   └──────────┘   └──────────┘
         resume    │         （终态）        （终态）
                   ▼
              ┌────────┐
              │ active │
              └────────┘
```

- `active` / `paused`：可以发言，可以继续流转
- `stopped` / `finished`：**终态**，拒绝新消息（409），历史仍可读
- `paused` 期间**允许发言**——暂停的是编排推进，不是用户补充
- 重复调用 `pause`/`resume`/`stop`/`finish` 幂等，不报错
- 对终态调用 `pause`/`resume` 返回 `409 INVALID_STATE`

## 5. 接口清单

所有接口都需要身份（网页 Cookie 或扩展 Bearer），未登录返回 `401 AUTH_REQUIRED`。

| 方法 | 路径 | 作用 |
|---|---|---|
| POST | `/api/discussions` | 创建讨论 |
| GET | `/api/discussions` | 讨论列表（分页） |
| GET | `/api/discussions/{id}` | 讨论详情 |
| POST | `/api/discussions/{id}/pause` | 暂停 |
| POST | `/api/discussions/{id}/resume` | 恢复 |
| POST | `/api/discussions/{id}/stop` | 停止（用户中断） |
| POST | `/api/discussions/{id}/finish` | 结束（正常完成） |
| POST | `/api/discussions/{id}/messages` | 用户发言（幂等） |
| GET | `/api/discussions/{id}/messages` | 读取消息 |
| GET | `/api/discussions/{id}/events` | 拉事件（轮询） |
| GET | `/api/discussions/{id}/stream` | 订阅事件（SSE） |

打开 `http://localhost:8000/docs` 可以看到全部接口并直接试。

**列表与详情**都返回完整的 `participants`（在座角色），前端列讨论时不用再逐条请求详情。列表分页参数 `limit`（1–100，默认 20）、`offset`，响应含 `total` 与 `has_more`，按创建时间倒序、同一秒内按插入顺序倒序，翻页不会抖动。

```json
{"items": [{"id": "…", "topic": "…", "status": "active", "participants": [...]}],
 "total": 3, "limit": 20, "offset": 0, "has_more": false}
```

### 5.1 创建

```json
POST /api/discussions
{"topic": "AI 应该替我们做决定吗？", "max_turns": 6, "role_ids": ["explorer", "skeptic", "weaver"]}
```

| 字段 | 必填 | 约束 |
|---|---|---|
| `topic` | 是 | 1–200 字；首尾空白自动去除，纯空白返回 422 |
| `max_turns` | 否 | 1–20，默认 6 |
| `role_ids` | 否 | 最多 8 个；不传则四个角色全部在座；`user` 永远在座 |

未知角色返回 `422 UNKNOWN_ROLE`，响应里带 `known_roles` 列表。

响应 `201`：

```json
{
  "id": "9f3c…",
  "topic": "AI 应该替我们做决定吗？",
  "status": "active",
  "max_turns": 6,
  "turn_index": 0,
  "message_seq": 0,
  "event_seq": 1,
  "message_count": 0,
  "created_at": 1794900000,
  "updated_at": 1794900000,
  "paused_at": null,
  "stopped_at": null,
  "finished_at": null,
  "participants": [
    {"role_id": "explorer", "display_name": "探索者", "title": "寻找另一种可能", "seat": 0},
    {"role_id": "skeptic",  "display_name": "质疑者", "title": "给观点一点阻力", "seat": 1},
    {"role_id": "weaver",   "display_name": "归纳者", "title": "把线索连成观点", "seat": 2},
    {"role_id": "user",     "display_name": "你",     "title": "这张桌子的一员", "seat": 3}
  ]
}
```

角色定义在后端 `discussion_store.ROLE_CATALOG`，与 `engine.mjs` 的 `roles` 一致，前端不用维护第二份。

### 5.2 用户发言

```json
POST /api/discussions/{id}/messages
{"body": "我想先区分：替我们分析，和替我们决定。", "client_msg_id": "local-1723…", "in_reply_to": null}
```

| 字段 | 必填 | 约束 |
|---|---|---|
| `body` | 是 | 1–4000 字；纯空白返回 422 |
| `client_msg_id` | 否 | ≤64 字；**空字符串或纯空白视为未提供** |
| `in_reply_to` | 否 | 引用同一条讨论内的消息 ID；跨讨论或不存在返回 422 |

响应新建 `201`，幂等命中 `200`：

```json
{"message": {"id": "…", "seq": 1, "role_id": "user", "body": "…", "status": "completed",
             "client_msg_id": "local-1723…", "in_reply_to": null,
             "created_at": 1794900010, "updated_at": 1794900010},
 "created": true}
```

**幂等规则**：同一讨论内相同 `client_msg_id` 只落一条；重复提交返回**首次那条消息**，即使请求体里的 `body` 改过。

**`status` 说明**：通过 HTTP 发的用户消息固定是 `completed`。`failed` / `cancelled` 只由服务端在写入 AI 消息时使用——本模块**没有**把一条消息从成功改成失败的接口，状态在落库时就定了。

### 5.3 读取消息

```
GET /api/discussions/{id}/messages?after_seq=0&limit=50
GET /api/discussions/{id}/messages?newest_first=true&limit=2&before_seq=4
```

**两个方向，两种游标，不要混用**：

| 参数 | 默认 | 说明 |
|---|---|---|
| `after_seq` | 0 | 正向拿新消息：只返回 `seq > after_seq` 的，按升序 |
| `before_seq` | 无 | 往回翻历史：只返回 `seq < before_seq` 中最大的 limit 条；不传表示从最新开始 |
| `limit` | 50 | 1–200 |
| `newest_first` | false | 往回翻时必须为 true；此模式下 `after_seq` 不生效 |

```json
{"items": [...], "message_seq": 5, "has_more": true, "after_seq": 0, "before_seq": null}
```

**往回翻的完整链路**（5 条消息，每页 2 条）：

```
第 1 页  newest_first=true&limit=2                    → [4, 5]，has_more=true
第 2 页  newest_first=true&limit=2&before_seq=4       → [2, 3]，has_more=true
第 3 页  newest_first=true&limit=2&before_seq=2       → [1]，   has_more=false
```

下一页的 `before_seq` 取**上一页返回结果里最小的 `seq`**。

**每页内部都是升序，但更早的一页要插到现有列表的前面**，不是往后追加：

```js
// 第一页之后，列表是 [4, 5]
const older = await fetch(url + '&before_seq=' + list[0].seq).then(r => r.json());
list = [...older.items, ...list];   // 得到 [2, 3, 4, 5]
```

如果写成 `list.push(...older.items)`，会得到 `[4, 5, 2, 3]`，顺序就乱了。

### 5.4 拉事件（轮询）

```
GET /api/discussions/{id}/events?after_seq=0&limit=100
```

```json
{
  "discussion_id": "…",
  "status": "active",
  "event_seq": 4,
  "has_more": false,
  "after_seq": 0,
  "events": [
    {"seq": 1, "type": "discussion.created", "created_at": 1794900000, "message": null},
    {"seq": 2, "type": "message.created", "created_at": 1794900010,
     "message": {"id": "…", "seq": 1, "role_id": "user", "body": "…", "status": "completed",
                 "client_msg_id": null, "in_reply_to": null,
                 "created_at": 1794900010, "updated_at": 1794900010}}
  ]
}
```

事件类型：

| type | 含义 | `message` |
|---|---|---|
| `discussion.created` | 讨论创建 | null |
| `discussion.paused` / `.resumed` | 暂停 / 恢复 | null |
| `discussion.stopped` / `.finished` | 停止 / 结束 | null |
| `message.created` | 消息落库（成功、失败、取消都是这一种） | 消息快照 |

消息的成败体现在快照的 `status` 字段（`completed` / `failed` / `cancelled`），不单独发事件。
**没有 `message.delta`、`message.completed`、`generation.failed`**——本模块不参与生成过程，不产生增量事件。

**事件带消息快照**，客户端拿到事件就能渲染，不必再按 ID 回查。

**快照在写入时固化**：`message.created` 里是消息落库那一刻的完整副本。本模块不允许修改已落库的消息，所以事件与消息表始终一致；快照的意义在于——即使将来增加修改功能、或有人直接改库，历史事件也不会被追溯改写。

### 5.5 订阅事件（SSE）

```
GET /api/discussions/{id}/stream?after_seq=0
Header: Last-Event-ID: 3        ← 浏览器断线重连时自动带上
```

响应 `Content-Type: text/event-stream`：

```
id: 3
event: message.created
data: {"seq": 3, "type": "message.created", "created_at": 1794900010, "message": {...}}

: keep-alive

id: 4
event: stream.end
data: {"status": "stopped"}
```

行为：

- `Last-Event-ID` 与 `after_seq` 二选一，**前者优先**；非法值回退到 `after_seq`
- 有新写入时**立即唤醒**（进程内条件变量），实测延迟 11 ms；1 秒超时只是兜底轮询，也是感知客户端断开的手段
- 15 秒无新事件发一次心跳注释（`: keep-alive`），防止中间层断开
- 讨论进入终态 → 发完积压事件后发 `stream.end` 并关闭连接；帧里带 `retry: 60000`，前端若忘记 `close()`，浏览器会等 60 秒再重连，而不是默认的 3 秒疯狂重试
- 单连接最长 600 秒，超时发 `stream.timeout` 后关闭
- 同时在线订阅数上限 32，超出返回 `503 STREAM_BUSY`（每个连接占一个线程，不能无限开）
- 讨论不存在或不属于当前用户 → 直接 `404`（在流开始前返回，不会出现"连着连着才报错"）

### 5.6 状态流转

四个端点结构一致，都返回完整的讨论对象：

```
POST /api/discussions/{id}/pause
POST /api/discussions/{id}/resume
POST /api/discussions/{id}/stop
POST /api/discussions/{id}/finish
```

### 5.7 推进 AI 发言（E 模块，2026-11-18 新增）

D 模块只负责存储，不生成内容。E 模块在 D 之上做角色调度，代码在
`api/app/discussion_engine.py`、`api/app/providers/model.py` 和
`api/app/discussion_engine_api.py`。

```
POST /api/discussions/{id}/advance
```

响应 `200`：

```json
{
  "advanced": true,
  "reason": null,
  "role_id": "skeptic",
  "message": {"id": "…", "seq": 2, "role_id": "skeptic", "body": "…", "status": "completed"},
  "discussion": {"id": "…", "turn_index": 1, "status": "active", "participants": [{"role_id": "skeptic", "display_name": "质疑者", "seat": 1}, "…"]}
}
```

规则：

- 一次只推进一位在座 AI 角色；`user` 永远不会被自动选中。
- 选人顺序：用户最后一条消息点名了某个角色（显示名或 `role_id`）→ 选它；否则按关键词打分（问句/证据偏向质疑者，总结/收敛偏向归纳者，假设/另一种可能偏向探索者）；仍不明显时选最久没说过话的角色。
- `turn_index` 只在 AI 发言写回时 +1，并与消息在同一个事务里更新；用户消息不推进轮次。
- 达到 `max_turns` 自动 `finish`，返回 `advanced=false, reason="max_turns"`。
- 暂停、停止、没有 AI 角色时不写消息，返回 `advanced=false`；手动接口在暂停时返回 `409 DISCUSSION_PAUSED`。
- 同一条讨论正在生成时再次推进返回 `409 ENGINE_BUSY`；生成期间用户停止或暂停，结果直接丢弃，不写库。
- 模型失败返回 `502 MODEL_ERROR`，不写失败消息。

**自动推进**：`POST /messages` 增加可选字段 `advance`（默认 `false`）。网页端设为 `true` 时，用户发言成功后由后台任务推进一轮；相同 `client_msg_id` 的幂等重试不会重复生成。实现上只有“新建消息”才排任务。

**模型**：当前 `THINKSPACE_MODEL_PROVIDER=fake`，使用确定性假模型，不联网、不耗额度，只用于验证调度链路；接知乎直答时新增 `ModelClient` 实现并在 `build_model` 切换。界面必须标明这是本地模拟，不能当作真实 AI 回复。

## 6. 错误码

| HTTP | code | 含义 |
|---|---|---|
| 401 | `AUTH_REQUIRED` | 未登录 |
| 404 | `DISCUSSION_NOT_FOUND` | 讨论不存在，或不属于当前用户 |
| 409 | `DISCUSSION_CLOSED` | 已停止/结束，拒绝新消息 |
| 409 | `INVALID_STATE` | 非法状态流转，响应带 `current_status` |
| 422 | `UNKNOWN_ROLE` | 创建时传了未定义角色，响应带 `known_roles` |
| 422 | `INVALID_REFERENCE` | `in_reply_to` 指向的消息不存在或跨讨论 |
| 422 | — | 请求体校验失败（pydantic 默认结构） |
| 429 | `MESSAGE_QUOTA_EXCEEDED` | 单条讨论超过 500 条消息 |
| 503 | `DATABASE_BUSY` | SQLite 写锁等待超时，稍后重试 |
| 503 | `STREAM_BUSY` | 同时订阅数超过 32 |

## 7. 前端接入

```js
const base = '/api/discussions';

// 1. 创建
const discussion = await fetch(base, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ topic: 'AI 应该替我们做决定吗？' }),
}).then(r => r.json());

// 2. 发言（幂等键防重复）
await fetch(`${base}/${discussion.id}/messages`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    body: '我想先区分：替我们分析，和替我们决定。',
    client_msg_id: crypto.randomUUID(),
  }),
});

// 3. 订阅事件（浏览器断线会自动重连并带上 Last-Event-ID）
const source = new EventSource(`${base}/${discussion.id}/stream`);
for (const type of ['discussion.created', 'message.created', 'discussion.paused',
                    'discussion.resumed', 'discussion.stopped', 'discussion.finished']) {
  source.addEventListener(type, (event) => {
    const payload = JSON.parse(event.data);
    render(payload);                       // payload.message 是消息快照
  });
}
source.addEventListener('stream.end', () => source.close());

// 4. 只有 stopped / finished 两种终态需要关掉输入框
```

最小接入改造：把 `engine.mjs` 里 `this.messages.push(m)` 换成渲染服务端返回的消息，`submit()` 改成上面的 POST，其余逻辑不用动。

> **安全提醒：`body` 和 `topic` 是纯文本，后端不做 HTML 转义。** 前端必须用 `textContent` 或框架默认的文本插值渲染，**不要用 `innerHTML`**。后端虽然在校验层拒绝了空字符（`\x00`），但 `<script>`、`<img onerror=...>` 这类内容会被原样存储和返回——这是有意的（保真），转义责任在前端。Vue 的 `{{ }}` 默认转义，React 的 `{}` 默认转义，都安全；只有手动 `innerHTML` 才会出问题。

## 8. 已验证与未验证

已验证（2026-11-17 记录：`pytest api/tests`，**66 passed**，其中讨论模块 56 个；2026-11-18 新增 E 模块 15 个用例，本机全量 81 个用例中 78 通过，3 个 SSE 生命周期用例因 anyio 3.7.1 失败——代码使用 `abandon_on_cancel`，需要 anyio ≥ 4）：

- 创建：默认座位、角色子集仍保留 user、未知角色 422、`max_turns` 边界、主题空白/超长、**写锁超时返回 503 DATABASE_BUSY**
- 认证与隔离：11 个端点未登录全部 401；跨用户读/写/暂停/停止/订阅全部 404；列表互不可见
- 列表：**带在座角色**（批量查询，非 N+1）
- 消息：序号连续、顺序稳定、分页 `has_more`
- **历史翻页**：`newest_first` 用 `before_seq` 连续往回翻，`[4,5] → [2,3] → [1]` 三页走通，翻到底 `has_more=false`
- 幂等：重复提交只落一条、改内容也返回首次结果、空幂等键按未提供处理
- 特殊字符：换行、制表符、emoji、引号、反斜杠、`DROP TABLE` 注入串、XSS 串、4000 字长文
- 引用：正常引用、引用不存在的消息 422、跨讨论引用 422
- 状态机：暂停/恢复/停止/结束全部路径，重复调用幂等，终态非法流转 409，暂停期间可发言
- 事件：创建/消息/状态变化各自产生事件，**两套序号独立**，增量与分页
- 消息状态：落库时确定，只接受 `completed` / `failed` / `cancelled`；传 `streaming` 等中间态直接拒绝
- 落座校验：只有在这条讨论里落座的角色才能发言，未落座角色被拒绝
- 事件快照：直接改库里的消息内容后，历史事件里的副本保持不变
- 输入健壮：含 `\x00` 的主题与正文被拒绝（接口规范；空字符本身能存，但会让 SQL 的 `length()` / `LIKE` 计数错乱）
- SSE：历史重放、`Last-Event-ID` 续传、`after_seq` 续传、终态关闭、不存在 404、名额耗尽返回 **503 STREAM_BUSY**
- SSE 生命周期（用 monkeypatch 缩短时间常量，不靠真等）：空闲时按间隔发心跳、超过存活上限发 `stream.timeout` 并关闭、**客户端断开后归还名额**（只有 1 个名额时第二次连接仍可成功）
- 持久化：换新 app 实例（同一库文件）后数据与序号都在
- **旧库迁移**：v2 结构且表为空时自动重建；有数据时拒绝启动并提示备份
- 并发：20 线程写入序号严格 1..20；20 线程抢同一幂等键只落 1 条；**并发读写时水位不会落后于返回的消息**
- 唤醒：一次真实写入（不是手动通知）在 500ms 内唤醒订阅者，证明走的是通知而不是兜底轮询
- 存储：WAL 模式生效、`user_version` 记录表结构版本
- 资源：读操作确实关闭连接（关闭后再用会抛 `ProgrammingError`）；源码里不再出现 `with self._connect()` 的写法
- 序号边界：`after_seq` / `before_seq` / `offset` 超过 64 位范围返回 422；`Last-Event-ID` 超范围被收敛后正常收尾

> 下面这条是**手动脚本实测**，脚本未入库，不作为可复现的自动化指标：SSE 订阅端在发言后 11 ms 收到事件；24 项端点行为逐条核对通过。需要复现请按第 7 节示例自行连接。

未验证 / 已知风险：

- **与前端联调**：`packages/debate-room` 仍在跑预设脚本
- **没有速率限制**：登录用户可以无限创建讨论、无限发言（单讨论 500 条上限挡住了最坏情况）。演示够用，公网部署前应加 per-user 限流
- **SSE 建立后不重新校验会话**：连接期间 session 过期不会主动断开，靠 600 秒上限自然回收
- **多进程部署**：条件变量不跨进程，`--workers > 1` 时退化为 1 秒兜底轮询；多进程共享同一 SQLite 文件未做压力测试
- **大量并发连接**：心跳、超时、断开释放名额都有用例覆盖，但几十个真实连接同时在线时的内存与调度表现未做压测
- **消息量级**：单讨论 500 条上限内的分页性能未做基准测试

## 9. 明确没做的部分

- **流式生成**：本模块不处理生成过程。没有 `streaming` 状态、没有增量正文事件；E 模块生成完毕后一次性写入完整消息。
- **AI 消息写入的 HTTP 接口**：故意不开放。E 模块在服务端内部调用 `DiscussionStore.append_message(..., status=...)`，状态在落库时确定，避免前端伪造角色发言或篡改状态。
- **消息编辑/删除**：计划书未要求。已落库的消息不可修改，这也是事件快照有意义的前提。
- **轮次推进**：`max_turns` / `turn_index` 只存储不校验，由 E 的调度器维护。
- **讨论删除**：未提供，注意与 `stop` 的语义区别。

> 术语说明：本模块实现的是**追加式事件日志**（每次变化追加一条带序号的记录），
> 不是严格意义上的事件溯源（event sourcing）——系统状态不由重放事件重建，
> 消息表仍是读取的事实来源；也不承担 SQLite WAL 的崩溃恢复职能。答辩时请按"事件日志"描述。

## 10. 表结构版本与迁移

表结构版本写在 `PRAGMA user_version` 里（当前 `SCHEMA_VERSION = 3`）：

| 版本 | 变化 |
|---|---|
| v1 | 初版：消息序号与事件序号合并字段，事件表用全局自增主键 |
| v2 | 两套序号分离，事件序号改为每条讨论内独立计数 |
| v3 | 事件表增加 `payload` 列，消息快照在写入时固化 |

启动时的判断：

- 版本一致 → 直接启动，不做任何检查
- 版本更低（含全新库）→ 检查旧表结构。**旧表为空时自动重建，有数据时拒绝启动并提示先备份**
- 版本高于代码 → 拒绝启动并提示更新代码

不会静默删除任何已有数据。`data/thinkspace.db` 被 `.gitignore` 忽略，备份时连同 `-wal`、`-shm` 一起复制。

## 11. 已知未修的问题

以下是本轮审计发现、但**决定暂不修复**的问题，留给需要时再处理：

| 问题 | 影响 | 为什么先不修 |
|---|---|---|
| 无限流 | 登录用户可无限创建讨论/发言 | 需要先定配额策略。单讨论 500 条上限**只能限制单条讨论**，讨论数量本身没有上限，总数据量仍可无限增长 |
| SSE 不重校验会话 | 连接期间 session 过期不会断开 | 600 秒上限自然回收，收益低于改造成本 |
| 通知可能丢失（lost wakeup） | 写入恰好发生在"查完"和"开始等"之间时，订阅端最多延迟 1 秒 | 1 秒兜底轮询已覆盖，改造成本高于收益 |
| 多进程退化 | `--workers > 1` 时条件变量不跨进程，退化为轮询 | 当前部署是单 worker |

## 12. 检查中发现的跨模块问题

**`api/app/store.py`（用户/会话/泡泡存储）同样使用 `with self._connect() as conn`，连接不会被显式关闭。** 这不在 D 模块范围内，但影响整个进程：

- 每次登录、会话校验、泡泡读写都会留下一个连接，靠 GC 回收
- 在 Windows 上表现为数据库文件被占用，测试临时目录无法清理
- 本模块已改为 `_connection()` / `_write()` 显式关闭；建议 `store.py` 后续同步调整

D 自己的代码已通过 `test_no_read_path_uses_the_unclosed_pattern` 守住这个写法，不会再退化。
