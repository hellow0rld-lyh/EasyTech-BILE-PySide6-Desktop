# BILE Workbench：动画专业瑞士军刀深化增量

> **历史实现记录**：本文保留专业取证能力增量交付时的设计、文件清单和测试快照。文中的测试数字与截图是当时证据，不代表当前完整回归结果；当前能力请以 README、docs/README.md 和源码为准。

**交付范围：** 本增量将工作台从“具备专业轨道编辑能力”深化为面向单个复杂 BILE 三件套的 **静态取证、编辑前影响认知、暂存变更审阅和回归闭环工作台**。它不改变 BILE v2/v3/v4 的解析模型，不扩大任何写回字段，也不生成或修改游戏资源文件。

## 新增能力

| 能力 | 用户解决的问题 | 产出或显示 | 格式边界 |
|---|---|---|---|
| **单动画静态档案** | 在编辑前理解整段动画的槽位覆盖、Track 分布与 BELE 复用。 | `*_static_evidence.json`、`*_static_evidence.md`；包含每槽位活动 Track/通道、全部静态 Track、BELE 全文档复用与目标元素。 | 只投影已解析的静态引用；不推断游戏内人数、实例数或最终运行时行为。 |
| **BELE 静态复用警戒** | 避免把共享 BELE 误认为“只会影响当前画面”。 | 检查器显示当前动画静态引用数、全文档 Track 数、动画根数及目标元素示例。 | 仅统计 `TrackContext`；不改 BELE/Track，也不承诺所有静态引用会在运行时同时可见。 |
| **变更账本与实时预检 Dock** | 在导出前直观看到暂存改动、来源绑定和预检告警，避免隐藏风险。 | BILE 版本、源 SHA-256、白名单说明、BELE/BMTI 暂存变化、完整重解析与 `initial_phase` 范围结果。 | 只读取 `EditSession.patch_payload()` 和既有 `run_preflight()`；绝不写源 BIN、补丁 JSON 或实验包。 |
| **Ribbon 与视图入口** | 让取证和安全审阅成为可发现的专业任务，而非隐藏脚本能力。 | “动画工具”的“输出与档案”组、“验证”的“候选与取证”组，以及“视图”页中的账本 Dock 开关。 | 使用原有 `QAction`；原菜单、快捷键、候选工作流和错误边界保持不变。 |

## 推荐的专业工作流

用户应先选择动画根，在时间线或轨道检查器定位 Track，再先阅读检查器内的 **BELE 静态复用警戒**。如果影响范围不直观，应先导出 **单动画静态档案**；该档案在未进行任何编辑时也可产生。随后，用户只可通过既有检查器白名单修改 v3/v4 的 BELE 仿射/ARGB/`initial_phase` 或 BMTI 锚点。每次暂存修改会自动更新 **变更账本与实时预检**；预检通过后，仍应使用候选差异、轨道影响范围、实验包和游戏内回归案例形成闭环。

> **关键边界：** “预检通过”表示候选 BIN 在现有解析器和白名单范围内能重解析，并不表示游戏内行为已经被证明。静态 Track 引用也不等同于外层编队数量、单位人数或运行时实例数。

## 深化后的定位

> **BILE Workbench 是面向 EasyTech 动画三件套的专业取证、保守编辑与跨游戏实验工作台。它将离散槽位—通道—保持段—Track—BELE 链路转化为可审阅证据，并把每一项写回限制在已验证字段、完整重解析和可追溯游戏内回归之内。**

这一区分很重要：工具有意不做新增/删除/重排 Frame、Track、元素、字符串或块的“自由动画制作”，也不写回 `playback_mode`，更不对 BILE v2 写回。其核心竞争力是使难以理解的动画资源变得 **可定位、可比较、可审计、可实验和可证明**。

## 工程实现

| 文件 | 作用 |
|---|---|
| `src/bile_workbench/animation_evidence.py` | 单动画静态档案生成器；JSON/Markdown 以及 BELE 全文档复用审计。 |
| `src/bile_workbench/ui_change_ledger.py` | 可停靠的变更账本和缓存化实时预检视图。 |
| `src/bile_workbench/app.py` | 档案导出动作、检查器复用警戒、账本 Dock、会话同步与 Ribbon/视图整合。 |
| `tests/test_animation_evidence.py` | 静态覆盖、BELE 复用、JSON/Markdown 以及只读声明的回归测试。 |
| `tests/test_app_document_session.py` | 账本、预检与关键帧复用警戒随暂存会话更新的离屏 GUI 回归。 |
| `tools/smoke_swiss_army_gui.py` | 自动加载样本、选择 Track、做可撤销编辑、展示账本并生成视觉截图。 |

## 验证记录

| 检查 | 结果 |
|---|---|
| 动画静态档案单元测试 | 2/2 通过。验证槽位覆盖、BELE 全文档复用和 JSON/Markdown 中的只读边界声明。 |
| 主窗口专业审阅 GUI 测试 | 3/3 通过。验证 Ribbon 上下文页、变更账本、实时预检和关键帧复用警戒。 |
| 离屏视觉冒烟 | 通过。`research/gui_swiss_army_ledger.png` 显示动画根列表、预览、时间线和账本可以在深色工作区同时使用。 |
| 全量回归 | **51/51 通过**，约 58 秒；原有 BILE 解析、跨游戏兼容、保守编辑、候选差异、实验包、回归案例和 XML 安全测试均保持通过。 |

## 设计依据

Rive 将时间线、当前动画、播放控制与“仅显示已选对象”结合，以降低复杂动画的审阅复杂度。[1] Unity 将当前选择、检查器、属性轨道和 Dopesheet 关联，使属性上下文与时间总览保持一致。[2] Blender 的 Dope Sheet 强调按通道/当前帧选择和标记来理解关键时刻。[3] BILE Workbench 只借鉴这些专业审阅范式；由于 BILE 当前实证模型是离散保持段和 Track 引用，工具没有将其误表示为可自由插入或移动的连续曲线系统。

[1]: https://rive.app/docs/editor/animate-mode/timeline "Rive — Timeline"
[2]: https://docs.unity3d.com/6000.5/Documentation/Manual/animeditor-UsingAnimationEditor.html "Unity Manual — Use the Animation view"
[3]: https://docs.blender.org/manual/en/latest/editors/dope_sheet/editing.html "Blender Manual — Editing Dopesheet Data"
