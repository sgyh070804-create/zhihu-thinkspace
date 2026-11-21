# ThinkSpace 泡泡动画包 v0.1.0

独立动画组件，不依赖 OAuth、模型接口、Vue 或 React。双击 `demo.html` 即可体验，也可用静态服务器打开。无运行时依赖、无外部纹理、无网络请求。

## 首版：连续膜节点与更低接触阈值

接触改为变形表面间隙判定，1–3px 容差；拖动后松手即可。形变由 64 个边界节点以不大于 1/240 秒的子步连续求解，通过 16 位纹理和三次插值显示；无预制形变帧。具体方程、实验来源和交互映射见 PHYSICS-NOTES.md。

悬停不会冻结物理，也不会覆盖为白色。点击泡泡通过阻尼镜头推进，四周环境与其他泡泡淡出，在原有透明曲面内展示完整文字；没有白色弹窗。泡泡继续参与物理运动，镜头实时追踪它；膜纹继续流动。

文字独立按屏幕分辨率排版，避免随镜头缩放而被低分辨率放大。长文字可以在泡泡内部滚动。按 Esc、点击背景或返回按钮退出，镜头柔和退回。

`focus(id)` 进入指定泡泡；`closeFocus()` 退出。`onSelect` 仍可通知宿主，但宿主不应再弹出白色详情窗。`getStats()` 增加 focusedId。

## 材质

WebGL 实时计算曲面法线、Fresnel 掠射反射，以及随薄膜厚度与观察角度变化的 RGB 干涉色。环境反射来自程序化柔光箱、窗框和明暗环境，不是拍摄的 HDR 贴图。碰撞形变会改变反光。

薄膜厚度使用持续推进的域扭曲流场。透明中心、较强边缘反射、白色窗口高光分开计算，文字在独立 DOM 层保持清晰。

## 挤压与融合

普通接触由弹簧力、相对法向速度阻尼和局部接触压缩驱动形变：每颗 64 个边界膜节点直接积分，受力侧凹入、自由侧鼓起，分离后连续回弹。

有意融合依次经历靠近、接触挤压、液桥扩张、合并和衰减回弹。液桥使用三维隐式曲面 ray marching，法线由曲面梯度得到，反光可连续跨过颈部。表面持续存在，不以父泡泡淡出来代替融合。

最终半径按 `cbrt(r1³+r2³)` 计算，并受容器尺寸限制。中间形态由逐帧弹簧压力、接触时间与液桥松弛共同驱动；不再按固定时间曲线移动两颗父泡泡。距离场负责实时显示该状态下的曲面。

**边界：这是实时薄膜光学、软体和隐式曲面近似，不是完整流体仿真，也未求解真实肥皂膜的排液、破裂及表面张力方程。**

## 观察方式

- 拖动抵住另一颗泡泡可观察挤压；接触后松手融合，无停留门槛。
- “观看挤压与融合”：由逐帧弹簧求解推进，收敛后结束，之后轻微回弹。
- “慢镜观察”：四分之一速度，再次点击恢复。
- “定格液桥”：停在融合 50% 处；滑条可以检查各阶段，点击“慢镜观察”继续播放。
- 融合未结束时不能替换数据；可刷新演示重置。
- “撤销融合”恢复最近一次融合前的本地画布，并非服务端回滚。

## 接入

```html
<link rel="stylesheet" href="dist/thought-bubbles.css">
<div id="thoughts" style="height:680px"></div>
<script src="dist/bubble-physics.js"></script>
<script src="dist/thought-bubbles.js"></script>
<script>
const bubbles = ThoughtBubbles.create('#thoughts', {
  items: [
    { id: 'a', text: '阅读不是收集，而是建立连接' },
    { id: 'b', text: '把问题留下来' }
  ],
  onSelect(item) { /* 打开宿主详情 */ },
  async onMerge(a, b) {
    const res = await fetch('/api/thoughts/merge', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ parentIds: [a.id, b.id] })
    });
    if (!res.ok) throw new Error('生成失败');
    const data = await res.json();
    return { id: data.id, text: data.text, source: '融合观点' };
  },
  onChange(items) { /* 可保存布局 */ },
  onError(error) { console.error(error); }
});
// 页面卸载时调用 bubbles.destroy()。
</script>
```

Vue 在 onMounted 创建、onBeforeUnmount 销毁；React 在 effect 创建、cleanup 销毁。不要让框架逐帧重绘。类型声明见 dist/thought-bubbles.d.ts。

Thought 必填 id/text，可选 source/radius/x/y/generated/parents。ID 唯一，x/y 为容器宽高比例，radius 为 CSS 像素半径。服务端应保留父想法及衍生关系。可见父泡泡收起不代表删除源记录。onMerge 缺失或失败时保留原想法；演示是固定文案，未调用模型。

| API | 行为 |
| --- | --- |
| `create(host, options)` | 容器需明确高度 |
| `getItems()` / `setItems(items)` | 获取副本 / 替换数据，融合期间拒绝替换 |
| `merge(idA,idB)` | 返回 Promise，调用生成回调并播放融合 |
| `undo()` | 撤销最近一次本地融合 |
| `pause()` / `resume()` | 停止 / 恢复漂浮，膜纹继续流动 |
| `setMotionRate(rate)` | 0..2 控制膜纹与融合速度，0 定格 |
| `seekMerge(progress)` | 融合期间检查 0..0.99 的阶段 |
| `getStats()` | 后端、数量、rAF 频率、融合进度和 busy |
| `destroy()` | 清理资源 |

选项：items/onSelect/onMerge/onChange/onError；maxDpr 默认 1.35，speed 默认 1，motionRate 默认 1。

宿主自定义阅读界面时可设 `externalReader: true`，通过 `onFocusChange(item|null)` 同步阅读状态；`focus(id)`、`closeFocus()` 和点击背景均会通知。镜头和薄膜仍由组件实时驱动，组件内文字随镜头淡出，隐藏按钮退出 Tab 顺序。`animateEntrance: true` 可为数据进入加入透明度与尺度过渡。两项默认关闭，保持旧演示兼容。主站接入见 [思维泡泡页面](../../docs/thought-bubbles/README.md)。

## 性能

单 WebGL 画布；变换参数由 CPU 预计算；普通泡泡解析计算曲面，仅融合区域多步 ray marching。最多 24 个可见泡泡，建议 5–12 个；低性能设备可将 maxDpr 设为 1，数据更多时由宿主筛选或分页。

减少动态模式停止自主漂浮和膜纹时间推进，并跳过融合动画。WebGL 不可用时降级 CSS，无法保留本版曲面反光、流动膜纹和液桥。极窄区域放太多泡泡可能拥挤。

rAF/s 是浏览器回调频率，不是 GPU 基准或显示帧率保证。尚未完成真实手机、跨显卡性能验收。目标设备需要实测。


