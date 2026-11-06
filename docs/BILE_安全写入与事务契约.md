# BILE 安全写入与事务契约

版本：BILE Safe Mutation / v1
日期：2026-11-05
适用范围：BILE v3/v4 已有文件的固定长度字段修改。

## 1. 基本原则

- 原始 BIN 永远是只读输入；所有编辑都输出到独立候选路径。
- v2 维持严格只读；不仅补丁入口拒绝写入，底层候选门禁也会拒绝 v2。
- 未知字段、未解释 Header、Section Header、保留字和非目标 Payload 字节必须原样保留。
- 结构性修改、记录增删、帧/通道增删、字符串池重排、字符串终止符/边界变化、Section 重排和 playback_mode 写入仍然 NoGo。
- 结构重解析通过不等于原游戏运行时验证通过。

## 2. RawBileImage

RawBileImage 将同一文件的两个视图分开保存：

1. 原始视图：完整 bytes、SHA-256、每个 Section 的原始 Header、Payload、偏移、尺寸和记录计数。
2. 语义视图：由现有 v2/v3/v4 解析器产生的 BileDocument。

无修改 round-trip 直接返回原始 bytes，不重新编码 Section，不重建字符串池，也不丢弃未知字段。

## 3. 补丁合同

每个补丁仍必须包含：

- schema = bile-workbench.interchange/v1；
- kind = patch；
- source_sha256；
- 目标记录 index；
- 允许修改的字段。

新生成的补丁还必须包含 expected-old：

- keyframes[].expected.transform；
- keyframes[].expected.argb；
- keyframes[].expected.initial_phase；
- elements[].expected.anchor；
- elements[].expected.name。

expected 对象中的字段必须与本次修改字段一一对应。expected-old 按 float32/u32 原始表示比较，不以宽松数值近似比较。

为兼容已导出的旧 interchange/v1 补丁，缺少 expected 对象的旧补丁仍可使用，但必须通过完整 source_sha256 绑定。新导出的模板与 EditSession 补丁均会携带 expected-old。

## 4. 候选写入门禁

候选发布前必须全部满足：

1. 输入源文件存在且是普通文件；拒绝源文件符号链接。
2. 输入与输出不是同一路径，也不是同一底层文件。
3. source_sha256 与当前源文件逐字节一致。
4. BILE 版本仍为 v3/v4。
5. 文件长度不变。
6. Section 顺序、偏移、总长度、记录计数、Header 字节和 Header 宽度不变。
7. 候选完整重新解析成功。
8. 编辑计划记录的 expected changed-byte offsets 无重复。
9. 所有变化字节必须落在当前 Python 编辑器白名单：BELE 仿射/ARGB/initial_phase、BMTI anchor 或仅被一个 BMTI 元素引用的 BRTS 名称正文；字符串池偏移、数量与每条 UTF-8 字节长度必须保持不变。
10. 实际 changed-byte set 与编辑计划完全相等；任何计划外字节变化均拒绝。
11. 临时候选回读字节和 SHA-256 与内存候选完全一致。
12. 发布前再次确认源 BIN SHA-256 未发生变化。

## 5. 原子发布与覆盖

默认不覆盖已有输出文件。

新输出先写入输出目录中的唯一临时文件，flush + fsync，回读并重新解析，再通过同目录 no-overwrite 原子链接发布。若当前文件系统不支持该操作，则 fail-closed，不退化为直接写入。

只有 UI 明确询问并得到用户确认后，才允许 overwrite：

1. 读取旧候选并记录 SHA-256。
2. 在同目录准备并校验旧候选备份。
3. 复核目标文件没有发生变化。
4. 使用同目录原子替换发布新候选。
5. 发布后回读并验证字节、SHA-256 和 BILE 结构。
6. 发布后校验失败时，以备份恢复旧候选。

源 BIN 不参与替换。失败时清理临时文件；恢复失败会抛出错误，不得宣称写入成功。

## 6. 当前实现状态与未完成项

已实现：

- RawBileImage 原始字节镜像；
- 固定长度 MutationBuffer；
- expected-old 校验；
- 文件长度与 Section Header/计数不变量；
- 精确 changed-byte set；
- 候选完整重解析；
- 临时文件回读和 SHA-256；
- 源文件漂移复核；
- 默认拒绝覆盖；
- 显式覆盖备份、原子替换与失败恢复。

尚未实现：

- Reconstruction 五类 Recovered Player Canonical 指纹的 Python 等价实现；
- 多操作 Project Edit Set 与 Overlay Compiler；
- 原版游戏自动化运行时验证。

因此当前安全写入门禁只能证明字段白名单、字节边界和 BILE 结构不变量，不得把它宣传为完整播放器行为等价或游戏内验证通过。
