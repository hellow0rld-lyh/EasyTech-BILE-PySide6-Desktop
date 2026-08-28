# Spine 新引擎静态工作区技术说明

**版本：v0.1；范围：欧洲战争 7（欧7）与征服者 2（征2）新引擎资源；开发者：3136818780（AI 辅助研究与文档整理）；日期：2026-08-22。**

本说明记录 BILE Workbench 新增的 **Spine 静态工作区**。该分支与 BILE v2/v3/v4 完全隔离：它读取欧7与征2的标准 Spine 静态骨架、同名 ATLAS 和可见区域，不重写二进制、不生成补丁、不将未解码的事件或动画时间线误称为已支持。Spine 官方将二进制 skeleton data 定义为其运行时可加载的序列化导出；具体版本必须由对应运行时读取，不能把 3.8、4.1 或 BILE 的字段规则互相套用。[1] [2] [3]

> **本轮关键结论：欧7的 212 份 BIN 是标准 Spine 3.8.99；征2的 468 份 BIN 不是未知外层容器，而是标准 Spine 4.1 的 `long hash` 起始格式。** 因此，两条新引擎支线已从“猜测候选”跨越到“具有官方读取顺序与全样本静态区验证的独立工作区”。

## 1. 实测格式矩阵

| 维度 | 欧7 | 征2 | 证据等级 |
|---|---|---|---|
| 样本 BIN | 212 | 468 | 全量本地清点。 |
| 版本分布 | 3.8.99：212 | 4.1.14：261；4.1.24：116；4.1.23：75；4.1.21：10；4.1.20：5；4.1.19：1 | 全量头部兼容性探针。 |
| 头部入口 | `0x00`：`string hash → string version` | `0x00`：8 字节 big-endian `long hash → string version` | 分别与官方 3.8、4.1 `SkeletonBinary` 顺序相符。[2] [3] |
| 静态区严格读取 | 212 / 212 | 468 / 468 | 读取至 skins 结束，逐项检查计数、索引、浮点与文件边界。 |
| ATLAS 方言 | `xy/size/orig/offset/index` | `bounds/offsets/rotate`（存在最小省略形式） | 本地 ATLAS 文本与区域裁切验证。 |
| 当前写回 | 禁止 | 禁止 | 产品安全边界。 |

欧7头部的第一项是可读的 Spine source hash 字符串，随后才是 `3.8.99` 版本字符串。征2头部的前八字节初看像“自定义前缀”，但按 4.1 官方运行时的 `readLong()` 读取后，紧接的版本、bounds、`nonessential`、fps、images 路径以及后续静态结构均连续成立。因此它应被描述为 **Spine 4.1 的标准 long hash 头部**，而非仍待猜测的外层壳。[3]

## 2. 已实现的静态读取范围

两个版本分别实现了版本固定的、可拒绝异常输入的静态读取器。读取器会校验 UTF-8 字符串、varint 长度、计数上限、父骨骼指向、骨骼/插槽/皮肤索引、枚举范围、有限浮点数以及每次读取的文件边界。静态骨架读取在 skins 结束处记录精确 offset，并把其后字节作为 **未解码尾部** 保留，绝不尝试“猜测跳过”后将文件列为完整解析。

| 静态区段 | 欧7 Spine 3.8 | 征2 Spine 4.1 | 工作台用途 |
|---|---|---|---|
| header 与共享字符串 | 已读取 | 已读取 | 版本分流、哈希绑定、图像路径与中转元数据。 |
| bones 与 slots | 已读取 | 已读取 | 骨架层次、初始姿态、绑定关系审阅。 |
| IK / transform / path constraints | 已穿越并统计 | 已穿越并统计 | 复杂度档案；尚未开放求解编辑。 |
| skins 与附件 | 已读取至 skins 末端 | 已读取至 skins 末端；处理 4.1 sequence 元数据跳过 | 皮肤、区域附件、图集关联与局部视觉取证。 |
| events 与 animations | 未解码 | 未解码 | 显式标为后续工作，未提供播放或写回。 |

官方 3.8/4.1 读取器均将 events 和 animations 放在 skins 之后；4.1 相较 3.8 还增加了 long hash、扩展的 transform mix 字段和 attachment sequence 数据。[2] [3] 这些差异是拆分版本读取器而非做“宽松万能解析器”的原因。

## 3. ATLAS 预览与工作台入口

新建 `spine_atlas.py` 读取两种本地 ATLAS 方言。加载器会验证 page 尺寸与实际 PNG/WebP 一致，验证每个区域未越出图集边界，并把 `rotate:true` 或 `rotate:90` 的区域在预览时顺时针旋转补偿。Spine ATLAS 的 region 元数据与旋转规则来自官方 Atlas 格式文档；本地实现仅用于静态区域预览，不是完整运行时网格渲染器。[4]

工作台文件页新增以下只读入口：

| 入口 | 行为 | 安全边界 |
|---|---|---|
| **打开 Spine 静态资源** | 打开同名 `.bin + .atlas + 图集页`，自动在欧7 3.8 与征2 4.1 间分流。 | 不调用 BILE 编辑会话。 |
| **资源浏览器** | 列出骨骼、插槽与 ATLAS 区域；选择区域即更新中央预览。 | 不将区域选择误作动画关键帧。 |
| **资源诊断** | 显示版本、静态数量、约束数量、图集方言、静态区末尾和未解码尾部字节。 | 诊断不推断运行时动作。 |
| **导出 Spine 静态档案** | 导出 JSON，包括 SHA-256、静态骨架、图集区域和显式边界。 | `read_only=true`；`writeback=forbidden`。 |

## 4. 验证结果

| 验证类别 | 结果 |
|---|---|
| 欧7 3.8 头部兼容性 | 212 / 212 通过。 |
| 征2 4.1 头部兼容性 | 468 / 468 通过。 |
| 欧7静态区读取至 skins 结束 | 212 / 212 通过。 |
| 征2静态区读取至 skins 结束 | 468 / 468 通过。 |
| 欧7传统 ATLAS `剑` 区域预览 | 176×176，旋转还原视觉核验通过。 |
| 征2新式 ATLAS 火焰区预览 | 180×180，`offsets` 与 `rotate:90` 视觉核验通过。 |
| 离屏主窗口冒烟 | 欧7 `Arthur2.bin` 与征2 `EmpireCityFire01.bin` 均可加载、选区、预览和导出；BILE 待提交写回动作保持禁用。 |
| 项目完整回归 | 56 / 56 通过，约 58 秒。 |

## 5. 关键边界与下一跳

当前新引擎支线已经提供了 **全量静态骨架审阅、ATLAS 局部取证、结构档案和 AI 可消费的只读 JSON**。它尚不等于“Spine 动画编辑器”：Animations 时间线、曲线、deform、draw order、event、sequence 运行时推进以及网格/加权骨骼最终渲染还没有解码。因此工作台不显示伪时间线，不导出伪动画，不开放 bytes 级写回。

下一阶段的高价值路径应是先按对应版本的 `readAnimation` 实现只读时间线档案，分别统计 slot、bone、constraint、deform、draw-order 和 event 时间线；然后在真实 Atlas/骨骼渲染结果上建立只读序列预览。只有当一个动画类型能做到“读取 → 导出中转 → 再读取 → 游戏内播放”四段证据闭环时，才应讨论受限代码化编辑。BILE 的保守编辑路径与 Spine 的未来编辑路径不能共享补丁格式或安全假设。

## References

[1]: https://en.esotericsoftware.com/spine-binary-format
[2]: https://raw.githubusercontent.com/EsotericSoftware/spine-runtimes/3.8/spine-libgdx/spine-libgdx/src/com/esotericsoftware/spine/SkeletonBinary.java
[3]: https://raw.githubusercontent.com/EsotericSoftware/spine-runtimes/4.1/spine-libgdx/spine-libgdx/src/com/esotericsoftware/spine/SkeletonBinary.java
[4]: https://en.esotericsoftware.com/spine-atlas-format

[1] Spine. “Binary export format.” 官方格式文档，访问于 2026-08-22。

[2] Esoteric Software. “SkeletonBinary.java, Spine Runtimes 3.8.” 官方运行时源码，访问于 2026-08-22。

[3] Esoteric Software. “SkeletonBinary.java, Spine Runtimes 4.1.” 官方运行时源码，访问于 2026-08-22。

[4] Spine. “Atlas export format.” 官方格式文档，访问于 2026-08-22。
