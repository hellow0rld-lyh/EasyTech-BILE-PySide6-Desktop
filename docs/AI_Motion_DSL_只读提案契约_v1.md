# AI Motion DSL v1：Spine pose 只读提案契约

**状态：已实现并回归验证的审阅中转格式。** 本契约服务于欧7 Spine 3.8 与征2 Spine 4.1 工作区的**内存 pose 提案**。它不是 Spine runtime 格式、不是 BIN 补丁格式，也不会使工作台获得任何 Spine 写回能力。

> **核心约束：** 一个提案必须同时绑定源 BIN 的 SHA-256、已验证的引擎分支与当前动画根。工作台只在这三项完全一致时才会把它叠加到内存 pose 预览；源 BIN 从不被打开为可写状态。

| 项目 | 规定 |
|---|---|
| Schema | `easytech-motion-proposal/v1` |
| 适用对象 | 通过完整 animations 段累计消费的单个欧7/征2 Spine animation root |
| 文件编码 | UTF-8 JSON |
| 源身份 | `source.sha256` + `source.engine` + `source.animation` 三重绑定 |
| 当前操作 | `bone_delta`、`slot_attachment` |
| 结果 | 只影响内存投影；支持会话内撤销与重做 |
| 写回 | 强制 `read_only: true`、`writeback: "forbidden"`；不生成 BIN 补丁 |

## 1. 最小合法文档

下面的模板由工作台按当前资源自动生成。AI 只能在 `operations` 内提出受限变换和附件切换，不应移除只读字段或修改 `source`。

```json
{
  "schema": "easytech-motion-proposal/v1",
  "name": "Wait 的只读 pose 提案",
  "read_only": true,
  "writeback": "forbidden",
  "source": {
    "sha256": "<当前 BIN 的 64 位 SHA-256>",
    "engine": "spine41",
    "animation": "Wait"
  },
  "operations": [
    {
      "id": "raise_root_01",
      "kind": "bone_delta",
      "bone": "root",
      "time": { "start": 0.0, "end": 0.2 },
      "delta": { "y": 8.0, "rotation": 4.0 }
    }
  ]
}
```

| 顶层字段 | 类型 | 约束 |
|---|---:|---|
| `schema` | string | 必须等于 `easytech-motion-proposal/v1`。 |
| `name` | string | 去除首尾空格后为 1–120 个字符。 |
| `read_only` | boolean | 必须为 `true`。 |
| `writeback` | string | 必须为 `forbidden`。 |
| `source.sha256` | string | 当前 BIN 的 64 位十六进制 SHA-256；任何不匹配均拒绝。 |
| `source.engine` | string | 必须等于当前工作区的 `spine38` 或 `spine41`。 |
| `source.animation` | string | 必须等于当前 pose 会话的 animation root 名称。 |
| `operations` | array | 1–256 个操作；每一个 `id` 必须唯一。 |

## 2. 操作语义

### 2.1 `bone_delta`

`bone_delta` 对**当前 pose 投影**施加相对增量。目标 `bone` 必须是当前静态骨架中已解析的骨骼名；所有数值必须为有限实数。当前版本只接受下表字段，避免把运行时世界矩阵、constraint 参数或未知字段伪装成可编辑能力。

| `delta` 字段 | 内存语义 |
|---|---|
| `x`、`y` | 加到已由 setup pose 与支持 timeline 计算出的局部平移。 |
| `rotation` | 加到已计算出的局部旋转角度（度）。 |
| `scale_x`、`scale_y` | 加到已计算出的局部缩放值；**不是**二进制字段写回，也不是 runtime mix。 |
| `shear_x`、`shear_y` | 加到已计算出的局部 shear 角度（度）。 |

`time.start` 与 `time.end` 必须满足 `0 ≤ start ≤ end ≤ animation.duration`。当 `time < start` 时操作不生效；在开区间内按线性系数 `(time - start) / (end - start)` 渐入；在 `time ≥ end` 时为 100%。若 `start == end`，这是一个在该时间点立即生效的阶跃提案。

### 2.2 `slot_attachment`

`slot_attachment` 只能为已解析的目标 slot 选择该 slot 可见的**既有 region attachment 名**，或设为 `null` 以隐藏附件。它不会创建图片、修改 ATLAS、添加网格，也不允许跨 slot 寻址附件。

```json
{
  "id": "hide_flash",
  "kind": "slot_attachment",
  "slot": "effect",
  "time": { "start": 0.5, "end": 0.5 },
  "attachment": null
}
```

> `slot_attachment` 的时间范围控制“提案何时接管当前 slot attachment”。它不会修改原 animation 的 attachment timeline。

## 3. 应用、撤销与审计

加载时，工作台依次验证 Schema、只读声明、SHA-256、引擎、animation root、骨骼/插槽/附件选择器与数值范围。通过后，提案进入 `MotionProposalSession` 的内存栈；**应用、撤销、重做只改变该栈**。切换 animation root、加载其他 Spine 资源或加载 BILE 三件套时，内存提案会话会被清空。

| 事件 | 行为 | BIN 影响 |
|---|---|---|
| 加载提案 | 仅追加至内存叠加栈，并刷新当前 pose。 | 无 |
| 撤销 | 从活动栈移至 redo 栈，并重投影。 | 无 |
| 重做 | 从 redo 栈恢复到活动栈，并重投影。 | 无 |
| 导出证据 | 输出 JSON：提案操作、源身份、采样时刻、图层数量、coverage 与诊断。 | 无 |
| 导出 pose 序列 | 仍基于原始 Spine pose 会话；它不隐式把提案变成 BIN 或补丁。 | 无 |

证据文件中始终携带 `read_only: true` 与 `writeback: "forbidden"`，并记录每个采样时刻激活的 `operation_id`、图层数和降级诊断。因此它可用于审阅“AI 建议了什么、何时生效、当前渲染器实际覆盖到哪里”，但不能作为游戏内回归通过的替代证据。

## 4. 运行时覆盖边界

提案叠加在现有 pose 投影器之上，**不扩大**它的已验证能力。只要应用过一个提案，画面会明确显示为非完整 runtime pose；工作台还会继续展示已有的 bezier、constraint、transform-mode、deform、mesh、draw-order、sequence 或 skin 映射降级诊断。

| 能力 | AI Motion DSL v1 状态 |
|---|---|
| setup blend + 已支持 bone/slot timeline 的内存 pose | 支持；仍以 pose 预览边界解释。 |
| 受限骨骼 transform 增量 | 支持；仅内存、可撤销。 |
| 已知 slot 的 region attachment 切换/隐藏 | 支持；仅内存、可撤销。 |
| bezier 精确求值、IK/transform/path constraint | 不支持；保留原有降级诊断。 |
| deform/mesh、draw order、sequence、完整 runtime playback | 不支持。 |
| Spine BIN 重写、Spine 补丁、游戏内实验包 | **明确禁止。** |

## 5. 工作台入口

选择一个已完整读取时间线的 Spine animation root 后，Ribbon 的 **Spine 动画 → AI 只读提案** 组提供四个入口：导出模板、加载提案、撤销/重做，以及导出 pose 提案证据。该组不会出现在 BILE 编辑流中；BILE 的保守补丁与 Spine 提案各自独立，不能互相转换。

> **社区发布措辞建议：** “AI Motion DSL v1 是对已验证 Spine pose 可视化子集的、哈希绑定的只读审阅提案；它不是官方运行时替代品，也不提供 Spine BIN 写回。”
