# ThinkSpace

面向知乎阅读的思考工作台。把收藏与阅读手记收进资料库，再用泡泡、思想树和讨论室继续探索。项目使用 Vue 3、TypeScript、FastAPI 和 SQLite。

## 网页字体

网站和浏览器内嵌演示通过 ZeoSeven Fonts 加载分段网页字体。导航和操作界面使用[思源黑体](https://fonts.zeoseven.com/items/69/)，观点、发言和阅读正文使用[霞鹜新致宋](https://fonts.zeoseven.com/items/22/)。字体服务不可用时使用设备上的同类字体。

## 本地启动

需要 Python 3.10+ 和 Node.js 20+。在仓库根目录用 PowerShell 启动后端。

```powershell
if (!(Test-Path .env)) { Copy-Item .env.example .env }
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r api\requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir api --reload --port 8000
```

在另一个终端从仓库根目录启动网页。

```powershell
npm.cmd --prefix web ci
npm.cmd --prefix web run dev
```

打开 [本地网页](http://localhost:5173)，在资料库或个人中心选择「先体验本地演示」。可先体验示例收藏、手动融合和思想树，无需配置外部凭证。[后端状态](http://localhost:8000/api/health)

## 功能入口

| 入口 | 可以做什么 |
| --- | --- |
| 资料库 `/library` | 查看收藏夹、近期收藏和阅读手记。收藏问答基于收藏摘要，并保存提问、答复和引用。可整理思绪版本、回看来源。[收藏问答](docs/qa-api.md) |
| 思维泡泡 `/thought-bubbles` | 阅读、拖动或融合思绪。配置 DeepSeek 后可生成融合草稿，也可自己填写。确认后保存新思绪和两条父思绪。[泡泡使用说明](docs/thought-bubbles/README.md) |
| 思想树 `/thought-branches` | 从任意思绪建立根节点，手动分支或从知乎直答的候选中选择。思想树按账号保存，节点可另存到资料库。[思想树与旧草稿](docs/thought-branches/README.md) |
| 长桌讨论室 `/space/debate` | 与刘看山角色进行三维讨论演示。内嵌演示使用预设回复，讨论室后端另有存储和角色调度接口。[讨论室演示](docs/debate-room/README.md) · [API](docs/discussions-api.md) |

从「资料库 → 思绪」打开一条记录，可以带着同一思绪及其来源进入三种思考工具。旧版思想分叉可从思想树页面的「控制变量实验」打开，也可访问 `/thought-branches?mode=experiment`。

## 服务配置

按需要在后端配置对应功能，修改后重启 FastAPI。[环境变量示例](.env.example)

| 功能 | 配置 |
| --- | --- |
| 本地演示 | `THINKSPACE_ENABLE_DEMO=true` |
| 知乎账号与资料 | `ZHIHU_ACCESS_SECRET`、`ZHIHU_OAUTH_APP_ID`、`ZHIHU_OAUTH_APP_KEY`、`ZHIHU_OAUTH_REDIRECT_URI`。回调地址须与应用登记值一致。 |
| 思想树候选 | `ZHIHU_ACCESS_SECRET`。默认快速档 `zhida-fast-1p5`，可通过 `THINKSPACE_ZHIDA_MODEL` 切换至深度思考档。额度与预算参数见[思想树文档](docs/thought-branches/README.md)。 |
| 泡泡融合草稿 | `DEEPSEEK_API_KEY`，由后端调用 DeepSeek Flash。 |

思想树已通过模拟 HTTP 响应验证，真实知乎直答与 OAuth 待联调。服务端保存凭证，SQLite 默认使用 `data/thinkspace.db`。密钥、令牌和真实用户数据库均应留在本地或部署环境。

## 阅读扩展

1. 打开 Chrome 或 Edge 的扩展管理页，开启开发人员模式，加载仓库中的 [`extension/`](extension)。
2. 在 ThinkSpace「个人中心」点击「连接阅读扩展」，将五分钟内有效的配对码填入扩展。
3. 打开受支持的知乎页面，通过「想法」按钮记录。扩展也会按当前页面召回最多三条相关旧泡泡。

扩展保存主动输入的想法、主动选中的引用和页面来源信息，使用配对凭证与 ThinkSpace 通信。

## 测试与部署

```powershell
.\.venv\Scripts\python.exe -m pip install -r api\requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest api\tests -q
npm.cmd --prefix web test
npm.cmd --prefix web run build
```

部署整个 `web/dist/`。同域 `/api/` 反向代理至 FastAPI，应用页面路由回退到 `index.html`。内嵌演示目录按各自的 `index.html` 提供，例如 `/experiences/debate/`。构建产物按域名根路径部署。

## 开发资料

| 位置 | 内容 |
| --- | --- |
| [`web/`](web) · [`api/`](api) | 网页、后端及测试 |
| [`extension/`](extension) · [`packages/`](packages) | 阅读扩展、泡泡动画和讨论室组件 |
| [`assets/`](assets) · [`releases/`](releases) | 模型源文件和素材包，[下载 v0.2.3](releases/thinkspace-resources-v0.2.3.zip) |
| [协作约定](AGENTS.md) · [队友交接](docs/TEAM-HANDOFF.md) · [工程规划与认领](docs/backend-engineering-plan.md) | 开发流程、交接、任务拆分 |
