# BILE Workbench：生产力 Ribbon 界面增量

**版本范围：** `py-workbench-evolution` 的 PySide6 桌面工作台界面增量。本文档对应 `BILE_Workbench_功能区界面增量包.zip`，该增量仅重构命令呈现与工作区组织；**不改变 BILE v2/v3/v4 的解析语义、写回白名单、候选工作流或游戏资源文件**。

## 设计结果

本次重构将原有的全动作平铺工具栏替换为 **任务导向 Ribbon**，并保留原有菜单、快捷键和 `QAction` 作为同一命令源。因此，快捷键、错误处理、会话订阅、候选包生成和保守写回逻辑没有复制或分叉。Ribbon 只负责重新组织命令的可发现性。

| 层级 | 作用 | 包含内容 |
|---|---|---|
| 快速操作带 | 跨任务高频入口 | 打开 BILE、导出待提交补丁、撤销、重做、播放。 |
| 核心工具页 | 始终可发现的任务入口 | 文件、编辑、验证、实验、视图。 |
| 上下文工具页 | 只在选择具备语义时出现 | 动画工具、轨道工具。 |
| 可停靠专业面板 | 同时可见的专业工作区 | 资源浏览器、动画导航、检查器、轨道检查器、时间线、资源诊断。 |
| 固定状态栏 | 不随主消息消失的状态读数 | BILE 版本、只读/保守写回边界、暂存变更数、元素或 Track 上下文。 |

## 工具页与上下文规则

| 工具页 | 功能组 | 出现或启用规则 |
|---|---|---|
| 文件 | 资源；中转与交付 | 始终可见；无文档时只允许打开相关动作。 |
| 编辑 | 历史；审阅 | 始终可见；撤销/重做随编辑历史启用。 |
| 动画工具 | 播放与定位；输出 | 仅在选中动画根时显示。精灵元素不会显示该页。 |
| 轨道工具 | 当前 Track；影响范围 | 仅在时间线或轨道检查器已选择验证过的 `TrackContext` 时显示。 |
| 验证 | 候选；游戏内回归 | 需要可编辑 v3/v4 文档和至少一项暂存变更的操作会禁用，避免显示可执行假象。 |
| 实验 | 跨游戏组合；诊断 | 组合实验需要选中动画根；`def_array` 摘要与诊断需要加载三件套。 |
| 视图 | 专业面板；时间与取证；工作区 | 可开关所有 Dock，并可恢复默认 CAD 式工作区。 |

> **安全边界仍然不变。** Ribbon 未提供添加/删除帧、创建/重排 Track、新增元素、编辑 `playback_mode` 或直接保存源 BIN 的入口。BILE v2 仍严格只读；v3/v4 仍仅通过原有的 BELE 仿射/ARGB/`initial_phase` 和 BMTI 锚点白名单进行暂存、重解析、预检和导出。

## 实现文件

| 文件 | 作用 |
|---|---|
| `src/bile_workbench/ui_ribbon.py` | 独立的轻量 Ribbon 组件：核心/上下文工具页、功能组、快速操作带；直接复用 `QAction`。 |
| `src/bile_workbench/app.py` | 主窗口命令分组、上下文页同步、Dock 视图入口、默认布局恢复、固定状态栏和可用性状态。 |
| `src/bile_workbench/theme.py` | Ribbon、功能组、标题带和状态栏的高 DPI 深色模式样式。 |
| `tests/test_app_document_session.py` | 新增离屏 GUI 回归：核心页、动画/轨道上下文页、命令禁用规则与状态栏 Track 读数。 |

## 验证记录

| 检查 | 结果 |
|---|---|
| 离屏跨游戏 GUI 冒烟 | 通过。依次加载将军的荣耀 3（v4/WebP）、欧洲战争 6（v4/PNG/小数图集几何）、世界征服者 3（v3/PNG），并在 WC3 选择 `victory_2_2a@18` 的活动 Track。 |
| 视觉核验 | 通过。截图见 `research/gui_cross_game_wc3.png`；Ribbon 不遮挡预览、轨道检查器和时间线。 |
| 全量单元测试 | **48/48 通过**，耗时约 58 秒。新增一项 Ribbon GUI 回归测试，原有格式、跨游戏、保守编辑与取证测试保持通过。 |

## 依据与界面原则

本实现采用“WPS/CAD 式任务功能区 + Spine 式多视图动画工作区”的混合模型。Microsoft 将 Ribbon 设计为以效率和命令发现性替代分层菜单、工具栏与任务面板的界面组织方式；其上下文工具页仅应在当前对象适用时出现。[1] [2] Spine 的编辑器则说明，专业动画工作流需要画布、层级/树和时间线/曲线等多视图长期并置、可调。[3]

[1]: https://learn.microsoft.com/en-us/office/vba/library-reference/concepts/overview-of-the-office-fluent-ribbon "Microsoft — Overview of the Office Fluent ribbon"
[2]: https://learn.microsoft.com/en-us/windows/win32/windowsribbon/ribbon-contextualtabs "Microsoft — Displaying Contextual Tabs"
[3]: https://en.esotericsoftware.com/spine-ui "Spine User Guide — User interface"
