# BILE Scene Interchange v1：只读场景契约

**状态：** 已实现并纳入跨游戏回归。  
**Schema：** `easytech-bile-scene/v1`。  
**实现入口：** `bile_workbench.bile_scene_interchange`。  
**工作台入口：** “文件”Ribbon 的“导出 BILE 场景 JSON + 渲染见证（只读）”。

## 1. 目的与安全边界

BILE Scene Interchange v1 将一组 `BIN + XML + WebP/PNG` 三件套投影为一个面向审阅、版本控制、AI 提案和未来编辑器适配器的 JSON 场景。它保留经过项目验证的元素、关键帧、通道、帧、轨道、图集区域、颜色、锚点和递归时间线关系，而不让 AI 或外部工具直接面对 BILE 的块偏移和不透明字段。

> Scene Interchange **不是** BILE writer，也不是 patch。它的 `read_only` 必须为 `true`，`writeback` 必须为 `forbidden`。任何加载或生成该 JSON 的工具都不得把它解释为可以直接写回 BIN 的授权。

这条边界解决了两个不同需求之间的冲突。专业动画编辑和 AI 需要一个可解释的场景层；游戏资源写回则要求对格式版本、记录数量、未知字段和游戏内行为采取极其保守的策略。v1 只解决前者，完全不扩大后者的权限。

| 路径 | 是否可修改 BIN | 记录数/块结构 | 适用目标 |
|---|---:|---|---|
| Scene Interchange v1 | 否 | 不产生 BIN | 审阅、AI 提案、场景适配、渲染对照。 |
| 既有保守 patch | 仅 v3/v4 白名单 | 严格不变 | 已验证的 BELE 仿射/ARGB/initial phase 与 BMTI 锚点修改。 |
| 未来 `experimental_rebuild_v4` | 尚未实现 | 可以重建，但必须隔离 | 从零动画、曲线 bake、新图集；需要独立解析、像素证据和游戏内回归。 |
| BILE v2 | 否 | 不适用 | 只读解析、预览、场景导出与证据。 |
| 欧7/征2 Spine | 否 | 不适用 | 独立的 Spine pose/AI Motion DSL 只读支线。 |

## 2. 根对象与可追溯性

根对象包含固定字段 `schema`、`kind`、`read_only` 和 `writeback`。`source` 同时记录 BIN、XML 和图集图像的文件名与 SHA-256；BIN 还记录实际解析到的 BILE 版本和 FPS。因而一个场景文件只能被视作与这一套具体源资源关联的审阅证据，不能静默套用到同名但不同内容的资源上。

```json
{
  "schema": "easytech-bile-scene/v1",
  "kind": "read_only_scene",
  "read_only": true,
  "writeback": "forbidden",
  "source": {
    "bin": {"name": "unit.bin", "sha256": "…", "version": 4, "fps": 24.0},
    "atlas": {
      "xml_name": "unit.xml",
      "xml_sha256": "…",
      "image_name": "unit.webp",
      "image_sha256": "…"
    }
  }
}
```

源哈希并非 patch 写回许可。它的用途是阻止场景提案、预览快照和渲染见证脱离原始三件套而失去可追溯性。

## 3. 场景数据模型

`nodes` 是 BMTI 元素的显式投影。每个节点都保留 `element_index`、名称、类型和锚点；纹理元素为 `sprite` 并包含图集区域与 `refx/refy`，动画元素为 `animation` 并包含其根级 `frame_count` 和 `channel_count`。未解释的 BMTI 字段、BRTS 原始偏移和区块地址不会进入 v1。

`keyframes` 是经过验证的 BELE 可解释子集。矩阵采用项目渲染器的确定义：

> `point(x, y) = (xx*x + yx*y + x, xy*x + yy*y + y)`。

每一条 keyframe 同时暴露 ARGB/RGBA、`initial_phase` 和 `playback_mode`。后两者被放进 `nested_playback`，并有 `mode_status` 显示该版本是否进入经验证的 v3/v4 reference timing 范围。v2 中对应数据只能以只读近似形式出现，不能反向写入。

`timelines` 将 BMTI → BYAL → BMRF → BXDI 的累计引用关系投影成有序层级：动画根 → 通道 → 槽位帧 → `draws`。每个 draw 只引用 `target_element_id` 和 `keyframe_id`，而不携带原始 BXDI/BMRF 地址。这让外部工具可以理解“何时引用什么元素、使用哪一条可解释 keyframe”，却不能伪造一个看似合法的二进制块修改。

| 字段组 | 保留内容 | 明确排除内容 |
|---|---|---|
| `nodes` | 元素 ID、名称、类型、锚点、已解析图集区域。 | BRTS 偏移、未解释 BMTI dword。 |
| `keyframes` | 2D 仿射、ARGB/RGBA、已读初相位/模式状态。 | 任何 opaque ref/flag 与物理 BELE 地址。 |
| `timelines` | 通道、槽位、轨道顺序、目标元素/关键帧引用。 | BXDI/BMRF 物理地址、区块游标。 |
| `diagnostics` | 解析出的图循环与可解释结构统计。 | 任何重写二进制所需的隐式布局信息。 |

## 4. 递归时间线与绘制顺序语义

场景投影记录了通道保持语义：每个通道在当前局部槽位选择最后一个 `slot <= local_slot` 的帧。嵌套动画在 `reference_v4` 模式下使用父帧切换槽位、`initial_phase` 与 `playback_mode` 计算子槽位。颜色沿递归引用按 RGBA 通道相乘。

该 JSON 同时明确标注一个容易误用的限制：timeline 中的 draw 顺序是源轨道输入顺序，不应未经预览对照就被宣称为最终像素合成顺序。最终合成仍由版本化 BILE renderer 的通道迭代、嵌套 timing 与图集裁切规则决定。因此，任何场景适配器都必须与 render witness 比较，而不是仅凭节点列表认为画面等价。

## 5. 渲染见证

调用 `export_scene_interchange(..., include_render_witnesses=True)` 或使用工作台入口时，JSON 会包含 `render_witnesses`。每个见证帧是由当前经验证的 `reference_v4` BILE renderer 对原始三件套渲染后得到的 RGBA bytes SHA-256；它不是截图替代物，而是可机器核验的画面基线。

为避免一个查看器导出动作退化为无边界批处理，见证采用显式预算。每份文档最多选择 **8** 个确定性分层代表动画，每个代表动画最多选择 **8** 个时间线切换槽位；画布固定为 256×192。若候选动画或时间线切换点不超过预算，则完整覆盖；超过预算时 `animation_coverage.sampling` 或动画条目的 `sampling` 必须显式标记为 `deterministic_stratified_*`，并保留候选总数。

> 见证哈希的“覆盖”含义必须按 JSON 中的 `candidate_*_count`、`selected_*_count` 与 `sampling` 读取。抽样见证是可重现的回归信号，**不是**“已全帧、全动画像素验证”的替代说法。

## 6. AI 与外部编辑器工作流

AI 或外部编辑器应把 v1 当作输入观察层，并输出另一份经过版本、源哈希和操作记录约束的提案文档。提案的首阶段只可作用于内存预览；其输出需与源 Scene Interchange 的 SHA-256 绑定，并在被接受前比较渲染见证。现有 BILE patch 与 Spine Motion DSL 的“来源绑定、可撤销、导出证据”的策略可作为这一层的安全模型参考，但 schema 不得混用。

未来的实验性 BILE v4 重建器若出现，必须使用新的 schema，例如 `easytech-bile-rebuild/v1`，且最低限度包括：输入三件套 hash、元素/轨道映射报告、独立解析器重读、关键槽位或全槽位渲染差异报告、未知字段处置清单、输出 hash 和待填写的游戏内回归清单。它不能把 v1 场景 JSON 直接作为“导出 BIN”按钮的输入。

## 7. 回归状态

Scene Interchange v1 已有以下自动化验证：源码内置 v4 三件套的源哈希、节点/轨道全量投影、禁止字段、图集角色和零修改断言；可用跨游戏数据集上的将军的荣耀 1 v2、世界征服者 3 v3、将军的荣耀 3 v4 的只读导出与预算化渲染见证断言；以及离屏 PySide6 主窗口中的 Ribbon 动作禁用/启用规则。

该状态表明 v1 已是一个可用的**只读专业中转层**。它并不说明 BILE 的任意结构都可安全重建，更不代表游戏内回归已经完成。
