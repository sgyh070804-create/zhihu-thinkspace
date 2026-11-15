# ThinkSpace 长桌讨论室 · 0.2.0

三位刘看山与用户同桌的前端讨论组件。当前版已接入用户确认的三维网格，使用原模型骨骼驱动头、身体、上臂、前臂和手；整体为冷灰蓝主题，角色气泡白底黑字，用户气泡黑底白字。

## 运行

在本目录运行 `python -m http.server 8780 --bind 127.0.0.1`，打开 http://127.0.0.1:8780/index.html 。通过 HTTP 加载，不直接双击 HTML。

Three.js、GLTFLoader、SkeletonUtils 与 GLB 均已随包提供，不依赖 CDN，不需要安装运行依赖。

## 资源

- `assets/kanshan/kanshan-runtime.glb`：2.35 MB 的减面运行版，8 个网格、11 根骨骼、41,928 顶点、83,824 三角面；三位角色共享几何和材质，各自克隆独立骨骼。
- `assets/kanshan/asset-info.json`：运行资源规格。
- 仓库 [`assets/kanshan`](../../assets/kanshan)：压缩 Blender 可编辑原件、高精度 GLB、三视图、建模和减面源码、实际渲染与模型检查器。
- 仓库 `releases/thinkspace-resources-v0.2.0.zip`：前端、完整素材、文档与验证截图组成的可下载资源包。

模型载入后才启动讨论与动画预热；资源失败会显示错误。角色动作使用阻尼弹簧连续过渡，映射到实际骨骼。12 个动作入口、暂停/速度/重新开始、三个示例话题、用户输入、角色邀请、记录及 Markdown 导出保留。角色外形按用户参考图重建，当前资源已获用户确认，并非官方生产原模。

## 接入

`scene.js` 管理场景，`kanshan-character.js` 载入/克隆模型并绑定骨骼，`engine.mjs` 管理讨论，`app.js` 管理气泡和输入。`paper-character.js` 为旧版留档，当前入口不使用它。

```js
window.debateRoom.setTopic(1);
window.debateRoom.submit('我的观点');
window.debateRoom.pause();
window.debateRoom.resume();
window.debateRoom.getTranscript();
window.debateRoom.dispose();
```

本版仍是前端预设讨论，不会理解用户输入，没有真实 AI、OAuth、后端或多人联网同步。业务接入时替换讨论数据源即可。

## 验证

`npm test` 使用 Node.js 内置测试（无需 npm install）：讨论状态、弹簧连续性、用户参与、GLB 完整性、骨骼与蒙皮权重。详情见 [VALIDATION.md](VALIDATION.md)。最新截图为 `screenshots/07-cool-overview.png`、`08-monochrome-user.png`、`09-cool-rig.png`；此前截图为历史留档。

角色 IP 和参考素材权利归原权利方；Three.js MIT 许可见 `vendor/THREE-LICENSE.txt`。
