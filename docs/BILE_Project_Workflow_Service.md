# BILE Project Workflow Service

状态：WU-6 核心实现
模块：`bile_workbench.project_workflow`
日期：2026-11-05

## 1. 目标与边界

Project Workflow Service 把 reference-only Project、Edit Set、Overlay Compiler 和 Canonical Candidate Validation 组合成一个可独立测试的领域服务。它不依赖 Qt，也不负责弹窗、路径选择或状态栏。

它不替代现有 `EditSession` 的预览、撤销/重做和编辑命令栈；旧编辑器通过一个明确的一次性适配器，把当前会话最终值映射为字段级 Edit Set。

## 2. 基本用法

### 导入与检查

```python
from bile_workbench.project_workflow import ProjectWorkflowService

service = ProjectWorkflowService.import_source(
    "assets/unit.bin",
    "projects/unit-project",
    xml_path="assets/unit.xml",
    texture_path="assets/unit.webp",
)

snapshot = service.inspect()
print(snapshot.status, snapshot.project_kind, snapshot.operation_count)
print(snapshot.candidate.status)  # NotConfigured
```

### 字段编辑、编译与验证

```python
operation = service.append_edit(
    section="BELE",
    index=0,
    field="transform.x",
    after=12.5,
)

build = service.compile_candidate("output/unit_candidate.bin")
print(build.validation.status)  # OfflineValid
print(build.snapshot.candidate.status)  # Current
```

编译默认不覆盖既有候选。若用户明确选择覆盖，必须传入 `overwrite=True`。

### 候选失效与重编译

```python
service.append_edit(
    section="BELE",
    index=0,
    field="transform.x",
    after=14.25,
)

snapshot = service.inspect()
print(snapshot.candidate.status)  # Stale

build = service.compile_candidate(
    "output/unit_candidate.bin",
    overwrite=True,
)
print(build.snapshot.candidate.status)  # Current
```

旧候选不会因 Edit Set 更新而被静默删除；它会被标记为 `Stale`。重新编译必须明确允许覆盖。

## 3. 候选状态

| 状态 | 含义 |
|---|---|
| `NotConfigured` | 尚未指定候选路径 |
| `Missing` | 已指定路径，但候选文件不存在 |
| `Current` | 追踪清单与当前 Project/Edit Set 匹配，且规范离线验证通过 |
| `CurrentUntracked` | 候选通过规范离线验证，但没有追踪清单 |
| `Stale` | 候选追踪清单对应旧 Project/source/Edit Set，需要重新编译 |
| `Invalid` | 候选、追踪清单、路径或规范验证不可信 |

追踪清单与候选 BIN 放在同一目录，命名为 `<candidate>.bile-workbench.json`。它记录 Project ID、source SHA-256、Edit Set SHA-256、候选 SHA-256/大小和离线验证范围。

追踪清单只是候选新鲜度索引，不是可信验证凭证。每次 `inspect()` 对匹配的候选仍会重新执行 Canonical Candidate Validation；清单缺失时也会直接验证候选，成功则标记为 `CurrentUntracked`。清单被篡改、候选哈希不符或规范校验失败都会标记 `Invalid`。

## 4. 旧 EditSession 适配

`apply_edit_session(session)` 只允许写入空 Edit Set，并要求 Project 与 EditSession 绑定到同一路径、同一 source SHA-256。

它会把会话最终状态映射为：
- BELE：`transform.xx/xy/yx/yy/x/y`、`argb`、`initial_phase`；
- BMTI：`anchor`。

只导入相对原始 source 真正发生字节变化的字段；字段按稳定顺序生成操作。Undo/Redo 的中间步骤不会被误写成 Project 操作。空会话、no-op、错源或非空 Project 均拒绝。

## 5. CandidateWorkflow 迁移

现有 `CandidateWorkflow.compile_project_candidate()` 会：
1. 执行原有 preflight；
2. 创建临时 reference-only Project；
3. 将当前 EditSession 映射为 Edit Set；
4. 调用 Overlay Compiler；
5. 在发布后执行 Canonical Candidate Validation；
6. 返回候选哈希、changed-byte offsets 和离线验证报告。

候选差异、实验包和回归案例均已改用这条管线。文档预览仍使用 `EditSession` 的临时候选，以避免把 Project 编译引入每次控件交互。

## 6. 明确不做的事

- 不修改原始 BIN/XML/纹理。
- 不把临时 Project 误报为用户保存的长期 Project。
- 不把 `OfflineValid` 说成游戏内验证通过。
- 不自动删除 stale candidate；覆盖需要显式确认。
- 本轮不接入 Qt 菜单和对话框；桌面 UI 接入属于下一阶段。
