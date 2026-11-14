# 队友交接说明（2026-11-14）

写给队友：本文说明 ThinkSpace 当前进度、每个部分怎么跑起来、以及 12 月 5 日拿到 OAuth 凭证后要做的唯一一件事。详细设计边界见 [PROJECT.md](PROJECT.md)，启动命令见根目录 [README.md](../README.md)。

## 一句话现状

OAuth 登录、用户界面、公开数据接入、浏览器扩展灵感泡泡**全部开发完成并通过测试**；唯一缺口是真实 OAuth 凭证——按主办方流程，App ID / App Key 要等 12 月 5 日 10:00 作品提交入口开启、在赛事页面「创建项目」后才会分配。我们把架子搭到了"拿到 key 填进去就能用"的程度。

## 已完成清单

| 功能 | 状态 | 验证方式 |
|---|---|---|
| OAuth 授权发起 / 回调 / 授权码交换 | ✅ 代码完成 | 跳转地址已实测正确（`302 → openapi.zhihu.com/authorize?app_id=...`）；真实授权待 key |
| 授权用户基础信息（昵称/头像/简介/uid） | ✅ 代码完成 | 官方接口 `GET openapi.zhihu.com/user`；uid 按官方要求以字符串无损保存 |
| 右上角头像 → 用户界面 | ✅ 完成 | 点击进入 profile 视图 |
| 关注列表 + 创作列表分页（加载更多） | ✅ 完成 | 按官方协议用服务端 `NextOffset` 原样回传；演示数据实测 5+3 分页正确 |
| 公开收藏夹 / 收藏条目 / 近期收藏 | ✅ 完成 | 演示模式可用；真实数据待 key |
| 点赞 / 评论历史 | ⛔ 官方未开放 | 公开文档无此接口，页面明确标注，不用累计数冒充 |
| 浏览器扩展灵感泡泡 | ✅ 完成 | 加载已解压扩展即可在知乎文章页记录想法、选中文字，按内容 ID 关联文章 |
| 服务端离线测试 | ✅ 10 项全过 | `pytest api/tests` |

## 目录结构

```text
api/        FastAPI 服务端（app/ 代码，tests/ 离线测试）
web/        Vue 3 + TypeScript 网页
extension/  Chrome/Edge MV3 灵感泡泡扩展
tools/      此前已验证的知识库 RAG 命令行工具
docs/       PROJECT.md（项目计划）、本文
.env        本地配置（已被 Git 忽略，绝不提交）
```

## 本地启动（3 分钟）

```powershell
Set-Location D:\ds\zhihu-thinkspace
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r api\requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir api --reload --port 8000

# 另开一个终端
npm --prefix web install
npm --prefix web run dev
```

打开 http://localhost:5173 → 点「先体验本地演示」→ 点右上角「演示用户」看用户界面和加载更多分页。

注意：网页从 `.env` 读 Access Secret。**每个人用自己在 https://developer.zhihu.com/profile 申请的 Access Secret**，只填在自己机器的 `.env` 里（复制 `.env.example` 起步），不要发到群里、不要提交到 Git。

## 12 月 5 日拿到 key 后（预计 5 分钟接入）

1. 10:00 后在赛事页面完成「创建项目」，拿到分配的 **App ID** 和 **App Key**
2. 打开 `D:\ds\zhihu-thinkspace\.env`，填入：
   ```dotenv
   ZHIHU_OAUTH_APP_ID=<赛事分配的 App ID>
   ZHIHU_OAUTH_APP_KEY=<赛事分配的 App Key>
   ```
3. 重启后端（Ctrl+C 后重新运行 uvicorn 命令）
4. 网页点「使用知乎账号登录」→ 知乎授权页 → 回调 → 右上角出现真实昵称头像
5. **登记回调地址**：如赛事页面要求填回调地址，填 `http://localhost:8000/api/auth/zhihu/callback`，必须与 `.env` 里的 `ZHIHU_OAUTH_REDIRECT_URI` 完全一致

## 已知的官方限制（不要踩坑）

- **点赞/评论历史**：公开用户数据文档没有这两个接口。页面上的"点赞""评论"标签是有意设计成"未接入"提示的，不要用内容上的累计点赞数冒充历史，也不要调知乎私有网页 API。
- **收藏只有摘要**：官方收藏接口返回 Summary 摘要，不是全文，不要当全文展示。
- **OAuth token 约 1 小时过期**：官方未提供刷新令牌机制，过期需重新授权（页面会提示）。
- **回调 state**：官方实测可能不回传 state，我们已用短期 HttpOnly 授权事务 Cookie 做请求关联校验，这部分代码已写好。
- **知识库**：创建知识库接口曾返回 405，使用已有知识库即可（tools/zhihu-kb-test 已验证过全链路）。

## 代码里几个值得看的位置

- `api/app/auth.py` — OAuth 发起、回调、会话建立
- `api/app/providers/zhihu.py` — 官方接口适配（双凭证、脱敏、用户信息）
- `api/app/zhihu_data.py` — 收藏/创作/关注数据端点与能力边界标注
- `web/src/components/UserProfile.vue` — 用户界面与分页逻辑
- `extension/content.js` — 知乎文章页悬浮泡泡
