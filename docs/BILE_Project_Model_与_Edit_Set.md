# BILE Project Model / Edit Set v1

状态：WU-3 Project Model、WU-4 Overlay Compiler、WU-5 Canonical Validation 集成完成
日期：2026-11-05
模块：`bile_workbench.project_model`、`bile_workbench.overlay_compiler`、`bile_workbench.candidate_validation`

## 1. 目标与边界

Project Model 是 BILE 原始文件与后续编辑意图之间的独立工程层。它不等同于 BILE，也不负责重新序列化 BILE。

WU-3 建立工程模型与 Edit Set；WU-4 在其上增加候选编译器。当前能力：

- 从已有 BILE 创建 reference-only Project；
- 为 Section、定长记录和 BRTS 字符串建立稳定身份；
- 记录有序字段级 Edit Set；
- 验证源 SHA-256、目标记录身份、before/after 原始 bit pattern 与操作链；
- 通过 Overlay Compiler 按序重放操作，并将候选交给 Safe Mutation Engine 原子发布。
- 通过 Canonical Candidate Validation 独立重放 Edit Set，逐字节验证候选并输出离线验证报告。

Project Model 本身不生成 BIN；WU-4 编译器只生成独立候选 BIN，不触碰 UI，也不原位写回源文件。

## 2. Project 目录布局

```text
<project>/
  project.json
  assets/
    manifest.json
  motions/
    README.md
  metadata/
    record-identities.json
    edit-set.json
  raw/
    README.md
```

- `project.json`：项目身份、源文件引用、格式版本、能力边界和验证状态。
- `assets/manifest.json`：BIN/XML/纹理的外部路径、SHA-256、大小与角色。
- `metadata/record-identities.json`：Section Header 哈希、记录偏移、记录长度、记录 SHA-256、BRTS 字符串身份。
- `metadata/edit-set.json`：有序字段操作及 before/after 原始字节表示。
- `motions/`：保留给语义动作分组；当前不复制原始资源。
- `raw/`：只保存策略说明，不保存 BIN payload。

**Reference-only 是硬约束**：导入不复制 BIN、XML、WebP 或 PNG。Project 中只保存路径、哈希、记录身份和字段级变更值。

## 3. 来源类型与能力状态

持久化的 `originKind` 当前只允许：

| 类型 | 含义 |
|---|---|
| `ImportedOriginal` | 从已有原始 BILE 导入 |
| `SyntheticFixture` | 合成测试样本 |

`ImportedModified` 是校验报告根据已验证 Edit Set 推导出的项目状态，不写入 `originKind`。新建 BILE 不属于当前支持的来源类型，明确保持 NoGo。

v3/v4 的 writer capability 为 `Conditional`，但 Project Model 本身不写 BIN。v2 可以 reference-only 导入，writer capability 为 `NoGo`。

`project.json` 固定声明：

- `newBileGeneration = NoGo`
- `structuralEdits = NoGo`
- `playbackMode = NoGo`
- `compiler.writesBinary = true；必须同时满足 candidateOnly = true、inPlaceWrite = false`
- `originalGame = NotYetOriginalValidated`

## 4. 记录身份

每条定长记录的身份由以下字段组成：

- Section tag；
- 记录 index；
- 原始文件绝对 offset；
- record width；
- 原始记录 SHA-256；
- 派生 `recordId = TAG:index:sha256-prefix`。

每个 Section 还记录：

- 原始顺序、offset、total size、header width、count；
- 原始 Section Header SHA-256；
- 原始 payload SHA-256。

BRTS 字符串单独记录 offset、UTF-8 字节长度、字符串 SHA-256 和引用次数。身份文件不包含原始记录 payload。

Project 校验会从外部源 BIN 重新生成整份身份表并逐项比较；源文件漂移或身份文件被手工改写都会使 Project 失效。

## 5. Edit Set v1

每个操作都是 `SetField`，并按 sequence 顺序排列。操作最少包含：

- `operationId`、`sequence`；
- `target.section/index/recordId`；
- `field`；
- `storage.section/offset/width`；
- `before`、`after`；
- `beforeRawHex`、`afterRawHex`；
- `validationState` 和逐项校验标记。

浮点数按 float32 编码后保存原始 bit pattern；ARGB/initial_phase 按 u32；anchor 按两个 float32；name 按 UTF-8 字节序列。数值 JSON 只是可读视图，raw hex 才是 before/after 的精确比较依据。

### 当前字段白名单

| 目标记录 | field | 约束 |
|---|---|---|
| BELE | `transform.xx/xy/yx/yy/x/y` | 有限 float32 |
| BELE | `argb` | u32 / `0xAARRGGBB` |
| BELE | `initial_phase` | u32；具体子动画帧范围仍由 preflight 检查 |
| BMTI | `anchor` | 两个有限 float32 |
| BMTI | `name` | 等 UTF-8 字节长度，且 BRTS offset 只能被一个元素引用 |

禁止：

- `playback_mode`；
- 新增/删除/重排记录、帧、通道、轨道或字符串；
- 任何 Section Header、计数、未知字段或结构写入；
- BILE v2 写入；
- 新建 BILE。

### 顺序操作

同一字段允许存在多个操作，但必须形成明确链：

```text
source raw value
  -> operation 1 before/after
  -> operation 2 before/after
  -> ...
```

后一操作的 `beforeRawHex` 必须等于前一操作的 `afterRawHex`。不允许无变化空操作、跳过中间状态或伪造目标 recordId。

## 6. 校验流程

`validate_project()` 会验证：

1. Project/Asset Manifest/Edit Set schema；
2. 项目路径和目录边界；
3. 外部 BIN 普通文件身份、SHA-256、大小、版本和 FPS；
4. Asset Manifest 的 reference-only 声明；
5. 原始 Section/记录/字符串身份表；
6. Edit Set source hash 与 BILE 版本；
7. 每个目标 recordId；
8. 字段白名单、storage offset/width；
9. before/after 数值与 raw bit pattern；
10. 多操作 before/after 链；
11. 无结构性操作；
12. Project 内不存在复制的 BIN/XML/WebP/PNG。

可选 XML/纹理引用缺失或哈希变化会给出 warning；原始 BIN 哈希变化则直接使 Project 失效。

## 7. API

```python
from bile_workbench.project_model import (
    import_bile_project,
    append_edit_operation,
    validate_project,
)

report = import_bile_project("unit.bin", "unit-project")
append_edit_operation(
    "unit-project",
    section="BELE",
    index=0,
    field="transform.x",
    after=12.5,
)
report = validate_project("unit-project")
```

前三个 API 只创建/更新 Project metadata；候选 BIN 由独立的 `compile_project_candidate()` 创建，且必须输出到 Project 目录之外：

```python
from bile_workbench.overlay_compiler import compile_project_candidate

candidate = compile_project_candidate(
    "unit-project",
    "output/unit_candidate.bin",
)
```

原始 source BIN 永远不能作为 output path。编译报告自带内存候选的规范校验结果；候选发布后也可独立复核文件：

```python
from bile_workbench.candidate_validation import validate_project_candidate

validation = validate_project_candidate(
    "unit-project",
    "output/unit_candidate.bin",
)
print(validation.status)  # OfflineValid
```

`OfflineValid` 只表示离线结构和 Edit Set 一致性通过，不表示原游戏运行时通过。

## 8. 验证

`tests/test_project_model.py` 覆盖：

- reference-only 导入与可选资产引用；
- 记录身份哈希；
- BELE/BMTI 字段操作；
- repeated operation 链；
- v2 只读；
- 共享 BRTS 字符串拒绝；
- 结构/playback_mode 拒绝；
- no-op/长度变化拒绝；
- source drift、身份文件和 Edit Set 篡改检测；
- Project 目录拒绝覆盖；
- SyntheticFixture 来源类型。
- 候选文件独立重放、完整字节比对、changed-byte set 与漂移检测见 `tests/test_candidate_validation.py`。

WU-4 已消费此 Edit Set：逐操作核对 beforeRaw、应用 afterRaw、验证每个中间 BILE，并从最终 overlay 独立计算 changed-byte union。WU-5 的 Canonical Candidate Validation 会再次独立重放 Edit Set，并要求已发布候选与预期完整字节镜像完全一致；它同时复核源身份、Project metadata、Section 布局、候选文件稳定性。离线通过不等于原游戏运行时通过。
