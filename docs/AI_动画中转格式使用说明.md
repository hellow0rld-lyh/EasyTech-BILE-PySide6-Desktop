# AI 动画中转格式使用说明

BILE Workbench 不让模型直接生成或覆盖二进制 BIN。它先导出带源哈希的 JSON，再只接受一组经过字段白名单限制的补丁。这样，AI 可以协助调整已有动画的位移、缩放、旋转、透明度、颜色和精灵锚点，而工具会拒绝错文件、越界索引、未知字段和结构性改写。

> 当前格式是**已有动画的安全提案格式**，不是“凭空新建任意 BILE 文件”的承诺。新建元素、增删帧、改通道数仍需要完整重建与游戏内回归。

## 工作流

| 步骤 | 在工作台中的操作 | 输入/输出 | 校验 |
|---|---|---|---|
| 1 | 打开同名 BIN、XML、WebP 三件套。 | 原始资源。 | 文件头、六个块、引用、字符串和时间线完整消费。 |
| 2 | 使用“导出 AI 中转 JSON”。 | `*.bile.json`。 | 写入源 BIN 的 SHA-256。 |
| 3 | 将 JSON 与下面的指令模板提供给 AI。 | AI 输出 `patch.json`。 | AI 只能描述字段变化。 |
| 4 | 使用“应用安全补丁 JSON”。 | 原 BIN + `patch.json` → 新 BIN。 | 核验 schema、源哈希、下标、字段类型，随后重新解析。 |
| 5 | 打开新 BIN 预览并与原始接触表比较。 | 新三件套。 | 工作台结构回归；最后仍需游戏内回归。 |

## 完整中转 JSON 的核心片段

导出的完整 JSON 使用以下标识：

```json
{
  "schema": "bile-workbench.interchange/v1",
  "kind": "full-document",
  "source": {
    "file": "anim_failure.bin",
    "sha256": "…"
  },
  "animations": [],
  "sprites": [],
  "keyframes": [],
  "patch_template": {}
}
```

`animations` 使用 `slot`、`tracks`、`keyframe` 和 `element` 展示嵌套时间线；`keyframes` 展示每个 BELE 关键帧的二维矩阵和 ARGB。模型可以阅读完整 JSON 进行理解，但**应用阶段只读取 `kind: "patch"` 的严格补丁**。

## 允许的补丁

```json
{
  "schema": "bile-workbench.interchange/v1",
  "kind": "patch",
  "source_sha256": "必须与导出文件相同",
  "keyframes": [
    {
      "index": 12,
      "transform": {
        "x": 18.0,
        "y": -6.0,
        "xx": 1.1,
        "xy": 0.0,
        "yx": 0.0,
        "yy": 1.1
      },
      "argb": "0xCCFFFFFF",
      "initial_phase": 1
    }
  ],
  "elements": [
    {
      "index": 4,
      "anchor": [-32.0, -16.0]
    }
  ]
}
```

| 对象 | 可改字段 | 效果 |
|---|---|---|
| `keyframes[]` | `transform.xx/xy/yx/yy/x/y` | 修改 BELE 仿射变换。矩阵可表达位移、旋转、缩放和斜切。 |
| `keyframes[]` | `argb` | `0xAARRGGBB`；最高字节是透明度。 |
| `keyframes[]` | `initial_phase` | BELE `+0x1C` 的无符号整数。导出前会验证其对所有实际子动画目标均小于子动画帧数；无子动画目标时会警告。 |
| `elements[]` | `anchor: [x, y]` | 修改 BMTI 图片锚点。 |
| `elements[]` | `name` | 仅支持与旧名称**UTF-8 字节数相同**的原位改名。 |

以下操作会被拒绝：改变记录数量、改变块顺序、改动 BRTS 长度、改动 BMTI 类型位、改动帧/通道计数、引用不存在的关键帧或元素、源哈希不匹配、超出真实子动画帧范围的 `initial_phase`，以及未知/不透明字段写入。`playback_mode` 虽会导出供分析，但当前样本未完成其子动画语义实证，因此严格禁止写入。

## 推荐给 AI 的指令模板

```text
你将收到一个 BILE Workbench 的 full-document JSON。请只输出一个合法 JSON 补丁，
不要输出 Markdown，不要改变 schema、kind 或 source_sha256。

目标：让动画 <动画名> 在槽位 <起点> 到 <终点> 从位置 (x1, y1) 平滑运动到 (x2, y2)，
并从 0% 淡入到 100%。

约束：
1. 只能写 keyframes[].index、transform 的 xx/xy/yx/yy/x/y、argb、initial_phase、elements[].anchor；禁止写 playback_mode。
2. 不得增加或删除关键帧、元素、通道、帧或轨道。
3. 所有 index 必须取自输入 JSON。
4. 使用 0xAARRGGBB 表示 argb。
5. 返回的 source_sha256 必须与输入完全一致。
```

## 注意事项

补丁系统会重解析写出的 BIN，因此它可以阻止明显损坏，但不能替代原游戏运行时测试。尤其是对于旋转、嵌套动画、超出原帧范围的保持帧和复杂 UI，建议先另存为实验 BIN，再从工作台输出接触表进行人工审查。任何想要增删元素或从零创建动画的 AI 功能，都应该通过一个未来的“完整重建”模式单独实现，而不是绕过当前安全边界。
