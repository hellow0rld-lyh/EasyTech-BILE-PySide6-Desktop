# BILE Workbench

开发者：**3136818780**  
许可证：[MIT](LICENSE)

**BILE Workbench** 是针对 EasyTech 风格动画三件套的 Windows/Python/PySide6 工作台。它围绕同名 `.bin + .xml + .webp` 资源提供结构校验、动画预览、播放、时间线可视化、格式审计，以及面向 AI 的受限 JSON 中转补丁。

> 当前版本的核心价值是：把原本不透明的 BILE BIN 转换为可完整解析、可离线预览、可回归测试、可安全提案编辑的资源格式。任何涉及增删元素、增删帧或游戏内发布的修改，仍应以原游戏运行时测试为准。

| 能力 | 状态 | 说明 |
|---|---|---|
| BILE 容器解析 | 完成 | 严格验证 v3/v4 六节与将1 v2 五节容器、定长记录、UTF-8 BRTS、引用与全量时间线消费；v2 当前严格只读。 |
| XML/WebP 图集读取 | 完成 | 支持原包使用的多顶层 XML 片段、UTF-8 名称、WebP/PNG 图集；外部 XML 统一经 `defusedxml` 适配层拒绝 DTD、实体和外部引用。 |
| 动画预览与播放 | 完成 | 支持嵌套元素、保持帧、BELE 仿射变换、ARGB 调制、`refx/refy` 图集参考点和 `reference_v4` 嵌套时钟；可导出 GIF、APNG、PNG 帧序列。 |
| 浅色/深色高 DPI UI | 完成 | PySide6/Fusion 宿主基础主题、浮点 DPI 策略、可停靠资源树/检查器/时间线；支持外部 QSS 主题插件叠加。 |
| 外部主题插件 | 完成 | 支持 plugin.json 文件夹插件与 .bileplugin/.zip 插件；内置二次元 ClaudeAI 少女、OpenAI 少女两套独立浅色/深色预设。 |
| 直接动画编辑 | 完成 | 检查器内编辑 BELE 仿射矩阵/Alpha/`initial_phase` 与 BMTI 精灵锚点；每次编辑均临时重解析。 |
| 编辑历史与视觉回归 | 完成 | 撤销/重做、待提交补丁导出、原始/暂存当前槽位对比 PNG；导出前检查源哈希、重解析、图循环及 initial_phase 子动画帧范围；可生成含候选三件套与回读报告的游戏内实验 ZIP。 |
| 跨游戏 BILE v2/v3/v4 | 完成 | 将军的荣耀1 v2（12 个五节样本，只读）、世界征服者3/欧洲战争4 v3、将军的荣耀3/欧洲战争6/世界征服者4 v4 严格解析通过；v3/v4 共享六块容器，v2 使用经实测的五节合并时间线。 |
| 根动画组合画像 | 完成 | 诊断直接精灵根动作与并发嵌套子动画根动作；已实证将3单兵根与世4三人组合根的结构差异，且明确不把该指标误报为游戏格子人数。 |
| PNG/WebP 与 XML 兼容 | 完成 | 同名 PNG/WebP、XML 声明、多顶层片段、尾随控制填充和小数图集几何均可只读加载并显式诊断。 |
| 资源诊断 | 完成 | 动画引用图循环、播放模式、空轨道、图集缺图、参考点与跨游戏 BILE/XML 图集兼容性画像；可生成原始/候选逐槽位字段与像素热区差异报告。 |
| 动画编辑中转 | 完成 | 导出完整 JSON；新补丁携带 expected-old 值；候选 BIN 经源 SHA-256、精确 changed-byte set、完整重解析和事务式原子发布；旧版补丁仍兼容。 |
| Project Model / Edit Set | 核心完成 | reference-only 导入；project.json、外部资产引用、记录身份哈希与有序 before/after 字段操作；不复制原始资源、不编译 BIN。 |
| Existing-BILE Overlay Compiler | 核心完成 | 按序重放 Edit Set；每步校验中间 BILE；计算最终 changed-byte union；只原子发布独立候选，源 BIN 永不原位写回。 |
| Canonical Candidate Validation | 核心完成 | 独立重放 Edit Set 并逐字节比对候选；核验源身份、完整解析、Section 布局、changed-byte set 与验证期间文件稳定性；明确离线验证不等于游戏内通过。 |
| BILE 完整结构重建 | 实验性/未开放 | 新建元素、增删帧和重排字符串需要更多游戏内回归。 |
| 第一轮架构重构 | 完成 | 三件套资产、候选编辑工作流、工作区状态、预览/时间线控件和实验对话框已分层；`app.py` 从 1,072 行缩减至 849 行，解析与渲染语义保持冻结。 |
| 文档驱动编辑器 | 完成 | `AnimationDocumentSession` 统一基线三件套、暂存显示文档、选择和槽位；检查器以保守编辑命令驱动，专用动画导航、画布、时间线、诊断和状态条共享快照。 |
| 专业轨道编辑与取证 | 完成 | 以动画根→通道→保持段→Track→BELE→目标元素的可验证上下文驱动选择；可导出当前暂存 BELE 的静态轨道影响范围，并与候选差异、实验包和游戏内证据结合。 |

## 快速开始

在 Windows 的 PowerShell 中执行：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
bile-workbench
```

也可以直接从源码运行：

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m bile_workbench.app
```

打开一个 `.bin` 后，程序会在同一目录查找同名 `.xml` 与 `.webp`，找不到 WebP 时再尝试 `.png`。建议把三件套放在同一目录，且首次修改时始终另存为实验文件。项目根目录 `plugins/` 会自动扫描主题插件；也可以从“视图 → 主题”导入插件文件或文件夹。插件清单、浅色/深色 QSS 和可选头像资源的格式见 [`docs/主题插件开发与安装.md`](docs/主题插件开发与安装.md)。

## Windows 打包

安装依赖后执行：

```powershell
.\packaging\build_windows.ps1
```

产物会输出到 `dist\BILEWorkbench\BILEWorkbench.exe`。该脚本必须在 Windows 上执行，以生成目标平台可用的 Qt 插件和可执行文件。

## 验证

```powershell
python -m unittest discover -s tests -v
python tools\test_bile_parser.py
python tools\validate_triplets.py
python tools\render_regression.py
```

部分回归测试引用未随公开源码包分发的原游戏样本、跨游戏数据集和预打包主题文件；缺少这些外部夹具时，相关测试会失败或跳过，这不表示仓库包含这些素材。公开仓库可直接运行不依赖外部素材的解析安全、几何、命名和工作流单元测试。历史开发环境曾对 11 组 `anim_*` 样本执行完整解析和非空预览验证；这些结果仅作为历史记录，不随 MIT 源码重新分发原始素材。

## 文档

| 文档 | 内容 |
|---|---|
| [`docs/BILE_动画格式技术说明.md`](docs/BILE_动画格式技术说明.md) | 可用于社区发布的格式规范、证据等级、字段表、时间线算法与风险边界。 |
| [`docs/AI_动画中转格式使用说明.md`](docs/AI_动画中转格式使用说明.md) | AI JSON 中转、补丁白名单、提示词模板与校验流程。 |
| [`docs/BILE_安全写入与事务契约.md`](docs/BILE_安全写入与事务契约.md) | 原始字节镜像、expected-old、changed-byte set、候选原子发布与失败回滚。 |
| [`docs/BILE_Project_Model_与_Edit_Set.md`](docs/BILE_Project_Model_与_Edit_Set.md) | reference-only 工程结构、记录身份、字段级 Edit Set、校验状态与编译边界。 |
| [`docs/BILE_Overlay_Compiler.md`](docs/BILE_Overlay_Compiler.md) | Edit Set 顺序叠加、中间状态校验、最终 changed-byte union、原子候选发布与失败回滚。 |
| [`docs/BILE_Canonical_Candidate_Validation.md`](docs/BILE_Canonical_Candidate_Validation.md) | 独立重放 Edit Set、候选完整字节比对、源/Project 稳定性与离线验证报告。 |
| [`docs/迁移来源与权属审计.md`](docs/迁移来源与权属审计.md) | Reconstruction Animation Studio 成果的精确来源、哈希、迁移边界与许可证审计。 |
| [`docs/工作台直接编辑与回归.md`](docs/工作台直接编辑与回归.md) | 关键帧/锚点直接编辑、撤销重做、比较图与安全导出流程。 |
| [`docs/动画序列导出与游戏内验证.md`](docs/动画序列导出与游戏内验证.md) | GIF/APNG/PNG 序列导出、候选 BIN 回读验证、游戏内实验 ZIP 和人工回归流程。 |
| [`docs/主题插件开发与安装.md`](docs/主题插件开发与安装.md) | 外部主题插件协议、文件夹/压缩包结构、QSS 双模式、导入和安全边界。 |
| [`docs/候选差异与游戏内回归.md`](docs/候选差异与游戏内回归.md) | 候选字段/像素差异、热区图、持久回归案例、截图/录屏证据和游戏内结论状态。 |
| [`docs/跨游戏BILE兼容性报告.md`](docs/跨游戏BILE兼容性报告.md) | 将军的荣耀3、欧洲战争6、世界征服者3与世界征服者4的 BILE v3/v4、XML、PNG/WebP 跨游戏实证边界。 |
| [`research/cross_game_unit_count_hypothesis.md`](research/cross_game_unit_count_hypothesis.md) | 将3单兵根动作与世4三人组合根动作的离线证据、上层实例化边界与游戏内可证伪实验矩阵。 |
| [`research/bile_v2_candidate_constraint_check.md`](research/bile_v2_candidate_constraint_check.md) | 将军的荣耀1 BILE v2 五节容器的 12 样本结构约束与只读解析证据。 |
| [`docs/跨游戏兵模组合实验指南.md`](docs/跨游戏兵模组合实验指南.md) | 当前目标三件套与候选根动作的单变量实验包、可选 `def_array` 快照、手工 Motion 绑定配方与基线—处理组证据回归流程。 |
| [`research/third_party_format_claims_and_validation.md`](research/third_party_format_claims_and_validation.md) | 外部资料的逐条核验台账。 |
| [`research/reference_viewer_audit.md`](research/reference_viewer_audit.md) | 用户提供的私下查看器源码的静态审计、原包交叉验证与采纳边界；不重分发参考源码。 |
| [`research/initial_phase_effect_probe.md`](research/initial_phase_effect_probe.md) | 使用 `anim_status` 真实嵌套轨道验证 initial_phase 的画面影响，含对比图。 |
| [`research/playback_mode_experiment_matrix.md`](research/playback_mode_experiment_matrix.md) | 原包播放模式实验；新增跨游戏数据已在 `cross_game_bile_version_compare.md` 中确认嵌套 mode 1 的结构性使用，但仍缺游戏内运行时扰动验证。 |
| [`research/nested_field_usage_audit.md`](research/nested_field_usage_audit.md) | 按静态精灵/子动画目标类型拆分的播放字段分布审计。 |
| [`research/refactor_results.md`](research/refactor_results.md) | 第一轮重构的前后指标、稳定接口、模块边界、34 项回归与有意延后的解析/渲染重构。 |
| [`research/refactor_migration_plan.md`](research/refactor_migration_plan.md) | 重构前审计、迁移顺序和禁止混入格式语义变更的维护计划。 |
| [`research/third_party_dependency_research.md`](research/third_party_dependency_research.md) | 第三方库审计、defusedxml 选型依据、许可/兼容性结论与未采纳库的边界。 |
| [`research/commercial_animation_editor_architecture_mapping.md`](research/commercial_animation_editor_architecture_mapping.md) | Spine/Unity 公开工作流模式的边界化借鉴，以及 BILE 文档中心、命令栈和多视图协同映射。 |
| [`research/document_session_architecture.md`](research/document_session_architecture.md) | 文档会话、选择快照、保守编辑命令、订阅通知与候选工作流的实现合同。 |
| [`research/document_editor_visual_verification.md`](research/document_editor_visual_verification.md) | 文档状态条、动画导航、画布、时间线和诊断面板的跨游戏离屏视觉核验。 |
| [`docs/专业轨道编辑与取证指南.md`](docs/专业轨道编辑与取证指南.md) | 面向专业逆向与精细编辑的瑞士军刀定位、轨道上下文、局部影响范围证据与游戏内回归流程。 |
| [`research/professional_track_editing_mapping.md`](research/professional_track_editing_mapping.md) | 轨道级工作流的商业编辑器模式映射，以及 BILE 不支持连续曲线/重排关键帧的实证边界。 |
| [`research/professional_track_editor_visual_verification.md`](research/professional_track_editor_visual_verification.md) | 真实活动 Track 被选中后，轨道表、时间线通道高亮与 BELE 上下文的跨游戏视觉核验。 |

## 许可证与发布前提示

本仓库以 MIT 许可证发布，只包含解析器、工作台代码、研究文档和项目自带界面资源，不包含原始游戏资源。EasyTech、Spine、Claude 和 OpenAI 等名称及商标归各自权利人所有；本项目是非官方社区工具，与这些公司或项目不存在隶属或背书关系。发布或分发原始游戏资源、修改后的资源和截图前，请自行确认相应授权范围。
