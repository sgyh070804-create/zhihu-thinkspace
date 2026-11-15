# ThinkSpace 长桌讨论室 · 前端首版

三位刘看山参考角色与用户围坐一张长桌的 2.5D 讨论原型。正交投影、实时关节动画、头顶逐字气泡和发言接替均由前端驱动。刘看山使用分层平面插画（头、身体、手臂均为无厚度贴片），置于立体桌椅场景中；按镜头方向调整朝向，保留遮挡和空间位置。角色为参考素材制作的近似插画。

## 启动

在本目录执行：

```powershell
python -m http.server 8780 --bind 127.0.0.1
```

打开 http://127.0.0.1:8780/index.html 。请通过 HTTP 打开，不能直接双击 HTML。Three.js 0.180.0 已随包附带，不需要安装前端依赖或访问 CDN。

## 交互

- 三个示例话题，探索、质疑、归纳三种角色轮流发言；点击角色可邀请发言。
- 用户输入后立即入席发言，气泡随文字出现，再交回示例讨论。
- 暂停、速度切换、重新开始；讨论记录可导出 Markdown。
- 动作试演提供 12 个动作：倾听、解释、追问、展开双手、指向、思考、点头、摇头、挥手、记录、举杯、赞同。可切换四位角色。
- 动作使用连续关节目标与阻尼弹簧，不播放参考 GIF。呼吸、眨眼、口型、看向发言者与倾听反应叠加运行。

## 文件与接入

`paper-character.js` 是平面刘看山的图形和关节，`scene.js` 是场景渲染与用户角色关节，`engine.mjs` 是本地讨论状态，`app.js` 是 DOM 交互，`style.css` 是界面。页面宿主可调用：

```js
window.debateRoom.setTopic(1);
window.debateRoom.submit('我的观点');
window.debateRoom.pause();
window.debateRoom.resume();
window.debateRoom.getTranscript();
window.debateRoom.dispose();
```

目前没有 OAuth、后端、模型请求、真实多用户同步。角色回复为预设内容，不会理解用户输入。后续业务接入应替换讨论数据源；不要把演示回复当成 AI 输出。

测试：`npm test`（Node.js 20+，无需 npm install）。实际验证及性能限制见 [VALIDATION.md](VALIDATION.md)。

## 素材

刘看山外形参考用户提供的 `kanshan_material.zip`；仅头像使用其中一张参考照片，三维场景为程序生成。IP 和参考照片权利归原权利方，不因本仓库代码发布而变更。Three.js 的 MIT 许可见 `vendor/THREE-LICENSE.txt`。

## 平面角色修订（0.1.1）

三位刘看山已替换为平面插画分层关节动画。桌椅与用户仍为立体，刘看山不使用球体、胶囊或其他有体积的模型。头部转向通过平面内转动与轻微形变表达，手臂在同一平面内连续摆动。
