# 文档索引

本目录按使用任务组织。README 是项目首页；本页是技术文档导航。格式研究、编辑契约、桌面操作和历史增量说明分开维护，避免把“能解析”“能编辑”“离线验证通过”和“游戏内验收通过”混成一个状态。

## 先从这里开始

| 你要做什么 | 建议阅读 |
|---|---|
| 下载、安装和启动 | [项目首页](../README.md) |
| 第一次打开动画三件套 | [BILE 格式技术说明](BILE_动画格式技术说明.md)、[工作台直接编辑与回归](工作台直接编辑与回归.md) |
| 创建工程并组织修改 | [Project Model 与 Edit Set](BILE_Project_Model_与_Edit_Set.md)、[Project UI 工作流](BILE_Project_UI_Workflow.md) |
| 编译和验证候选 BIN | [安全写入与事务契约](BILE_安全写入与事务契约.md)、[Overlay Compiler](BILE_Overlay_Compiler.md)、[Canonical Candidate Validation](BILE_Canonical_Candidate_Validation.md) |
| 理解动画轨道影响 | [专业轨道编辑与取证指南](专业轨道编辑与取证指南.md)、[动画瑞士军刀能力地图](动画瑞士军刀能力地图.md) |
| 使用 AI 辅助提案 | [AI 动画中转格式](AI_动画中转格式使用说明.md)、[AI Motion DSL 只读提案契约](AI_Motion_DSL_只读提案契约_v1.md) |
| 使用场景提案接口 | [BILE Scene Interchange](BILE_Scene_Interchange_v1_只读场景契约.md)、[BILE Scene AI 安全提案契约](BILE_Scene_AI_安全提案契约_v1.md) |
| 安装或制作主题 | [主题插件开发与安装](主题插件开发与安装.md)、[插件目录说明](../plugins/README.md) |

## BILE 格式与编辑边界

| 文档 | 内容 |
|---|---|
| [BILE 动画格式技术说明](BILE_动画格式技术说明.md) | v2/v3/v4 容器布局、记录结构、时间线消费、XML/图集兼容和证据等级。 |
| [跨代资源格式边界报告](跨代资源格式边界报告.md) | 不同代际资源格式的已验证差异、兼容边界和未知项。 |
| [跨游戏 BILE 兼容性报告](跨游戏BILE兼容性报告.md) | 各游戏样本的解析覆盖、版本差异与不可直接外推的兼容结论。 |
| [跨游戏兵模组合实验指南](跨游戏兵模组合实验指南.md) | 区分 BILE 根动画内部组合与游戏上层实例化的受控实验方法。 |
| [工作台直接编辑与回归](工作台直接编辑与回归.md) | 检查器编辑、撤销/重做、候选差异和回归流程。 |
| [专业轨道编辑与取证](专业轨道编辑与取证指南.md) | Track/BELE 上下文、静态影响范围和游戏内证据闭环。 |
| [动画序列导出与游戏内验证](动画序列导出与游戏内验证.md) | GIF/APNG/PNG 序列、候选回读和游戏内实验记录。 |
| [候选差异与游戏内回归](候选差异与游戏内回归.md) | 字段/像素差异、热区图和持久回归案例。 |

## 工程模型与候选流水线

| 文档 | 内容 |
|---|---|
| [Project Model 与 Edit Set](BILE_Project_Model_与_Edit_Set.md) | Reference-only 工程、外部资源身份、有序字段操作和状态模型。 |
| [Project Workflow Service](BILE_Project_Workflow_Service.md) | 工程生命周期、编辑会话适配、候选追踪和服务 API。 |
| [Project UI Workflow](BILE_Project_UI_Workflow.md) | 桌面端创建/打开/同步工程、编译候选、规范验证和操作历史。 |
| [Existing-BILE Overlay Compiler](BILE_Overlay_Compiler.md) | 按序重放 Edit Set、中间验证、changed-byte union 和原子候选发布。 |
| [Canonical Candidate Validation](BILE_Canonical_Candidate_Validation.md) | 独立重放、逐字节核对、源身份与文件稳定性检查。 |
| [安全写入与事务契约](BILE_安全写入与事务契约.md) | expected-old、源哈希、精确变更字节集合、原子发布与失败处理。 |

## AI、场景和互操作

| 文档 | 内容 |
|---|---|
| [AI 动画中转格式使用说明](AI_动画中转格式使用说明.md) | 完整 JSON 导出、受限补丁、字段白名单和应用前校验。 |
| [AI Motion DSL 只读提案契约](AI_Motion_DSL_只读提案契约_v1.md) | 面向 AI 的只读动作提案结构；提案不直接获得写回权限。 |
| [BILE Scene Interchange v1](BILE_Scene_Interchange_v1_只读场景契约.md) | 场景结构交换的只读契约。 |
| [BILE Scene AI 安全提案契约](BILE_Scene_AI_安全提案契约_v1.md) | AI 场景提案输入、约束和安全边界。 |

## Spine 只读工作区

| 文档 | 内容 |
|---|---|
| [Spine 新引擎静态工作区技术说明](Spine_新引擎静态工作区技术说明.md) | Spine 3.8/4.1 静态结构、ATLAS 读取与未解码边界。 |
| [Spine pose 只读精度增量（历史记录）](Spine_pose_只读精度增量_20260822.md) | 2026-08-22 阶段性精度与样本回归记录；不是当前功能承诺。 |

Spine 文档描述的是按版本限定的只读读取、结构审阅或预览能力。除非后续文档明确记录读写闭环，不应将其称为通用 Spine 动画编辑器。

## 主题与界面

| 文档 | 内容 |
|---|---|
| [主题插件开发与安装](主题插件开发与安装.md) | plugin.json、QSS、主题资源、导入方式和安全边界。 |
| [动画瑞士军刀能力地图](动画瑞士军刀能力地图.md) | 专业工作台能力分层和能力边界。 |

## 来源、许可和历史记录

| 文档 | 内容 |
|---|---|
| [迁移来源与权属审计](迁移来源与权属审计.md) | 迁移来源、代码/文档权属和第三方材料边界。 |
| [项目交付包说明（历史）](../DELIVERY_PACKAGE_20260822.md) | 2026-08-22 交付包的内容与排除项记录。 |
| [Ribbon 界面增量（历史）](../RIBBON_INTERFACE_INCREMENT.md) | 早期界面重组的设计与当时测试记录。 |
| [专业瑞士军刀深化增量（历史）](../SWISS_ARMY_INCREMENT.md) | 早期专业取证能力增量记录。 |
| [跨格式时间线增量（历史）](../SWISS_KNIFE_TIMELINE_INCREMENT.md) | 早期 BILE/Spine 时间线读取能力增量记录。 |

历史增量文档中的测试数字、界面描述和“下一步”仅代表当时快照。当前能力应以源码、当前测试、README 和具体技术契约为准。

## 证据状态约定

- **Confirmed / 已确认：** 有可复现的样本、代码路径、测试或明确机器证据支撑；必须注明适用版本与范围。
- **Strong hypothesis / 强推断：** 有多项间接证据支持，但关键语义尚未通过针对性实验确认。
- **Unknown / 未知：** 证据不足，不能据此实现或承诺兼容。
- **NotRun / 未运行：** 尚未执行对应验证。
- **Skip / 跳过：** 测试因缺少私有素材、环境或前置条件而未执行，不计入通过数。
- **Offline validated / 离线验证通过：** 解析、候选或像素结果通过离线检查，不代表游戏运行时接受。
- **Desktop accepted / 桌面验收通过：** 真实桌面启动和交互已由人工记录。
- **Game accepted / 游戏内验收通过：** 指定游戏版本、资源和场景的运行时行为已由独立证据支持。

任何一份报告都应明确写出结论的游戏版本、样本范围、验证方式和未覆盖事项。
