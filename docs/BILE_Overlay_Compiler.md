# BILE Existing-BILE Overlay Compiler

状态：WU-4 Overlay Compiler 与 WU-5 Canonical Validation 集成完成
日期：2026-11-05
模块：`bile_workbench.overlay_compiler`

## 1. 编译边界

Overlay Compiler 消费 WU-3 Project Model 的有序 Edit Set。它只为已有 BILE v3/v4 生成独立候选文件：

- 不新建 BILE；
- 不增删/重排记录、帧、通道、轨道或 Section；
- 不写 playback_mode、未知字段或 Section Header；
- 不覆盖原始 source BIN；
- 不把候选 BIN 放回 Project 目录；
- 不把编译成功等同于原游戏运行时通过。

v2 可以 reference-only 导入，但没有候选编译能力。

## 2. 顺序叠加

每个操作都带有 target record identity、storage offset/width、beforeRawHex 和 afterRawHex。编译器按 sequence 重放：

1. 完整验证 Project、外部源 SHA-256、记录身份和 Edit Set。
2. 重新读取原始 BIN，并绑定 Project 的 source SHA-256。
3. 为每个操作检查当前内存 overlay 的字段字节必须等于 beforeRawHex。
4. 只在固定 offset/width 上应用 afterRawHex。
5. 对每个中间 overlay 执行完整 BILE 重解析、Section 布局检查、字符串池边界检查和字段白名单检查。
6. 计算最终字节映射，而不是简单累加“曾经改过”的偏移。
7. 再次验证 Project metadata 未漂移。
8. 将最终候选交给 Canonical Candidate Validation 独立重放并做完整字节比较。
9. 再次确认 Project metadata 未漂移，将最终候选交给 Safe Mutation Engine 原子发布。

同一字段的连续操作必须严格衔接：

```text
source 10.0
  -> op-000001: 10.0 => 12.5
  -> op-000002: 12.5 => 14.25
final 14.25
```

如果后续操作将字段恢复到原始值，该字段不会进入最终 changed-byte set。若所有操作最终都恢复原样，则拒绝生成空候选。

## 3. 最终 changed-byte union

编译器维护每个被触及字节的最终值：

- 同一字节被多次覆盖时，只保留最后一次结果；
- 最终值等于源字节时，从 changed-byte set 中排除；
- 最终值不同于源字节时，加入 changed-byte set；
- 最终集合按绝对文件 offset 排序；
- 最终集合必须与 Safe Mutation Engine 重新计算的实际变化集合完全一致。

因此它不是“操作触及过哪些字节”的历史集合，而是最终候选相对原始 BIN 的精确差异集合。

## 4. 回滚与发布

### 编译阶段失败

所有操作都只作用于内存中的 `BileMutationBuffer`。任一 beforeRaw 不匹配、中间重解析失败、Project metadata 漂移或最终字节集合不一致，都会丢弃内存 overlay，不调用发布函数。

已有候选文件在此阶段不会被触碰。

### 发布阶段失败

发布复用 `publish_verified_candidate()`：

- 默认拒绝覆盖已有目标；
- 显式 `overwrite=True` 才允许替换已有候选；
- 同目录暂存、回读、SHA-256 和完整解析验证；
- 发布前再次检查源 BIN 未漂移；
- 覆盖时先准备并校验旧候选备份；
- 发布后验证失败时尝试恢复旧候选；
- 无法恢复时保留备份并报告精确路径。

源 BIN 永远不能作为 output path；输出路径也必须位于 Project 目录之外。

## 5. API

```python
from bile_workbench.overlay_compiler import compile_project_candidate

report = compile_project_candidate(
    "unit-project",
    "output/unit_candidate.bin",
)
print(report.output_sha256)
print(report.changed_byte_offsets)
print(report.canonical_validation.status)  # OfflineValid
```

显式覆盖已有候选：

```python
report = compile_project_candidate(
    "unit-project",
    "output/unit_candidate.bin",
    overwrite=True,
)
```

`overwrite=True` 只表示允许替换目标候选文件，不会放宽 source/output 必须不同的约束。

## 6. 回归覆盖

`tests/test_overlay_compiler.py` 覆盖：

- 多字段组合编译；
- 同字段连续操作；
- 最终 changed-byte union 排除已恢复字节；
- 全部恢复时拒绝空候选；
- 中间 replay 失败时丢弃 overlay 并保留旧候选；
- Project metadata 编译期间漂移检测；
- source SHA 漂移检测；
- Edit Set 篡改检测；
- 候选不得写入 Project 目录；
- 已有输出必须显式确认覆盖；
- v2 严格 NoGo。

本轮只证明合成 BILE 样本上的编译与规范校验合同。真实跨游戏资源仍需离线样本回归与原游戏内验证；不能把候选文件生成成功或 OfflineValid 标记为运行时验证通过。
