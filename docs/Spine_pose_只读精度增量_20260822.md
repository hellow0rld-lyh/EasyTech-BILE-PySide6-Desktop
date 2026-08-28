# Spine Pose 只读精度增量：Bezier、Light Tint 与 Draw Order

**状态：** 已实现并通过欧7 Spine 3.8.99、征2 Spine 4.1.x 真实资源回归。  
**范围：** 仅内存 pose 投影、ATLAS region 分层预览、GIF/APNG 序列审阅与工作台诊断。  
**二进制写回：** 严格禁止。

## 1. 本轮改善的目标

此前的 Spine 工作区能够完整累计读取欧7/征2的 animations 段，并投影骨骼、attachment 与 region layer，但连续曲线、slot 颜色和 slot 重排没有进入 pose 求值。这使得“读到了 timeline”并不等于“预览正确应用了 timeline”。本轮将三个可独立验证的层补入只读投影链：**cubic Bezier 关键帧插值、slot light RGBA/alpha 及 draw-order**。

> 本轮不把 partial pose 伪装成完整 Spine runtime。每帧仍会把 constraints、复杂 transform inheritance、dark/two-color、非 normal blend、mesh/deform/sequence 和图集映射歧义写入 diagnostics；`coverage_complete` 只在该帧没有已知降级项时才为真。

| 能力 | 3.8.99 欧7 | 4.1.x 征2 | 现在的行为 |
|---|---:|---:|---|
| 连续 bone timeline | 已有 | 已有 | 仍以 setup blend、alpha=1 投影。 |
| Bezier | 已实现 | 已实现 | 捕获控制点；使用单调二分在时间轴反解 cubic x，再计算 y 值。 |
| slot attachment | 已有 | 已有 | 离散切换，仍做 skin/region 映射诊断。 |
| slot light RGBA / alpha | 已实现 | 已实现 | 将 timeline 颜色与 setup slot、region attachment 颜色按通道相乘。 |
| dark/two-color | 读取并标记 | 读取并标记 | light color 可见；dark color 的双颜色混合仍降级。 |
| draw-order | 已实现 | 已实现 | 按 offset 重建 slot index 排列，并以排列顺序输出 region layers。 |
| mesh/deform/sequence | 未实现 | 未实现 | 继续严格降级，不绘制为 region。 |
| BIN 重写 | 禁止 | 禁止 | 无 patch、无 BIN 导出、无原地修改。 |

## 2. Bezier 插值

Spine 的 CurveTimeline 在相邻关键帧之间使用 linear、stepped 或 cubic Bezier 曲线。[1] [2] v3.8 的二进制曲线段携带一组四控制值；v4.1 的连续 timeline 可为每个属性分量携带独立的四控制值。项目现在将这些控制点保存在 `PoseFrame.curve`，而不是像此前一样只保留 `bezier` 标签。

对于目标时间 `t`，投影器先把 `t` 归一化到前后关键帧的时间区间，然后以 18 次二分在 cubic 的 x 曲线求出参数 `u`，最后以同一个 `u` 计算 y 曲线。多分量 track（如 translate）可以分别采用不同曲线；旧缓存、构造测试或未来未知变体若只有 `bezier` 标签而没有控制点，则不再偷偷跳到左帧，而是退回线性并显示“控制点未捕获”诊断。

该实现遵循官方 API 对 `setBezier(time1, value1, cx1, cy1, cx2, cy2, time2, value2)` 的参数语义，但没有引入或复制官方运行时源码。[2]

## 3. Light Tint 与 Alpha

Spine 静态 slot 与 region attachment 都有 RGBA；slot timeline 可以修改 RGBA、RGB、alpha 或 two-color 变体。[1] 当前 pose 层把可支持的 light 通道归一化为 `0..1` 浮点并计算：

> `layer.lightRGBA = setup/timeline slot RGBA × attachment RGBA`。

ATLAS renderer 随后在仿射变换前按 R、G、B、A 分别乘色。因此 alpha timeline 会直接影响合成透明度，而不是只在 timeline 档案中显示。two-color/dark color 已被读取并保留诊断，但没有以 Pillow 近似冒充 Spine 的 dark tint shader；非 normal slot blend 也继续显示明确诊断。

征2 `[mini]effect_ui10.bin` 的 `Wait` 包含多条 `rgba` alpha timeline。采样诊断显示它们的 alpha 值在 0、约 0.12、约 0.52 等区间变化，证实 4.1 字节色值捕获和归一化进入了实际 pose layer，而不是仅完成字节消费。

## 4. Draw Order

Spine draw-order 是 slot index 的离散排列，而不是视觉上的“后处理排序”。官方 3.8 参考实现使用正 varint 读取 changed slot 和 offset：先收集 unchanged 项，将 changed slot 放入 `originalIndex + offset`，再从尾部填补空位。[3] 本项目独立实现了同一语义，并在 3.8 和 4.1 的 selected pose parser 中保留每个 draw-order keyframe。

在 pose 投影时，setup order 默认为 `0..slot_count-1`；进入某个 draw-order key 后，projector 验证其为完整、不重复的 slot index 排列，随后按该排列构造 `PoseProjection.layers`。renderer 本身按 `layers` 的顺序 alpha composite，因此不会再把 draw-order 读取为“已知但未应用”的信息。

## 5. 导出与诊断语义

序列证据 JSON 的 boundary 已更新，记录本轮支持项与剩余降级项。GIF 是 256 色格式；当多次 pose 采样在量化后视觉等价时，Pillow 可能把它们压缩为较少的容器帧。为了不丢失审计意义，evidence JSON 始终逐请求采样写入全部 `frames`，每条包含采样时间、coverage、图层数和 diagnostics。对于逐样本验证，应以 evidence 的帧清单为准，而不将 GIF 容器帧数误读为 parser 或 pose 求值帧数。

工作台的 Spine 静态档案和资源诊断现在也明确列出：Bezier、slot attachment/light RGBA/alpha、draw-order 已用于**只读** pose；任何尚未支持的 runtime 特性继续按帧显示。Spine 动画 Ribbon 保持“导出 / 审阅 / AI 只读提案”定位，未新增写回操作。

## 6. 验证结果

| 验证层 | 结果 | 覆盖内容 |
|---|---|---|
| 纯内存单元测试 | 通过 | 单/多分量 Bezier、无控制点降级、RGBA 通道乘色、draw-order offset 与 layer 顺序。 |
| 欧7真实样本 | 通过 | Arthur2 `Wait` 的 3.8 控制点捕获、pose、ATLAS 合成和 UI 冒烟。 |
| 征2真实样本 | 通过 | `[mini]effect_ui10` 的 4.1 RGBA 字节捕获、coverage-complete pose、GIF evidence 和 UI 冒烟。 |
| 全项目回归 | **75/75 通过** | BILE v2/v3/v4、Scene Interchange、专业工作台、Spine、序列导出、AI Motion DSL。 |

欧7的 Arthur2 当前仍可能为 partial，这不是 Bezier 未支持，而是实际资源存在 transform mode、non-normal blend 或 attachment/ATLAS 映射歧义等其它未实现项。征2的 setup-compatible 样本则可以在本轮功能集内保持 `coverage_complete`。两个结果都符合“能力按实际帧、实际资源声明”的原则。

## 7. 下一步边界

下一阶段的优先项应为 IK/transform constraint 的读后求值，以及 region 与 mesh 的分流渲染；之后才讨论 deform 和 sequence。复杂 transform inheritance、dark/two-color 与非 normal blend 也需要独立的像素级验证。任何一步都不得绕过源 SHA-256、只读序列证据、独立重读或游戏内回归。

## References

[1]: https://en.esotericsoftware.com/spine-binary-format "Spine — Binary export format"
[2]: https://en.esotericsoftware.com/spine-api-reference "Spine Runtimes Guide — API Reference"
[3]: https://raw.githubusercontent.com/EsotericSoftware/spine-runtimes/3.8/spine-libgdx/spine-libgdx/src/com/esotericsoftware/spine/SkeletonBinary.java "Spine Runtimes 3.8 — SkeletonBinary"
[4]: https://en.esotericsoftware.com/spine-json-format "Spine — JSON export format"
[5]: https://en.esotericsoftware.com/spine-meshes "Spine User Guide — Mesh attachments"

## 8. 约束静态数据与受限求值增量

静态读取器现在不再只保留 IK/transform/path 的数量。欧7 Spine 3.8.99 与征2 Spine 4.1.x 均会把 IK 与 transform constraint 的名称、全局 `order`、skin-required 标志、受约束骨骼、target、offset 和 setup mix 保存在静态文档中，并继续通过完整 animations 段累计消费验证。旧的 `ik_constraint_count` 和 `transform_constraint_count` 仍以兼容属性提供，因此现有 timeline 引用边界不变。

在 pose 求值中，约束会按 `order` 排序后进入一个严格受限的 setup-path：**IK 仅执行 normal transform、非 skin-required、softness=0 的单骨或直接父子双骨链**；**transform constraint 仅执行 normal transform、非 skin-required、absolute-world 模式**。两个几何子集均有独立纯内存单元测试，并通过纯内存骨架夹具验证其实际改变 `BoneWorld`。约束条件不满足时，预览保持原 world matrix 并逐条写入诊断；这比使用近似数学去掩盖 runtime 差异更安全。

约束动画的 mix timeline、IK softness、非直接链、local/relative transform、skin activation、复杂 transform inheritance，以及 path constraint 仍未执行。它们没有被移出诊断，也没有被声明为 coverage-complete。当前完整项目离屏回归为 **82/82 通过**；这一数字包含 BILE、Scene Interchange、工作台、Spine 3.8/4.1、Bezier、颜色、draw-order、序列证据、独立 IK/transform solver 和 AI Motion DSL。

## 9. 动画约束 mix timeline 增量

Spine 3.8 与 4.1 的 selected pose parser 现会把 IK 与 transform constraint timeline 从“只消费”升级为 `PoseTrack`。IK 被拆分为连续的 `(mix, softness)` track 与离散的 `(bend, compress, stretch)` track；transform mix 保留 3.8 的四分量形式或 4.1 的六分量形式及各自的 Bezier 数据。这样保持二进制累计消费顺序不变，也避免把离散状态错误线性化。

在当前时间投影时，约束 timeline 值会覆盖 setup mix 后再进入受限求值器。3.8 transform 的 `rotate/translate/scale/shear` 四分量会显式映射为统一的六分量通道；4.1 直接使用其分离通道。纯内存回归已经验证在 0.5 秒中点，IK mix 从 0 到 1 会将 world axis 转到 45°，absolute-world transform translation mix 从 0 到 1 会把 world Y 推进到目标偏移的一半。

这不等于完整 Spine constraint runtime。若播放时出现 softness、非直接 IK 链、local/relative transform、skin-required constraint、非 normal transform 或无效分量，系统会保留当前矩阵并写出帧诊断。项目仍不写入或重建任何 Spine BIN。全量离屏回归保持 **82/82 通过**。

## 10. Mesh 静态与独立渲染子集

Spine 3.8/4.1 静态读取现在会保留普通 mesh 的 path、RGBA、UV、triangle indices、hull length 与顶点数据。无权重 mesh 的局部二维 vertices 直接被保留；加权 mesh 的骨骼影响数据仍会完整消费，但 `vertices` 显式保留为 `None`，不会被错误地按单 slot bone 投影。4.1 含 sequence 的 mesh 不会进入该子集；linked mesh、deform、clipping 同样未进入。

新增的纯内存 mesh pose 服务可将无权重局部顶点经 slot bone 的 `BoneWorld` 映射为 world vertices，并校验 UV/vertices 对齐与 triangle 索引。新增三角形纹理栅格化服务以 normalized UV 在 source image 中取样、逆仿射至预览画布并按 polygon alpha mask 合成。真实样本中，欧7 Arthur2 的唯一 mesh 为加权数据而保持降级；征2 EmpireCityFire01 的三份 mesh 均为无权重、8 顶点、10 triangle 的有效子集。

当前这一能力仍是**独立的只读几何/渲染模块**，尚未并入 `render_pose_layers` 的工作台 region layer；UI 不会把它展示为“mesh 已完整可见”。本项目完整离屏回归为 **84/84 通过**。

## 11. 无权重 MeshPoseLayer 已接入只读预览

无权重 mesh 现在不再只是独立工具。`PoseProjection` 增加了与既有 region `layers` 分离的 `mesh_layers`；当前 slot attachment 命中唯一无权重 mesh 时，系统将该 mesh 的 local vertices 经 slot bone `BoneWorld` 投影，保留 UV 和 triangle topology，并按 slot light RGBA 生成只读 mesh layer。加权 mesh、UV/triangle 不一致以及无法唯一映射的资源不会被伪造为 region，而会显示诊断。

`render_pose_layers` 现会将这些 mesh layer 纳入同一 world bounds 画布，解析其 ATLAS region、应用 light tint，并以逐 triangle 的逆仿射 UV 采样和 alpha polygon mask 合成。region layers 的既有接口仍保持不变；网格层被额外统计。当前实现仍不执行 deform、linked mesh、sequence、clipping、dark/two-color 或非 normal blend。项目完整离屏回归现为 **85/85 通过**。

## 12. 加权 Mesh setup pose 子集

静态读取现已保留加权 mesh 每个顶点的 `(bone index, local x, local y, weight)` influence 序列。只读 pose 对该 attachment 会使用所有已求值 bone world matrix，将 influence 的 world 坐标按权重累加，随后复用既有 UV triangle renderer。因此欧7 Arthur2 的加权 mesh 不再因“单骨 slot 假设”被跳过；它以**无 deform 的当前 setup/骨骼 pose**进入 mesh layer。

该提升并不执行 deform timeline。3.8/4.1 parser 仍完整消费 deform frames，并把 `deform:vertices` 保留在 animation 的不支持特性集合中，因此出现变形时间线的帧仍会被明确标注为 partial。加权 influence 读取、世界顶点计算和无效引用拒绝均有纯内存及真实欧7样本回归；当前项目不写入 Spine BIN。

## 13. Deform frame 只读取证

Spine 3.8 与 4.1 的 selected pose parser 现会在完整消费 deform timeline 的同时，将每个 frame 的 skin、slot、attachment、time、`start` 与 float value 数组保存为 `DeformTimelineEvidence`/`DeformFrameEvidence`，并附于 `PoseAnimation.deform_evidence`。该信息仅用于追溯、诊断与后续版本化验证；系统没有把它传入 weighted 或无权重 mesh 的 world vertex 投影。

因此当前预览遇到 `deform:vertices` 仍保持 partial，而不是把“能读出 values”误称为“已实现 deform”。3.8/4.1 animation 段在新增证据捕获后仍完成全段消费；不提供任何 BIN 重写、deform 写入或运行时补丁接口。

后续审计已将这个边界正式固化。官方格式将 deform 定义为指定 mesh attachment 的顶点键控：无权重与加权 mesh 的值解释不同，linked mesh 是否继承 source mesh 的 deform timeline 又取决于 attachment 设置。当前 evidence 已保留强类型 linear、stepped 或 Bezier curve，但尚未以独立真实样本验证 `start/values` 到无权重 local vertices、加权 bone influence 及 linked mesh 的版本化组合语义。因此不能将 values 直接叠加到已投影 world vertices；那会混淆 attachment-local 与 weighted vertex 计算空间。详细就绪性审计见 `research/spine_deform_application_readiness_20260822.md`；在其列出的受控子集、逐帧 curve 和真实可见回归具备前，deform 必须保持 evidence-only。[1] [4] [5]

工作台现会在 pose diagnostics 中追加 **Deform 只读审计**：显示已捕获 timeline、frame 与 values 数量、linear/stepped/Bezier/末帧 curve 分布，以及无权重 identity/span 预检数量。该摘要调用的是独立纯验证器；它既不更改 `PoseProjection` 或 mesh vertices，也不生成补丁、调用写回接口或修改 Spine BIN。当前完整离屏回归为 **98/98 通过**。

## 14. Linked mesh 与 sequence：静态 evidence-only 起点

Spine 3.8/4.1 静态解析已证明会消费 linked mesh 的 path、parent skin/name 与 deform-inheritance 标志；Spine 4.1 还会消费 sequence 的 `count`、`start`、`digits`、`setup_index`。这些字段此前只用于维持二进制读指针正确，尚未进入静态文档、renderer 或 pose projection。

本轮新增独立的 `LinkedMeshEvidence` 与 `SequenceEvidence` 数据契约，以及同-slot 的纯审计规则。征2 `EmpireCityFire01` 已作为真实 `attachment:sequence` timeline 样本固定为“完整消费但未执行”的诊断线索。**这不构成 linked mesh 或 sequence 渲染支持**：在静态 parent / inheritance / frame range 元数据保留、ATLAS frame 映射与真实样本回归完成前，它们继续显示为 partial diagnostics，Spine BIN 继续严格只读。

### 14.1 征2 4.1 sequence 静态 evidence

征2 4.1 静态解析现会把 region、mesh 与 linked mesh attachment 中已消费的 sequence `count`、`start`、`digits`、`setup_index` 保存为 `SequenceEvidence`；linked mesh 同时保留 path、parent skin/name、inherit timelines 与是否带 sequence 的只读证据。真实 `EmpireCityFire01` 回归确认存在非空 sequence evidence，且 sequence mesh 依旧不进入 `mesh_attachments` 的可渲染子集。

该增量只保留解析事实：它不选择当前帧、不解析 sequence timeline 的显示帧、不查找 sequence 图集区域，也不改变 pose projection、renderer 或 Spine BIN。所有 sequence attachment 继续通过明确诊断保持 partial。

### 14.2 欧7 3.8 linked mesh 静态 evidence

欧7 3.8 静态解析现会把 linked mesh 已消费的 path、parent skin/name 与 `inherit_deform` 写入 `LinkedMeshEvidence`。Arthur2 回归当前得到空 evidence 列表，说明该夹具不含可审计的 linked mesh；该事实不表示 linked mesh 已被渲染或被验证。与征2 sequence evidence 相同，3.8 linked mesh 字段仅服务于后续 parent、同-slot 与 inheritance 的只读核验；它不改变 mesh projection、renderer、pose coverage 或 Spine BIN。

### 14.3 回归基线

3.8 linked mesh 与 4.1 sequence 的静态 evidence-only 采集已纳入全量离屏回归；当前项目基线为 **103/103 通过**。该数字只证明严格解析、静态证据、既有 pose 降级、BILE 会话与工作台动作保持一致，**不**代表 linked mesh、sequence 或 deform 已加入可视运行时。

### 14.4 工作台审阅摘要

Spine 工作区 diagnostics 现会显示 attachment evidence 的 linked mesh 与 sequence 数量，并在同一行明确“仅审计，不渲染”。主窗口已将该 diagnostics 文本用于资源加载和 pose 审阅面板，因此该摘要随既有工作区加载/切换自然刷新；它不新增可写状态、不会跨 BILE/Spine 工作区残留，也不改变任何预览或导出动作的启用条件。

### 14.5 结构化 attachment 状态

工作区现将 attachment evidence 的状态作为独立审计事实输出：`captured_static_only` 表示当前样本保留了静态字段；`not_captured_in_current_sample` 表示该样本未出现对应元数据；两种状态均伴随 `rendering_state: forbidden`，不暗示运行时支持。清单 JSON 与 diagnostics 文本都显示该状态。接入期间同时修复了工作区错误依赖序列导出模块的循环导入，改为直接依赖 pose renderer；Spine 序列导出、主窗口会话与跨版本解析定向回归均通过。

### 14.6 完整回归基线

attachment evidence 的结构化状态摘要、工作区清单/diagnostics 接入，以及工作区–序列导出循环依赖修复完成后，完整离屏回归为 **104/104 通过**。所有结论仍受同一边界约束：静态 evidence 用于审计；linked mesh、sequence 与 deform 不进入未验证的运行时渲染或顶点应用；Spine BIN 不产生补丁且不被重写。

### 14.7 Sequence–ATLAS 静态范围核验

征2 `EmpireCityFire01` 现可对已捕获 sequence evidence 执行纯静态范围核验：attachment 前缀 `images/火焰序列/火焰序列-4_` 的 `count=16`、`start=0`、`digits=5` 对应 ATLAS 中唯一的 `00000..00015` 区域范围。验证结果以 `candidate_range_verified_static_only` 写入工作区 `attachment_evidence.sequence_atlas_validations`；缺失、重复、非法范围都会进入拒绝状态。该结果只证明候选命名和静态范围一致，**不**选择 sequence timeline 帧、不调用渲染器，也不修改 Spine BIN。

### 14.8 回归基线更新

sequence–ATLAS 静态范围核验及其工作区交付附录接入后，完整离屏回归为 **106/106 通过**。新增验证器的真实征2样本、缺失/重名拒绝夹具、BILE 工作流和全部既有 Spine 只读链路均在同一基线通过；sequence 继续保持“候选静态范围已核验、运行时帧选择与渲染仍禁止”的明确状态。

### 14.9 Spine 4.1 sequence timeline 原始证据

完整读取的 Spine 4.1 animation archive 现增加 `SequenceTimelineEvidence` 与逐帧 `SequenceTimelineFrameEvidence`。每个关键帧保留 `time`、二进制 `mode_and_index`、低四位 `mode_ordinal`、算术右移四位 `sequence_index` 和 `delay`。字段拆分仅按官方 4.1 binary reader 对 `modeAndIndex & 0xF`、`modeAndIndex >> 4` 以及紧随其后的 delay 的读取顺序记录，[6] 不在本工具中执行 `SequenceMode` 播放规则。

| 审计对象 | 已捕获事实 | 明确未实现 |
|---|---|---|
| 动态 `attachment:sequence` timeline | animation、skin、slot、attachment 身份；单调时间；packed mode/index；delay | mode 驱动的运行时状态转移 |
| 静态 sequence attachment | count、start、digits、setup index；ATLAS 候选命名范围唯一性 | 任意时刻的 sequence frame selection |
| 工作区 JSON | `attachment_evidence.sequence_timeline_evidence`；逐项 `selection_state=forbidden`、`rendering_state=forbidden` | 图像采样、renderer 接入、Spine BIN 写回 |

真实征2 `EmpireCityFire01.bin/Wait` 回归要求每条动态 timeline 身份精确落在已捕获的静态 sequence attachment 集合中；每帧时间和 delay 必须为有限值，raw packed 值与拆分值必须互相一致。该回归只验证已读取的二进制字段和静态身份约束，**不**计算播放结果。

该证据链接入后，完整离屏回归为 **107/107 通过**。新增覆盖包括真实 4.1 packed 字段拆分、静态 attachment 精确绑定、JSON manifest 的禁止选择/渲染状态与源 BIN 字节不变；它不改变 deform、linked mesh 或 sequence 的 runtime 支持边界。

[6]: https://github.com/EsotericSoftware/spine-runtimes/blob/4.1/spine-libgdx/spine-libgdx/src/com/esotericsoftware/spine/SkeletonBinary.java "Spine Runtimes 4.1 — SkeletonBinary"

### 14.10 Linked mesh 父级静态身份核验

为避免在没有真实样本时把 linked mesh 的 parent 字段误当成可渲染继承关系，项目对用户提供的 782 个 BIN 执行只读静态扫描：其中 680 个被当前已验证的 Spine 3.8/4.1 static parser 识别，82 个包含至少一条 linked mesh evidence。该扫描不解析 events/animations、不更改任何原文件，原始结果固化于 `research/spine_linked_mesh_sample_scan_20260822.json`。

征2 `[mini]effect_ui5.bin`（4.1.24）提供了一个最小真实锚点：child `Style4 / slot 0 / 战役简单-下层水流` 声明 parent `Style2 / slot 0 / 战役困难-下层火焰4`，并在当前已解析的**非 sequence 普通 mesh 子集**中恰好命中一次。官方 4.1 reader 会以 linked mesh 声明的 skin（缺省时 default skin）、slot 和 **skin attachment table key**（parent 字段）寻找 parent attachment，[6] 因此工作区只输出 `verified_static_identity_only`，而不声明 parent 几何、transform、deform 或 timeline 已被应用。

| 验证状态 | 可证明的范围 | 永不隐含的能力 |
|---|---|---|
| `verified_static_identity_only` | parent skin、slot 和 attachment table key 在当前非 sequence 普通 mesh 子集中唯一命中 | 顶点拷贝、inherit timelines/deform、linked mesh pose、渲染 |
| `verified_static_identity_sequence_mesh_only` | parent skin、slot 和 attachment table key 在 sequence evidence 中显式标记为 mesh 且唯一命中 | sequence frame selection、mesh 顶点解析、linked mesh pose、渲染 |
| `candidate_parent_rejected` | 缺失 parent key、候选 parent key 重复，或 parent key 不在当前已捕获的 mesh identity 子集 | 任何内部 name/path 的回退匹配或 parent 猜测 |
| `vertex_resolution_state=forbidden` | 当前没有 parent 几何解析结果 | world vertex 计算、deform 应用 |

工作区 manifest 在 `attachment_evidence.linked_mesh_parent_validations` 中交付这些状态，diagnostics 分别聚合普通 mesh 与 sequence mesh 的已核验数量。随后保留了 skin table key 并将验证器从内部 name 修正为 key；在同一 82 个 linked mesh 资源、4,465 条 linked mesh evidence 的重审计中，精确静态命中由 1,470 提升至 4,457。继续把 sequence attachment 的 table key 与 kind 保留为证据后，余下 8 条全被识别为 `verified_static_identity_sequence_mesh_only`，因此当前 4,465 条均有**静态身份**结论。这个结论仍不产生任何 sequence frame selection、mesh vertices、inherit/deform、`PoseProjection`、renderer、sequence evaluator 或 Spine BIN 写回能力；真实 sequence mesh parent、key/name 不同样本、缺失/重复拒绝夹具、manifest 摘要和源 BIN 字节不变均由离屏回归覆盖。接入后的完整离屏回归为 **112/112 通过**。

### 14.11 Sequence timeline–static range 只读交叉审计

4.1 `attachment:sequence` timeline 的 attachment 引用现明确作为 skin attachment table key 保存，并与静态 `SequenceEvidence.attachment_key` 以 `(skin, slot, key)` 精确交叉绑定。官方 runtime 以 sequence 的 region 数组索引操作 timeline index，而以 `start + index` 形成命名路径；因此 raw index 是**零基 region index**，static `start` 只作候选名称偏移。[6] 本审计只比较同一已读取身份和 `0..count-1` 的 raw region index 数值范围，不复用或实现任何 `SequenceMode` 行为。

| 审计状态 | 仅能证明 | 不代表 |
|---|---|---|
| `timeline_static_identity_verified_raw_region_index_observed_only` | timeline key 唯一命中静态 sequence attachment，且 raw region index 位于 `0..count-1` | 时刻对应实际图像帧、mode 播放规则、delay runtime、可渲染性 |
| `timeline_static_identity_verified_raw_region_index_outside_only` | identity 已命中，但至少一个 raw index 数值不在 `0..count-1` | 格式损坏或 runtime 应如何处理 |
| `timeline_static_attachment_rejected` | static key 未捕获、歧义或静态 count 非法 | 可用替代 attachment 或回退匹配 |

真实征2 `EmpireCityFire01/Wait` 的 7 条 timeline key 均唯一绑定到 `attachment_kind=mesh` 的 static sequence evidence；静态证据的命名偏移为 `start=0`、region count 为 `16`，已消费 raw index 为 `0, 4, 8, 11, 12, 15` 的组合，均落在零基 region 范围 `0..15`。工作区在 `attachment_evidence.sequence_timeline_static_validations` 交付该结果，并对每项固定 `selection_state=forbidden`、`rendering_state=forbidden`、`writeback=forbidden`。测试中的缺失 key 与 raw index=16 夹具只能生成明确审计状态，绝不触发帧选择。

为避免把该 `start=0` 样本的偶然一致误写为通用格式规律，项目对已提供资源执行独立只读扫描：468 个已完整静态读取的 4.1 资源中共发现 355 条 static sequence evidence，58 条具有非零 `start`；其中 57 条能以 `(skin, slot, attachment key)` 精确关联 sequence timeline。强锚点为 `[mini]form_main3.bin/Cast` 的 `封面流焰2-baopo1_`：static `start=54`、`count=39`，而其已消费 timeline raw index 为 `0`。纯审计在该 key 的首时刻接受 region index `0`，并仅导出 `candidate_name_ordinal=54`，由此在真实样本上区分了 **零基 region index** 与 **命名偏移**；该结论仍不选择图像帧、不采样 ATLAS、不渲染且不写回 BIN。接入后的完整离屏回归为 **121/121 通过**。

### 14.12 单时刻 sequence region-index 纯审计

官方 4.1 `SequenceTimeline` 在非首帧前的情形依赖 runtime blend 与 slot 状态；在可审计的非负 raw time 中，它选择不晚于 target time 的最后一个 timeline key，并按 key 的 `mode/index/delay` 与 sequence region count 推导 slot sequence index。[6] 本项目将这一行为规格重写为独立的、**不接触 runtime 对象**的数学审计：输入为唯一绑定的 static sequence evidence、一个 timeline evidence 和显式非负 finite target time；输出为 `audited_region_index` 与仅作命名算术的 `candidate_name_ordinal=start+index`。

| 前置条件 | 拒绝原因或限制 |
|---|---|
| 精确 `(skin, slot, attachment key)` 唯一静态绑定，且 `count > 0` | 缺失、歧义或非法 count 返回 `audit_rejected` |
| target time 非负且有限，且不早于首 key | 首帧前依赖 blend/slot setup，返回拒绝；不模拟 runtime |
| mode ordinal 为官方 `0..6` | 非法 ordinal 返回拒绝 |
| 非 hold mode 的 delay 为正且有限 | 非法 delay 返回拒绝 |
| base region index 位于 `0..count-1` | 超范围返回拒绝 |

对合成纯证据，七个官方 mode 的数学分支都经过回归；所有结果固定 `frame_selection_state=forbidden`、`attachment_application_state=forbidden`、`rendering_state=forbidden`、`writeback=forbidden`。真实 `EmpireCityFire01/Wait` 的首条 loop timeline 在 raw time `0.1` 时只导出审计 region index `1`，并不选择任何 WebP/ATLAS 图像帧，也不修改 slot、pose 或 BIN。接入后的完整离屏回归为 **117/117 通过**。

该审计现可导出为确定性、哈希绑定的 `easytech-spine-sequence-time-audit/v1` JSON evidence。顶层固定包含源 BIN `source_sha256`、engine、Spine version、animation、显式 `target_time`、`time_domain=unlooped_raw_animation_time_only`，以及各 timeline 的结构化 audit。顶层和每项 audit 同时明确 `frame_selection=forbidden`、`attachment_application=forbidden`、`rendering=forbidden`、`writeback=forbidden`。相同 workspace、animation 和 target time 的重复导出字节一致；负时间并不触发任何回退，而是以 `audit_rejected` evidence 交付。该 JSON 旨在让专业审阅或 AI 中转可以复核已消费的数值与边界，而非赋予播放、图像采样或 BIN 修改权限。接入后的完整离屏回归为 **119/119 通过**。

该 evidence 现额外包含 `candidate_name_audits` 附录。每项先要求单时刻 region-index audit 成功，再以 static `start`、digits 与 attachment name 组成**候选名称字符串**，仅在完整 static candidate range 已唯一匹配 ATLAS 且该名称恰好出现一次时报告 `candidate_name_identity_verified_static_only`。真实非零 start 锚点 `[mini]form_main3/Cast` 在 index `0` 时只验证候选名称 `封面流焰2-baopo1_00054` 的静态唯一身份；输出固定 `frame_selection_state=image_sampling_state=attachment_application_state=rendering_state=writeback=forbidden`。缺失或重名 ATLAS、非法 static range 和失败的 time audit 均只产生结构化拒绝，不会回退为图像帧、slot attachment 或 renderer 输入。接入后的完整离屏回归为 **123/123 通过**。

工作台在“文件”菜单和“Spine 动画”Ribbon 的“动画档案”组提供“导出 Spine sequence 时间审计证据”。它只会在存在已选 pose animation 的完整 Spine 4.1 workspace 时启用，并取当前只读 pose 审阅时间作为 raw target time；Spine 3.8、未加载资源与切换到 BILE 工作区时一律禁用。导出过程明确提示它没有选择图像帧、没有渲染 sequence，也没有写回 BIN；离屏 GUI 回归覆盖 4.1 可用、3.8/BILE 禁用、当前时间传递和源 BIN 字节不变。接入后的完整离屏回归为 **120/120 通过**。

### 14.14 clipping attachment 静态边界证据

Spine 3.8 与 4.1 的官方 binary reader 在 clipping attachment 分支均先消费 `endSlotIndex` 与 `vertexCount`，然后才读取顶点载荷，并可在 nonessential 情况下继续消费颜色。[7] [8] 本工作台现以独立 `ClippingEvidence` 保留已消费的 `(spine version, skin, slot, attachment key, end slot index, vertex count)`；**顶点坐标、权重、颜色、裁剪多边形与裁剪结果均不保留**。每条 evidence 固定 `vertex_application_state=forbidden`、`clipping_rendering_state=forbidden`、`writeback=forbidden`。

| 审计层级 | 已验证事实 | 明确未声明/未实现 |
|---|---|---|
| static parser | attachment identity、end slot 索引、vertex count 已按各版本字段顺序消费 | 顶点几何正确性、world vertices、裁剪多边形 |
| static boundary validator | `vertex_count > 0`，且 `end_slot_index` 位于当前 static slot 范围 | 裁剪生效区间、draw order、runtime slot 状态 |
| workspace manifest | `attachment_evidence.clippings` 与 `clipping_static_validations` 可复现交付 | texture sampling、mesh/region 裁剪、画面渲染 |

跨已提供资源的严格只读扫描覆盖 212 个 3.8 资源与 468 个 4.1 资源，分别捕获 46 与 185 条 clipping evidence。欧7 `Arthur2.bin` 的 `default/slot=3/root` 给出 `end_slot=4`、`vertex_count=4`；征2 `[mini]form_main1.bin` 的 `default/slot=0/cq` 给出 `end_slot=82`、`vertex_count=4`。双版本真实回归、无效 end-slot/vertex-count 拒绝夹具、manifest/diagnostics 交付以及源 BIN 零写入均已覆盖。接入后的完整离屏回归为 **126/126 通过**。**这些事实不构成 clipping render、裁剪 preview 或完整 Spine runtime 支持。**

[7]: https://raw.githubusercontent.com/EsotericSoftware/spine-runtimes/3.8/spine-libgdx/spine-libgdx/src/com/esotericsoftware/spine/SkeletonBinary.java "Spine Runtimes 3.8 — SkeletonBinary clipping attachment branch"

[8]: https://raw.githubusercontent.com/EsotericSoftware/spine-runtimes/4.1/spine-libgdx/spine-libgdx/src/com/esotericsoftware/spine/SkeletonBinary.java "Spine Runtimes 4.1 — SkeletonBinary clipping attachment branch"

### 14.15 dark/two-color slot timeline raw evidence

Spine 3.8 的 slot type `2` 对应 `two_color`，其关键帧携带 light RGBA 与 dark RGB；Spine 4.1 将对应通道拆为 `rgba2`（7 通道）与 `rgb2`（6 通道）。官方 runtime 分别声明 `SLOT_TWO_COLOR=2` 以及 `SLOT_RGBA2=3`、`SLOT_RGB2=4`，并使用相应 Timeline 类型读取这些通道。[9] [10] 本项目的严格 timeline parser 已消费上述帧、通道与曲线；本次新增将 selected pose 中的这部分**已消费值**提升为强类型 `TwoColorTimelineEvidence`，而不改变 pose projection 或 renderer。

| 证据字段 | 可复核事实 | 明确禁止 |
|---|---|---|
| `light_components` / `dark_rgb` | 关键帧读取出的 light/dark 原始归一化通道 | 将通道应用到图片像素 |
| `curve` | 已消费的 existing curve descriptor | runtime mix、完整 blend 行为 |
| timeline slot/name/kind/time | 证据绑定到 animation 与 slot track | slot attachment 写入、ATLAS 采样、渲染 |

跨样本 archive 扫描覆盖 133 个严格读取的 3.8 资源与 359 个 4.1 资源：当前 3.8 样本未捕获 `two_color` timeline；4.1 捕获 203 条 `rgba2/rgb2` timeline、共 471 帧。征2 `EmpireCityFire01.bin/Wait` 提供三条 `rgb2` 与一条 `rgba2` 实锚点；`effect_skill50.bin` 提供多帧 `rgb2/rgb2` 锚点。哈希绑定 `easytech-spine-two-color-audit/v1` JSON 可导出当前 pose session 的所有 raw evidence，重复导出确定一致；欧7当前无 two-color 的 session 如实导出空 `timelines`，绝不伪造回退。

工作台在“文件”菜单和“Spine 动画”Ribbon 的“动画档案”组增加“导出 Spine dark/two-color 审计证据”。它只在存在完整只读 pose session 时启用，界面明确提示：**不应用 dark tint、不创建像素输出、不渲染、不写回 BIN**。当前 pose projection 会保留 dark 值并给出“renderer 仅应用 light RGBA，预览非完整”的 diagnostics；这不是 two-color renderer 支持。

[9]: https://raw.githubusercontent.com/EsotericSoftware/spine-runtimes/3.8/spine-libgdx/spine-libgdx/src/com/esotericsoftware/spine/SkeletonBinary.java "Spine Runtimes 3.8 — TwoColorTimeline slot type"

[10]: https://raw.githubusercontent.com/EsotericSoftware/spine-runtimes/4.1/spine-libgdx/spine-libgdx/src/com/esotericsoftware/spine/SkeletonBinary.java "Spine Runtimes 4.1 — RGBA2Timeline and RGB2Timeline slot types"

本节所述 two-color raw evidence、哈希绑定导出与 Ribbon 入口接入后的完整离屏回归为 **132/132 通过**；该基线不改变当前 renderer 仅应用 light RGBA 的限制。

### 14.16 受限 straight-alpha normal two-color preview

在 raw two-color evidence 之后，工作台对官方 Spine 4.1 `Tint Black` shader 的 normal-alpha 行为进行了额外核验。该 shader 使用预乘 alpha blend `One / OneMinusSrcAlpha`；其 straight-alpha 输入分支以 `(1 - tex.rgb)` 形成 dark 基础项，将 light/dark tint 组合后再乘 texture alpha。[11] [12] 本地实现没有复制 runtime shader，而是以独立、逐像素可测的 Pillow 内核建立该 straight-alpha 分支在 **Pillow straight RGBA 输出**上的受限可视等价。

| 前置条件 | 本地行为 | 失败处理 |
|---|---|---|
| normal `blend_mode=0` | 可以进入受限 two-color 合成候选 | 非 normal blend 保持 light-only，明确 diagnostics |
| source 全不透明，或半透明像素中存在 `RGB > alpha` 的 straight-alpha 证明 | 将 `light RGBA`、`dark RGB` 合成为 source，再复用既有 affine/mesh 与 `alpha_composite` | alpha 编码不充分时保持 light-only，明确 diagnostics |
| 无 PMA、gamma/linear、外部 `_Black` 偏置、dark-alpha additive 要求 | 受限 local preview | 这些材质/runtimes 分支全部未实现 |

跨真实 two-color resource 的前置条件审计检查 38 个 animation/time job，获得 4 个同时具备 normal region dark layer 与 straight-alpha 证明的候选。征2 `[mini]effect_ui8.bin/Cast@0.06666667014360428` 的 `upgradation glow_00000` 是真实接入锚点：其 normal blend region 有 4,775 个半透明像素，其中 1,576 个满足 `RGB > alpha`。该真实资源回归确认 renderer 只读输出含“已应用受限 straight-alpha normal two-color preview”的 diagnostics，源 BIN 字节不变。

**仍然不支持**：PMA-unverified input、gamma/linear conversion、外部 Black Point、dark-alpha additive、non-normal blend、sequence attachment、clipping、完整 runtime mix/playback，以及任何 Spine BIN 写回。若缺少所需证据，系统不会猜测 alpha 编码，自动降级到已验证的 light RGBA 路径。

[11]: https://raw.githubusercontent.com/EsotericSoftware/spine-runtimes/4.1/spine-unity/Assets/Spine/Runtime/spine-unity/Shaders/Spine-Skeleton-TintBlack.shader "Spine 4.1 — Skeleton Tint Black shader"

[12]: https://raw.githubusercontent.com/EsotericSoftware/spine-runtimes/4.1/spine-unity/Assets/Spine/Runtime/spine-unity/Shaders/CGIncludes/Spine-Skeleton-Tint-Common.cginc "Spine 4.1 — Tint Black fragment formula"

本节的公式夹具、alpha 证据审计、真实征2 normal region 预览、降级分支与全项目联合回归已完成；最新完整离屏基线为 **138/138 通过**。该数字不扩展上述未支持 feature 的范围。
