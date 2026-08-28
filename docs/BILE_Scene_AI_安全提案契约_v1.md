# BILE Scene AI 安全提案契约 v1

## 定位

BILE Scene AI Proposal v1 是 **Scene Interchange v1 的受限编辑意图层**，不是 BIN writer，也不是结构重建格式。它把 AI 或人工提出的变更限制在已经由本项目实证的 v3/v4 patch 白名单内，并交给既有暂存编辑会话、预检、候选包和渲染回归链路处理。

> **任何提案都不能直接修改原始 BIN。** 它只能形成暂存变更；候选 BIN 必须通过既有导出、重新解析、预检、实验包和游戏内回归流程另行验证。

| 类别 | v1 允许 | 强制拒绝 |
|---|---|---|
| 版本 | BILE v3、v4 | BILE v2，始终只读 |
| 源绑定 | BIN SHA-256 与格式版本 | 无哈希、跨源或跨版本提案 |
| BELE | 完整仿射矩阵、ARGB、initial phase | playback mode、记录数、未知字段、偏移 |
| BMTI | 精灵元素 anchor X/Y | 非精灵元素、结构修改 |
| 容器 | 暂存会话、候选导出、证据与回归链路 | 原地写回、重建区块、改变容器布局 |

## JSON 轮廓

```json
{
  "schema": "easytech-bile-scene-proposal/v1",
  "writeback": "candidate_only",
  "source": {"bin_sha256": "<64 位 SHA-256>", "version": 4},
  "keyframes": [{
    "keyframe_index": 12,
    "transform": {"xx": 1, "xy": 0, "yx": 0, "yy": 1, "x": 8, "y": -3},
    "argb": 4294967295,
    "initial_phase": 0
  }],
  "anchors": [{"element_index": 2, "x": 14, "y": 20}]
}
```

关键帧仿射提案必须提供全部六个矩阵分量，避免 AI 基于不完整状态隐式覆盖字段。`argb` 与 `initial_phase` 为可选；未给出的字段保留当前已解析值。解析器明确拒绝 `playback_mode`、任何未知顶层字段、v2、无效索引和值域外数值。

## 应用与审计

提案通过 `AnimationDocumentSession.execute` 映射为既有 `SetKeyframeCommand` 和 `SetAnchorCommand`。因此撤销/重做、预览重新解析、候选导出、预检和差异回归全部复用既有保守链路。哈希匹配的 v4 提案可形成暂存编辑而原 BIN 字节保持不变；跨源提案必然被拒绝。

AI 系统可生成此 JSON 作为**待审阅建议**，但不应把它描述为游戏内验证或完整动画重构。游戏实机表现仍必须由候选实验包和用户的游戏内测试确认。

## 工作台可用性与审计状态

桌面工作台在“文件 → 中转与交付”以及同名 Ribbon 分组提供“导出 BILE AI 场景提案模板”和“加载 BILE AI 场景提案（暂存）”两个入口。模板由当前 `AnimationDocumentSession` 创建，包含当前源 BIN 的 SHA-256、BILE 版本、`candidate_only` 意图以及一个完整的 `xx/xy/yx/yy/x/y` 仿射样例；它不是通用补丁，也不包含写回授权。

加载入口先读取 UTF-8 JSON，执行 schema、字段白名单、版本与源哈希校验，再将通过的 keyframe/anchor 候选逐项映射为既有会话命令。每一项随即进入变更账本、实时预检、原始/暂存预览对比、候选差异和实验包链路。该过程不调用补丁写入器，不创建、替换或修改任何源 BIN。

当已在当前 BILE v3/v4 会话中接受提案后，“导出 BILE AI 场景提案证据”动作才会启用。该 JSON 证据包含已验证候选的白名单内容、源哈希和版本、当前 `EditSession` 暂存 patch，以及明确的 `binary_writeback: none` 标记。它是**候选会话快照**，而非候选 BIN；若加载提案后又进行受限人工调整，快照会如实包含这些后续暂存编辑。

变更账本同时以只读“候选来源”条目显示是否已接受哈希绑定 AI 场景候选及其源 SHA-256。重载 BILE 三件套或切换至 Spine 工作区时，该来源状态和证据入口均被清除；账本标签不会加入 patch JSON，更不会扩大既有写回白名单。

| 工作区状态 | 模板导出 | 候选加载 | 证据导出 | 原因 |
|---|---:|---:|---|
| BILE v3/v4 可保守编辑会话，尚无已接受提案 | 可用 | 可用 | 禁用 | 缺少可追溯的提案来源 |
| BILE v3/v4 可保守编辑会话，已接受提案 | 可用 | 可用 | 可用 | 受限白名单、SHA-256 与暂存会话可验证 |
| BILE v2 | 禁用 | 禁用 | 禁用 | v2 为严格只读格式 |
| Spine 静态/pose 工作区 | 禁用 | 禁用 | 禁用 | Spine 分支为严格只读，不共享 BILE 写回会话 |
| 未加载资源 | 禁用 | 禁用 | 禁用 | 缺少可验证的源身份和编辑会话 |

本轮离屏回归覆盖了 v4 候选加载后的 dirty/账本变化与源 BIN 零改动，也覆盖了 v2、Spine 禁用及 schema、未知字段、`playback_mode`、跨源哈希拒绝。完整测试基线为 **94/94 通过**。
