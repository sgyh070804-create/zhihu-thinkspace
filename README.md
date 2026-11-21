# ThinkSpace

AI 阅读思考助手与个人收藏知识库：收藏问答、拓展视角、观点沉淀。知乎黑客松项目。

成员与 AI 开发助手开始协作前，请阅读 [ThinkSpace 协作约定](AGENTS.md)。

## 当前实现与验证边界

主站已提供资料区和「思考体验」入口，泡泡动画、三维讨论室可在主站内打开。当前完成本地演示与离线检查，真实知乎 OAuth 和 AI 回复仍待联调；未部署公网网站。最新修整与验证见 [网站 review 记录](docs/reviews/2026-11-18-site-review.md)。

思维泡泡已有独立页面 `/thought-bubbles`，可读取当前账号保存的泡泡，支持沉浸阅读、手记筛选、用户书写的连接草稿与实时融合。采用统一冷灰蓝主题和渐入、卡片切换、轻弹性过渡。[实际截图、运行方式与本次验证](docs/thought-bubbles/README.md)。连接草稿目前仅留在本页，可导出，尚未同步服务器。

- 知乎 OAuth Authorization Code 接入骨架：`app_key`、授权码交换和 OAuth token 都只留在服务端。
- 官方用户数据适配：公开收藏夹、收藏条目、近期收藏、用户公开创作、关注用户。
- 能力边界展示：截至 2026-11-14 查阅的官方公开用户数据文档未提供“点赞历史”和“评论历史”接口，页面明确标注，不用互动计数冒充历史。
- 灵感泡泡首版：Chrome/Edge MV3 扩展在知乎回答、专栏文章、想法和视频页提供悬浮窗，保存文章标题、作者、规范链接、选中文字和用户想法。
- 文章关联：按内容类型与内容 ID 关联泡泡，例如 `answer:20001`、`article:30001`；同一文章的不同追踪参数会归并。
- 用户隔离：网页会话和扩展 Bearer token 分开；扩展通过网页生成的一次性配对码连接，不读取知乎 Cookie。
- 讨论室角色调度首版（E 模块）：支持手动推进、用户发言后自动推进；当前使用确定性假模型，真实模型尚未接入。
- 离线演示模式：没有知乎凭证时可以验证示例资料交互；动画融合和讨论回复使用示例内容。

## 本地启动

思想分叉已有可运行的本机草稿前端：从主站「思想分叉」或 `/thought-branches` 进入，树下方显示当前问题，支持单条件分叉、判断记录、分支对照及导出。无需 API 即可体验，真实 AI 与账号同步未接入。[运行、截图与验证范围](docs/thought-branches/README.md)。

要求 Python 3.10+ 与 Node.js 20+。

```powershell
Set-Location D:\ds\zhihu-thinkspace
if (!(Test-Path .env)) { Copy-Item .env.example .env }
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r api\requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir api --reload --port 8000
```

另开一个终端启动网页：

```powershell
Set-Location D:\ds\zhihu-thinkspace
npm --prefix web ci
npm --prefix web run dev
```

打开 <http://localhost:5173>。没有真实凭证时可点击“先体验本地演示”。

## 接入真实知乎账号（待凭证与联调）

已实现授权发起、回调、授权码交换和账号归属逻辑，离线测试使用模拟提供方。凭证获取方式与回调要求以赛事及官方当前说明为准。本地测试不证明真实账号已经接通。获得凭证后在根目录 `.env` 填入：

```dotenv
ZHIHU_ACCESS_SECRET=<个人申请的 Access Secret>
ZHIHU_OAUTH_APP_ID=<赛事分配>
ZHIHU_OAUTH_APP_KEY=<赛事分配>
ZHIHU_OAUTH_REDIRECT_URI=http://localhost:8000/api/auth/zhihu/callback
```

重启后端后，再验证授权、回调、资料读取、同账号再次登录、换账号隔离和令牌过期行为。回调地址必须与官方登记值一致。当前实现处理 `authorization_code`，并使用 HttpOnly 授权事务 Cookie 校验请求关联性；`state` 回传、令牌刷新和撤销行为仍需真实联调确认。

更多进度、坑位和队友协作说明见 [docs/TEAM-HANDOFF.md](docs/TEAM-HANDOFF.md)。

## 安装浏览器扩展

1. 打开 Chrome 或 Edge 的扩展管理页，开启“开发人员模式”。
2. 选择“加载已解压的扩展程序”，目录选 `D:\ds\zhihu-thinkspace\extension`。
3. 在 ThinkSpace 网页右上角点击“连接阅读扩展”，复制 5 分钟内有效的一次性配对码。
4. 点击浏览器工具栏中的 ThinkSpace 扩展图标，粘贴配对码。
5. 打开知乎回答、专栏文章、想法或视频页，点击右下角“想法”按钮记录。

扩展只保存用户主动输入的想法、主动选中的引用，以及当前公开页面的标题、作者和规范 URL；不会抓取整页正文、读取知乎 Cookie 或调用私有接口。

## 测试与构建

```powershell
.\.venv\Scripts\python.exe -m pip install -r api\requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest api\tests -q
npm --prefix web run build
npm --prefix web test
```

测试覆盖演示数据、能力缺口、文章关联、扩展配对、OAuth 请求及账号隔离、讨论室存储与 SSE、角色调度与自动推进；网页测试覆盖异步请求失效、错误处理、思想分叉和演示资源打包。本次实际结果见 review 记录。

构建会将两个组件的运行资源复制到 `web/dist/experiences/`，无需分别启动演示服务器。可用 `npm --prefix web run preview` 检查构建产物。正式部署需发布整个 `web/dist/` 并配置同域 `/api/` 反向代理到 FastAPI，不能只上传主页。当前资源路径按域名根目录部署；子路径部署需另行适配。

## 目录

```text
api/        FastAPI 服务端与离线测试
web/        Vue 3 + TypeScript 网页
extension/  Chrome/Edge MV3 灵感泡泡扩展
tools/      知乎知识库链路验证 CLI
docs/       项目计划
```

真实数据库默认写入 `data/thinkspace.db`，该目录已被 Git 忽略。密钥、OAuth token、真实用户数据不得提交到 Git。

## 灵感泡泡动画组件（首版）

独立动画组件位于 [`packages/thought-bubbles`](packages/thought-bubbles)，包含透明薄膜材质、连续膜节点形变、拖动融合和内景阅读。主站泡泡入口现已转为正式前端页面，账号记录读取已接入；无需 OAuth 的独立 `demo.html` 继续保留。服务端融合关系和草稿同步仍待实现，详见 [页面交接](docs/thought-bubbles/README.md)。

- [运行方式、实际测试截图与验证范围](docs/bubble-animation/README.md)
- [组件接入说明与 API](packages/thought-bubbles/README.md)
- 测试：`node packages/thought-bubbles/tests/physics.cjs`


## 长桌讨论室（前端首版）

独立 2.5D 讨论原型位于 [`packages/debate-room`](packages/debate-room)：刘看山参考角色与用户同桌、12 种实时关节动作、头顶文字气泡与本地发言接替。演示内容不连接 AI 服务。

- [启动与接入说明](packages/debate-room/README.md)
- [实际测试截图与验证限制](docs/debate-room/README.md)
- 测试：`npm --prefix packages/debate-room test`

## 三维角色与冷色资源包（0.2.3）

长桌讨论室已接入刘看山三维骨骼模型，配套黑白气泡和冷灰蓝主题。

- [当前界面、截图和接入文档](docs/debate-room/README.md)
- [模型原件、参考和建模源码](assets/kanshan/README.md)
- [完整前端素材 ZIP](releases/thinkspace-resources-v0.2.3.zip)
- 自动测试：`npm --prefix packages/debate-room test`

0.2.1 修复模型动作幅度被二次缩小、手势遮挡和低帧率时计时变慢。动作试演会平滑拉近角色。9 项自动检查与实际截图见讨论室验证记录；内嵌预览采样不作为流畅度验收。

0.2.2 修正抬手时手肘向内折：左右肘采用实时外侧方向约束，保持臂长。10 项检查通过，包含能复现旧错误的动作过渡检查。

0.2.3 在正式讨论中默认自然垂手，发言手势短暂抬起后收回，暂停也会收手。取消自动悬空写字和举杯；完整动作保留在试演。11 项检查通过。

## 后端工程规划与认领

- [独立后端规划、工作量估算与任务认领](docs/backend-engineering-plan.md)：基准 26 人日（156 小时），建议预留约 33 人日；按 A–G 模块自行认领。
