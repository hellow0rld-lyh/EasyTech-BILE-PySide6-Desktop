# BILE Canonical Candidate Validation

状态：WU-5 核心实现完成
日期：2026-11-05
模块：`bile_workbench.candidate_validation`

## 1. 目标

Canonical Candidate Validation 是 Project Model、Edit Set 和 Overlay Compiler 之后的独立验证门。它不信任编译器报告，也不以“候选能被解析”作为充分条件。

唯一的候选正确性标准是：

> 候选 BIN 必须与当前 Project 所绑定的原始 source BIN 按 Edit Set 顺序独立重放后得到的完整字节镜像完全一致。

任何额外字节、缺失字节、错误字段值、旧候选、错源候选或 metadata 漂移都会导致验证失败。

## 2. API

### 验证已发布候选

```python
from bile_workbench.candidate_validation import validate_project_candidate

report = validate_project_candidate(
    "unit-project",
    "output/unit_candidate.bin",
)
print(report.status)
print(report.to_dict())
```

### 在内存中验证候选

Overlay Compiler 在写盘前使用同一套规范校验：

```python
from bile_workbench.candidate_validation import validate_candidate_bytes

report = validate_candidate_bytes(
    "unit-project",
    candidate_bytes,
    candidate_path="output/unit_candidate.bin",
)
```

内存验证不会创建文件。候选路径（如果提供）仍必须位于 Project 之外，并且不能指向 source BIN。

## 3. 验证顺序

1. 验证 Project、Asset Manifest、Record Identity 和 Edit Set schema。
2. 重新读取外部 source BIN，核对 SHA-256、大小、版本、FPS 与记录身份。
3. 拒绝空 Edit Set、BILE v2、无效 source 路径和不受支持的 writer capability。
4. 按 sequence 从 source 原始字节开始重放每个 SetField：
   - 当前字段 bytes 必须等于 beforeRawHex；
   - 只应用固定 storage offset/width 上的 afterRawHex；
   - 生成独立的最终预期字节镜像。
5. 对候选执行完整 BILE 重解析。
6. 检查 Section 顺序、offset、总长度、计数、header bytes、字符串池偏移和 UTF-8 字节长度。
7. 检查实际 changed-byte set 与预期差异完全一致，且每个变化字节都位于当前字段白名单。
8. 要求候选完整字节镜像与独立重放结果逐字节相同。
9. 再次检查 source SHA-256 和 Project metadata 快照，拒绝验证期间发生的漂移。
10. 文件 API 在结束前重新读取候选，确认候选文件在验证期间没有变化。

## 4. 候选路径与来源保护

- 候选必须是普通文件，不能是符号链接。
- 候选必须位于 Project 目录之外。
- 候选不得与 source BIN 是同一路径或同一个底层文件（含硬链接）。
- source BIN 必须是普通文件且不能是符号链接。
- 验证不写入 source、candidate 或 Project metadata。
- 内存 API 只读验证传入的不可变 bytes；不会发布文件。

## 5. 规范报告

`CanonicalValidationReport.to_dict()` 输出 JSON 友好的结构化报告，包含：

- schema、status、scope；
- projectId、Project 路径；
- source/candidate 的路径、SHA-256、文件大小和 BILE 版本；
- Edit Set 操作数量与 operation IDs；
- 精确 changed-byte offsets、数量及其摘要；
- candidate 与独立预期镜像的 SHA-256；
- 每个验证门的状态（Passed / NotApplicable；内存候选不伪称文件稳定性已验证）；
- 可选 XML/纹理资源 warning；
- `original_game_validation = NotPerformed`。

成功状态为 `OfflineValid`，其 scope 为 `OfflineStructuralAndEditSet`；所有适用的验证门必须通过。

## 6. 明确的非承诺

`OfflineValid` 只证明：

- 文件符合当前解析器理解的 BILE 结构；
- 候选没有越过当前字段/结构写入白名单；
- 候选精确对应这个 Project 的 Edit Set；
- 验证期间 source、Project metadata 和候选文件没有发生可检测的变化。

它**不证明**原游戏一定接受候选，不证明画面正确，不证明动画时序、嵌套行为或游戏内效果符合预期。原游戏验证必须单独执行并记录游戏版本、设备、资源三件套和观察结果。

## 7. 回归测试

`tests/test_candidate_validation.py` 覆盖：

- 编译器返回规范校验证据；
- 已发布候选和内存候选验证；
- 报告 JSON 序列化；
- 结构合法但字段值错误的候选拒绝；
- 未开放 opaque 字段变化拒绝；
- source 路径、Project 内路径、符号链接和 source 硬链接拒绝；
- 空 Edit Set 和 v2 拒绝；
- source、Project metadata（包括读取/哈希快照竞态）、候选文件验证期间漂移检测；
- 可选 XML 哈希变化以 warning 形式保留。

测试使用合成 BILE fixture，不包含或重新分发任何原游戏资源。
