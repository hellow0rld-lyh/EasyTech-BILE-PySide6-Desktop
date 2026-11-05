# BILE Project UI Workflow

状态：WU-7 桌面接入
模块：bile_workbench.project_workflow、bile_workbench.app.MainWindow
日期：2026-11-05

## 1. 设计边界

桌面 UI 只负责路径选择、确认、状态展示和报告呈现。Project 生命周期、Edit Set 同步、候选编译和规范验证全部委托给 ProjectWorkflowService。

Project 是 reference-only 工程：原始 BIN/XML/纹理仍在外部原路径，Project 只保存引用、身份、哈希和 Edit Set。任何候选都输出为独立 BIN，不原位覆盖 source。

## 2. 创建 Project

1. 先通过“文件 → 打开 BILE”加载目标 BIN 与同名 XML、WebP/PNG。
2. 确认当前资源为 BILE v3/v4。
3. 选择“工程 → 从当前 BILE 新建 Project”。
4. 选择保存父目录。程序创建 <BIN 名称>.bileproj；若目录已存在，拒绝覆盖。
5. 当前已有暂存编辑会在创建后同步到新 Project。

Project 创建不会复制源资源，也不会写回源 BIN。

## 3. 打开 Project

选择“工程 → 打开 Project”，即使当前尚未打开任何 BILE 资源也可以执行。程序读取 Project 绑定的原始 BIN 路径，并按 Workbench 约定查找同目录、同名 XML 与 WebP/PNG 图集，先加载 source 工作区，再恢复 Edit Set。

如果当前已打开另一份 BILE，程序会先处理当前 Project 的未同步编辑；若当前没有 Project 但存在暂存编辑，则要求明确确认是否放弃。Project 的 source BIN 必须存在，且资源三件套必须成功加载。程序不会仅凭文件名把另一份资源当成匹配源；恢复前还会在临时 EditSession 中核对 source SHA-256 和字段身份。

如果当前编辑会话已有暂存修改，程序会先要求确认替换。恢复后，Project 的最终字段值会进入当前预览、检查器和时间线。Project 原始 Edit Set 不会被重写。

重新加载当前 source 或切换到其他 BILE 时，如果编辑会话指纹与最近一次 Project 同步快照不同，程序会要求先同步到当前 Project；选择取消会保留当前文档和编辑会话。同步成功后才允许切换，切换到不同 source 时再解除旧 Project 绑定。

## 4. 同步编辑

在“工程 → 同步暂存编辑到 Project”中保存当前编辑状态。

同步支持：
- 第一次导入当前会话的字段修改；
- 对同一字段继续追加新的 before/after 操作；
- 重复同步保持幂等，不生成重复操作；
- 撤销至原始值时，追加一个显式恢复操作，而不是删除历史；
- 多字段同步先在临时 Project 副本中完整验证，再以单文件原子替换提交 Edit Set；中途失败不会留下半份操作链。

主界面 Project 状态行会显示 Project ID、Edit Set 操作数、候选状态，以及当前暂存状态是否已同步。

## 5. 候选 BIN

### 设置路径

选择“工程 → 设置候选 BIN 路径”。候选必须位于 Project 目录之外，且不能与原始 source BIN 指向同一文件。

候选路径当前属于桌面会话状态；重新打开 Project 后需要重新选择输出路径。

### 编译

选择“工程 → 编译 Project 候选 BIN”：
1. 执行现有动画编辑预检；
2. 将当前暂存编辑同步到 Project；
3. 使用 Existing-BILE Overlay Compiler 编译独立候选；
4. 执行 Canonical Candidate Validation；
5. 写入候选追踪清单并刷新状态。

候选文件已经存在时，程序会要求显式确认原子替换。拒绝确认不会覆盖文件。Project 的 Edit Set 更新不会自动删除旧候选；旧候选会显示为 Stale。

### 验证

“工程 → 验证 Project 候选 BIN”会对当前候选重新执行规范离线验证并登记追踪清单。

如果当前编辑会话尚未同步、候选已过期、候选无效或路径未配置，程序会停止并提示下一步，不会把旧候选标成当前候选。

## 6. 操作历史

“工程 → 查看 Project 操作历史”显示 Edit Set 中最近 100 项操作，包括 sequence、Section/记录索引、字段和 before/after 值。

历史只读；撤销/重做仍由当前 AnimationDocumentSession 负责。同步时把最终状态转换为追加操作，不把 Undo/Redo 中间过程伪装成工程历史。

## 7. 验证语义

- Current：候选与当前 Project/Edit Set 匹配，且规范离线验证通过。
- CurrentUntracked：候选内容匹配并通过验证，但尚无追踪清单。
- Stale：候选对应旧 source 或旧 Edit Set。
- Invalid：候选、追踪清单或路径不可信。
- OfflineValid：完整结构和 Edit Set 字节一致性通过；不代表原游戏已接受该候选。
- original_game_validation = NotPerformed：必须在目标游戏内另行测试。

## 8. 当前限制

- 打开 Project 会根据其 source BIN 路径自动加载同目录同名 XML 与 WebP/PNG；当前仍不支持 Project 内自定义资产路径映射。
- 候选输出路径尚未持久化到 Project，重开工程后需重新设置。
- 本轮不增加结构性编辑能力；BILE v2 仍只读。
- 当前桌面 EditSession 恢复/同步范围为 BELE transform、ARGB、initial_phase 与 BMTI anchor。Project 含有桌面暂不支持的字段（例如 BMTI.name）时，打开恢复会明确拒绝，不会静默显示不完整预览。
- 桌面 UI 的运行时测试需要安装项目声明的 PySide6。若测试环境缺少 PySide6，只能完成 Python 编译与 Qt-free 工作流回归，不能据此宣称已完成实际窗口交互验收。
