# 知乎知识库 RAG 验证工具

一个基于知乎开放平台官方接口的命令行验证工具，用于检验「上传文章 → 限定知识库检索 → 基于片段生成带引用的回答」这条链路是否可靠。

## 目录结构

```
tools/zhihu-kb-test/
├── zhihu_kb_cli.py        # 命令行工具
├── README.md              # 本文件
├── articles/              # 待上传的 Markdown 文章
├── reports/               # 每次 ask 生成的验证报告
└── upload_manifest.json   # 内容 ID ↔ 来源映射（upload 自动维护）
```

## 对接的官方接口

接口字段已于 2026-11-13 通过真实调用逐项核对：

| 用途 | 方法与路径 | 关键参数 |
|---|---|---|
| 列出知识库 | `GET /api/v1/knowledge/bases` | `Scope=all/created/subscribed` |
| 上传文件 | `POST /api/v1/knowledge/files` | multipart：`KnowledgeBaseID`、`File` |
| 知识库检索 | `POST /api/v1/knowledge/search` | JSON：`Query`、`KnowledgeBaseIDs`、`Limit`（≤10） |
| 直答生成 | `POST /v1/chat/completions` | JSON：`model`、`messages`、`stream` |

鉴权统一使用请求头 `Authorization: Bearer <Access Secret>` 与 `X-Request-Timestamp`（秒级 Unix 时间戳）。

检索响应中每条 `Items` 元素包含 `KnowledgeBaseID`、`DocName`、`RecallContentID`、`Content`（片段数组）；上传响应返回 `KnowledgeBaseID`、`RecallContentID`、`FileName`、`FileSize`、`Title`。

## 启动说明

### 1. 准备环境

从仓库根目录进入工具目录再执行下方命令：

```bash
cd tools/zhihu-kb-test
```

只需 Python 3.10+，仅用标准库，无需安装依赖。

### 2. 配置凭证

Access Secret 从 <https://developer.zhihu.com/profile> 获取，**只通过环境变量传入**，不要写进代码、脚本或命令历史。

Windows PowerShell：

```powershell
$env:ZHIHU_ACCESS_SECRET = "<你的 Access Secret>"
```

Windows CMD：

```cmd
set ZHIHU_ACCESS_SECRET=<你的 Access Secret>
```

macOS / Linux：

```bash
export ZHIHU_ACCESS_SECRET='<你的 Access Secret>'
```

工具会在所有输出与报告中擦除凭证字面量；未设置该变量时直接报错退出，不会回退到任何硬编码值。

### 3. 查询知识库 ID

```bash
python zhihu_kb_cli.py bases
```

输出每个知识库的 ID、名称、内容数、归属关系与可见性。

### 4. 上传文章

```bash
python zhihu_kb_cli.py upload --kb-id <知识库ID> articles/甲-意义来自选择.md articles/乙-选择不足以构成意义.md
```

- 标题、作者、原文 URL 的读取顺序：YAML front matter（`title` / `author` / `url`）→ 正文一级标题与 `作者：`、`原文：` 行 → 文件名兜底。
- 上传结果写入 `upload_manifest.json`，记录 `RecallContentID` 与本地路径、标题、作者、原文 URL、内容 sha256 的映射，`ask` 据此把检索片段还原成可追溯来源。
- **不自动重复上传**：内容 sha256 未变化时跳过，确需重传加 `--force`。

文章 Markdown 的推荐写法：

```markdown
---
title: 甲：意义来自我们作出的选择
author: 测试作者-正方
url: https://example.com/test1-pro
---

# 甲：意义来自我们作出的选择

作者：测试作者-正方
原文：https://example.com/test1-pro

正文……
```

上传后知识库需要服务端解析入库，通常需要等待 1–3 分钟才可被检索到。

### 5. 提问验证

```bash
python zhihu_kb_cli.py ask --kb-id <知识库ID> --question "按文章甲的观点，意义主要来自什么？" --limit 10
```

常用参数：

| 参数 | 说明 |
|---|---|
| `--kb-id` | 知识库 ID，可重复传入以同时检索多个库 |
| `--limit` | 返回文档结果数，1–10，默认 5；每条结果可能含多个片段 |
| `--model` | `zhida-fast-1p5`（默认）/ `zhida-thinking-1p5` / `zhida-agent` |
| `--report` | 指定报告路径；省略则按时间与问题自动命名到 `reports/` |

退出码：`0` 正常，`1` 接口调用失败，`2` 完成但校验未全部通过。

## 行为约定

**检索范围严格限定。** `ask` 只发送 `KnowledgeBaseIDs`，绝不发送 `RecallScopes`。只要不传该参数，服务端就不会把召回扩大到 `personal` / `subscription` / `public`。返回的每条片段都会校验 `KnowledgeBaseID` 是否落在请求范围内，超范围的片段直接丢弃并计入报告告警。

**无命中即止。** 检索结果为空时直接返回「资料不足」，不调用生成模型，避免模型凭内部知识编造答案。

**引用编号可核验。** 片段以 `[1]`、`[2]` 顺序编号后作为上下文传给模型，系统提示要求每个结论标注片段编号。回答返回后校验：引用编号必须落在实际片段编号集合内；给出了结论却没有任何编号也记为不通过。

**本工具不做的事：** 网页抓取、OAuth 授权、收藏同步、向量数据库。切分、向量化与召回全部由知乎服务端完成，本地不保存任何向量索引。

## 四类测试问题模板

把 `<甲>`、`<乙>` 替换成你上传的两篇文章主题，`<KB_A>` 为目标知识库，`<KB_B>` 为另一个你能访问但不打算检索的知识库。

### 一、答案可在文章甲直接找到 —— 验证能否准确检索与回答

```bash
python zhihu_kb_cli.py ask --kb-id <KB_A> --limit 10 \
  --question "按文章甲的观点，<甲的核心论点>主要来自什么？"
```

通过标准：命中甲文片段；回答内容与片段一致；引用编号指向甲文片段。

本次实测（问题：「按文章甲的观点，意义主要来自什么？」）：命中 1 条甲文片段，回答「意义主要来自人对自身生活的自主选择，以及为这份选择承担责任的过程 [1]」，知识库 ID 校验与引用编号校验均通过。

### 二、比较两篇主张 —— 验证能否区分观点及条件

```bash
python zhihu_kb_cli.py ask --kb-id <KB_A> --limit 10 \
  --question "关于<共同议题>，甲文与乙文的主张分别是什么？两者有何不同？"
```

通过标准：同时命中甲、乙片段；回答分别陈述两方主张并说明差异，不把对立观点合并；每条结论都带编号。

本次实测（问题：「关于人生意义，甲文与乙文的主张分别是什么？两者有何不同？」）：命中 2 条片段，回答分列甲文主张 `[1]`、乙文主张 `[2]`，并从意义来源、主观意愿地位、对非自主因素的看法、判断标准四个维度列出差异，校验通过。

> 注意：`--limit` 过小时可能只召回一篇，导致误判为「资料不足」。比较类问题建议用 `--limit 10`。本次用 `--limit 5` 时只召回甲文，工具如实返回「资料不足」并说明缺少乙方内容——这是正确的保守行为，而非缺陷。

### 三、两篇都没提供依据 —— 验证能否明确说资料不足

```bash
python zhihu_kb_cli.py ask --kb-id <KB_A> --limit 10 \
  --question "<与两篇文章完全无关的事实型问题>"
```

通过标准：检索 0 条片段；输出「资料不足」；不调用生成模型；不出现任何编造内容。

本次实测（问题：「甲乙两篇文章给出的员工离职补偿金计算公式是什么？」）：命中 0 条片段，直接返回「资料不足」，未调用生成模型。

### 四、答案只在另一知识库 —— 验证是否严格限定检索范围

先确认该问题在 `<KB_B>` 中确实有答案，再只指定 `<KB_A>` 提问：

```bash
# 对照组：答案确实存在于另一知识库
python zhihu_kb_cli.py ask --kb-id <KB_B> --limit 3 --question "<只有 KB_B 能回答的问题>"

# 验证组：只限定 KB_A，应当无命中
python zhihu_kb_cli.py ask --kb-id <KB_A> --limit 10 --question "<只有 KB_B 能回答的问题>"
```

通过标准：验证组检索 0 条片段并返回「资料不足」；对照组能正常命中，证明问题本身可答、无命中并非接口故障。

本次实测（问题：「糖尿病患者的血糖控制目标是多少？」）：

- 对照组指定公共知识库 `7533055000733786828`，命中 3 条片段（《中国老年糖尿病诊疗指南(2024版)》等），所有片段 `KnowledgeBaseID` 均等于请求值。
- 验证组只指定测试知识库，命中 0 条，返回「资料不足」。

说明范围限定生效：答案可被检索到，但不在指定知识库内时工具不会越界取用。

## 报告格式

每次 `ask` 都会生成一份 Markdown 报告，包含：

- 问题、检索知识库、召回范围参数、片段数、生成模型；
- 每条检索片段的 `KnowledgeBaseID`、`RecallContentID`、作者、原文 URL 与片段原文；
- 模型回答全文；
- 两项校验结论（返回知识库 ID 是否越界、回答引用编号是否有效）；
- 来源清单与错误/告警列表。

## 已知限制

- 知乎开放平台当前未开放创建知识库的接口（`POST /api/v1/knowledge/bases` 返回 405），第四类测试需要使用已有的第二个知识库作为对照。
- 服务端对上传文档会生成摘要式片段，检索返回的是经服务端处理的内容，不是逐段原文切片。
- 知识库接口有每日调用额度，可用 `zhihu-cli quota --api-id knowledge` 查询余量。

## 本次入库说明

实测结果为用户提供的初步验证记录，本次提交未重新调用远端 API。文章与原始报告未随本次附件提供；运行时需自行准备文章。articles/、reports/ 和 upload_manifest.json 默认忽略，不提交真实资料和本地映射。

引用编号校验只检查编号存在性，不检查语义支持程度。检索返回可能是平台处理后的摘要式片段，不能自动视为逐字原文引用。当前脚本仍需补充异常分支和脱敏专项验证，README 的设计约定不等同于全面验证通过。
