# ThinkSpace

AI 阅读思考助手与个人收藏知识库：收藏问答、拓展视角、观点沉淀。知乎黑客松项目。

## 当前已完成的第一闭环

- 知乎 OAuth Authorization Code 接入骨架：`app_key`、授权码交换和 OAuth token 都只留在服务端。
- 官方用户数据适配：公开收藏夹、收藏条目、近期收藏、用户公开创作、关注用户。
- 能力边界展示：截至 2026-11-14 查阅的官方公开用户数据文档未提供“点赞历史”和“评论历史”接口，页面明确标注，不用互动计数冒充历史。
- 灵感泡泡首版：Chrome/Edge MV3 扩展在知乎回答、专栏文章、想法和视频页提供悬浮窗，保存文章标题、作者、规范链接、选中文字和用户想法。
- 文章关联：按内容类型与内容 ID 关联泡泡，例如 `answer:20001`、`article:30001`；同一文章的不同追踪参数会归并。
- 用户隔离：网页会话和扩展 Bearer token 分开；扩展通过网页生成的一次性配对码连接，不读取知乎 Cookie。
- 离线演示模式：没有知乎凭证时也可以验证完整交互，不会伪造真实知乎数据。

## 本地启动

要求 Python 3.10+ 与 Node.js 20+。

```powershell
Set-Location D:\ds\zhihu-thinkspace
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r api\requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir api --reload --port 8000
```

另开一个终端启动网页：

```powershell
Set-Location D:\ds\zhihu-thinkspace
npm --prefix web install
npm --prefix web run dev
```

打开 <http://localhost:5173>。没有真实凭证时可点击“先体验本地演示”。

## 接入真实知乎账号（等 12 月 5 日赛事分配 key）

知乎登录链路已开发完成并验证。按赛事手册流程，OAuth App ID / App Key 在 **2026-12-05 10:00 作品提交入口开启后**，随赛事页面「创建项目」分配。拿到后在根目录 `.env` 填入：

```dotenv
ZHIHU_ACCESS_SECRET=你在 https://developer.zhihu.com/profile 申请的 Access Secret
ZHIHU_OAUTH_APP_ID=<赛事分配>
ZHIHU_OAUTH_APP_KEY=<赛事分配>
ZHIHU_OAUTH_REDIRECT_URI=http://localhost:8000/api/auth/zhihu/callback
```

重启后端即完成接入，网页「使用知乎账号登录」真实生效。`ZHIHU_OAUTH_REDIRECT_URI` 必须与赛事页面登记的回调地址一致。OAuth 回调实测使用 `authorization_code`，当前公开资料没有闭合 `state` 回传、刷新令牌和撤销接口，所以首版用 HttpOnly 授权事务 Cookie 校验请求关联性，并把生产上线前确认项保留在文档中。

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
```

当前 7 个服务端测试覆盖：演示数据、能力缺口、URL 规范化、文章—泡泡关联、用户隔离、扩展配对、OAuth 发起和知乎请求双凭证。

## 目录

```text
api/        FastAPI 服务端与离线测试
web/        Vue 3 + TypeScript 网页
extension/  Chrome/Edge MV3 灵感泡泡扩展
tools/      知乎知识库链路验证 CLI
docs/       项目计划
```

真实数据库默认写入 `data/thinkspace.db`，该目录已被 Git 忽略。密钥、OAuth token、真实用户数据不得提交到 Git。
