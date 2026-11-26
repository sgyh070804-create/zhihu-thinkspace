# 思想树

从「思考空间」进入思想树，或在资料库、思维泡泡中用一条已有思绪开启。已有思绪的全文会成为根节点，同账号再次从该思绪进入时打开同一棵树。

## 使用方式

- 点选任意节点阅读、补充想法、手动添加子节点，或请求 AI 生成候选。画布支持拖动、缩放、折叠和自动布局。小屏也可通过路径和子节点按钮导航。
- 一次请求返回零至三个候选。虚线代表候选，编辑后确认才成为正式节点。已确认节点使用实线。确认后的修改由服务端保存。
- 删除前会确认。当前页面可撤销最近 20 次编辑。另存到资料库的思绪可独立在资料库和思维泡泡中打开，树上的删除不会删除该副本。
- 「控制变量实验」保留旧界面。打开同一浏览器、同一站点下的 /thought-branches?mode=experiment 可读取和导出原 v1 草稿。损坏的原始数据也可导出，原存储不会被覆盖。旧草稿与账号思想树分别保存。

## 接入知乎直答

在后端设置 ZHIHU_ACCESS_SECRET。默认使用 zhida-fast-1p5，THINKSPACE_ZHIDA_MODEL 可切换为 zhida-thinking-1p5。服务端复用知乎 HTTP 客户端和 Access Secret 鉴权，提交 model、messages、stream=false，从 choices[0].message.content 解析候选。

主动点击生成时发送根节点、当前节点、最近 12 个祖先的摘要、当前节点的已有子节点和用户粘贴的参考资料。每棵树最多 96 个节点，正文 4000 字、补充 2000 字，单次参考资料最多 2000 字。提示词维护在 api/app/branch_prompt.py，模型正文中的 JSON 需经 Schema、长度和去重校验。

| 环境变量 | 默认 | 用途 |
| --- | --- | --- |
| THINKSPACE_BRANCH_AI_DAILY_BUDGET | 30 | 同数据库的北京时间日总尝试上限 |
| THINKSPACE_BRANCH_AI_USER_BUDGET | 10 | 每账号日尝试上限 |
| THINKSPACE_BRANCH_AI_MIN_INTERVAL | 5 | 同账号两次未命中缓存的最小间隔秒数 |
| THINKSPACE_BRANCH_AI_CONCURRENCY | 2 | 全局在途上限，同一账号至多一个 |
| THINKSPACE_BRANCH_AI_QUOTA_RESERVE | 1 | 保留的免费额度，另预留其他在途请求的空间 |
| THINKSPACE_BRANCH_AI_ALLOW_DEMO | false | 显式允许演示账号调用直答 |

缓存按节点、模型、提示词和实际发送的上下文命中，持续 24 小时。未命中缓存才占用尝试预算，失败也计入预算。每次生成前查询 zhida_openai 的剩余免费额度，额度不可确认或触及保护线时停止。失败后可手动创建节点，系统无自动重试。多实例使用同一 SQLite 文件时共用预算。使用独立数据库或与其他系统共用 Access Secret 时，请留意外部额度消耗。

官方文档：[直答 HTTP API](https://developer.zhihu.com/docs?key=zhida) · [额度查询](https://developer.zhihu.com/docs?key=quota)。

## 数据与接口

新增 SQLite 表由后端初始化，老数据无需迁移。所有树按当前账号隔离，旧版本提交返回 409，用户可重新载入并继续。

| 接口 | 请求与结果 |
| --- | --- |
| GET /api/thought-trees | 当前账号的思想树列表 |
| POST /api/thought-trees | request_id 加 content 或 source_id，返回树 |
| GET /api/thought-trees/{id} | 返回树、节点、版本及已保存思绪链接 |
| POST /api/thought-trees/{id} | version 和 nodes，返回更新后的树 |
| POST /api/thought-trees/{id}/nodes/{node_id}/candidates | version、可选 references，返回 branches 和 cached |
| POST /api/thought-trees/{id}/nodes/{node_id}/thought | version，返回存入资料库的思绪 |

## 验证

- 后端 113 项和网页 27 项测试通过，生产构建通过。直答接口测试使用 httpx.MockTransport，覆盖请求协议、上下文隔离、缓存、预算、异常及账号恢复。
- Edge 实际验收了从资料库和泡泡建立思想树、历史节点分叉、候选编辑和拒绝、删除撤销、刷新恢复、旧草稿以及 390px 窄屏操作。
- 本轮未检测到已配置的知乎 Access Secret，真实直答生成调用为 0。开启小额联调时可先将日总量与单人预算限制为 1。
