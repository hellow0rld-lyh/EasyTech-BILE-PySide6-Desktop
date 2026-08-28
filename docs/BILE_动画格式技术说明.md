# BILE 动画格式技术说明

**版本：0.5（跨代 v2 可变轨道计数与组合根动画实证版）**  
**开发者：3136818780（AI 辅助研究与文档整理）**  
**更新日期：2026-08-22**

> 本文说明 EasyTech 系列资源中由 `.bin`、同名 `.xml` 和 `.png`/`.webp` 组成的二维动画三件套。它不是任何游戏运行时的官方声明。文中“已确认”结论均应能由本项目的严格解析器、用户提供的原始样本、离线渲染工件与回归测试复现；没有游戏内扰动证据的字段不会被提升为已确认语义。

## 摘要

BILE 是**小端序、定长记录驱动的二维精灵/层级动画容器**。图集图像仅提供像素，XML 仅提供图集区域与参考点，而 BIN 提供元素、仿射变换、时间线、元素引用和名称。它并不是机器码、压缩包或单张图片格式。

当前工作台已将用户提供的资源验证扩展至 BILE v2、v3 和 v4。v3/v4 共用六节容器和一套完整时间线解码器；将军的荣耀1的 v2 使用较早的五节容器，已实现严格**只读**解析、预览、序列导出与诊断，但没有开放写回。新增的 `def_motion.xml` 与 `unit_infantry` 样本还证明：跨游戏“一个部队变三/四个部队”的现象不能只归因于上层配置，BILE 根动画本身也可能从单兵精灵层级变为并发嵌套的组合动画。

| 证据等级 | 含义 | 本文示例 |
|---|---|---|
| **已确认** | 由严格边界断言、样本全集计数或离线画面复现。 | v2 的五节顺序；v3/v4 的六节顺序；世4步兵组合根动作存在三条并发子动画轨道。 |
| **强推断** | 由跨块一致性、累计消费与渲染结果支持，尚缺游戏内单字段扰动。 | v2 BELE `+0x18` 的浮点 alpha 与其后若干保留字的完整运行时语义。 |
| **未确认** | 尚无可复现运行时证据。 | v2 BELE 后半保留字的确切含义；任何游戏 Army 类型到上层编队行的完整选择规则。 |

## 1. 三件套分工与 XML 兼容性

一个动画资源通常以相同基名配对：`foo.bin`、`foo.xml` 和 `foo.webp` 或 `foo.png`。加载器应按**基名**寻找 XML 和实际存在的图像扩展名，不能相信 XML `<Texture>` 标签中可能过期的 `.png` 文字。

| 文件 | 职责 | 当前工作台能力 | 关键边界 |
|---|---|---|---|
| `.png` / `.webp` | 图集像素与透明通道。 | 统一解码为 RGBA 后离线合成。 | 不重排图集、不改变原图格式。 |
| `.xml` | 图集区域、名称、`refx/refy`。 | 兼容 XML 声明、并列顶层节点、NUL 填充和小数几何。 | 兼容处理仅在内存中进行，不覆写源 XML。 |
| `.bin` | BILE 元素、关键帧、通道、帧、层级和字符串。 | v2/v3/v4 严格解析与预览。 | v2 禁止写回；v3/v4 仅允许已验证字段的保守补丁。 |

XML 可能带 UTF-8 BOM、XML 声明或多个顶层节点。读取器可先移除声明、包裹虚拟根后解析；写回时不得把虚拟根写入原文件。世界征服者3部分 XML 尾部包含非法 NUL 填充，欧洲战争6出现小数图集几何，二者均已在内存中兼容。精灵名称按精确匹配、再追加 `.png` 回退匹配；BMTI 中未被 XML 解析的图片名必须保留为诊断。

图集的局部左上角使用：

```text
left = BMTI.x - Image.refx
top  = BMTI.y - Image.refy
```

该规则已通过原包、参考点样本和离线渲染回归验证。[1] [2]

## 2. 已验证版本与样本范围

下表是独立数据集的验证结果。世界征服者4扩展集可能与最初 11 组原包样本存在重叠，故不把各行简单相加为“唯一文件总数”。

| 数据集 | BILE 版本 | BIN 数 | 严格解析通过 | 完整三件套 | 顶层布局 | 图集 |
|---|---:|---:|---:|---:|---|---|
| 世界征服者4原包起始集 | v4 | 11 组 | 11 组 | 11 组 | 六节 | PNG/WebP |
| 将军的荣耀3 | v4 | 25 | 25 | 25 | 六节 | WebP |
| 欧洲战争6 | v4 | 5 | 5 | 5 | 六节 | PNG |
| 世界征服者3 | v3 | 46 | 46 | 40 | 六节 | PNG |
| 欧洲战争4 | v3 | 16 | 16 | 16 | 六节 | PNG |
| 将军的荣耀1 | v2 | 12 | 12 | 12 | 五节 | PNG |
| 世2新增集 | v2 | 30 | 30 | 30 | 五节 | PNG |
| 欧3新增集 | v2 | 13 | 13 | 13 | 五节 | PNG |
| 世界征服者4扩展集 | v4 | 23 | 23 | 22 | 六节 | PNG/WebP |

将军的荣耀3验证集中另有 `ch_battle.bin`，其魔数不是 `BILE`；它被明确归类为非 BILE 二进制，而不是“容错通过”的动画文件。

## 3. 公共文件头

所有已验证 v2/v3/v4 文件均为小端序，并使用 20 字节头。首先必须满足 `payload_size + header_size == file_size`。

| 偏移 | 类型 | 名称 | v2 | v3/v4 | 结论 |
|---:|---|---|---:|---:|---|
| `0x00` | `char[4]` | magic | `BILE` | `BILE` | **已确认**。 |
| `0x04` | `u32le` | version | 2 | 3、4 | **已确认**。 |
| `0x08` | `u32le` | payload_size | `file_size - 20` | `file_size - 20` | **已确认**。 |
| `0x0C` | `u16le` | header_size | 20 | 20 | **已确认**。 |
| `0x0E` | `u16le` | section_count | 5 | 6 | **已确认**。 |
| `0x10` | `f32le` | fps | 24.0 | 24.0、25.0、40.0 | **强推断**为播放速率；保留原值。 |

非 BRTS 顶层节使用 16 字节节头；BRTS 使用 12 字节节头。`total_size` 包含标签与节头本身，故相邻节应连续，且所有节必须恰好消费文件末尾。

```text
0x00  char[4]  tag
0x04  u32le    total_size
0x08  u32le    count          // BRTS 不解释为字符串数
0x0C  u32le    opaque_value   // 仅非 BRTS 节；当前不赋语义
0x10  byte[]   payload         // 仅非 BRTS 节
```

## 4. BILE v3/v4：六节容器

v3 与 v4 的已确认顺序为：

```text
BELE → BXDI → BMRF → BYAL → BMTI → BRTS
```

| 节 | 记录宽度 | 已确认用途 | 引用方向 |
|---|---:|---|---|
| `BELE` | 44 字节 | 二维仿射关键帧与 ARGB 调制色。 | 被 BXDI 下标引用。 |
| `BXDI` | 8 字节 | `keyframe_index` 与 `element_index` 轨道对。 | 指向 BELE 与 BMTI。 |
| `BMRF` | 8 字节 | 槽位与该帧的轨道数。 | 顺序消费 BXDI。 |
| `BYAL` | 8 字节 | 通道的帧数。 | 顺序消费 BMRF。 |
| `BMTI` | 56 字节 | 名称、锚点、图片/动画类型、帧数与通道数。 | 顺序消费 BYAL，名称指向 BRTS。 |
| `BRTS` | 变长 | UTF-8、NUL 终止字符串。 | 被 BMTI 的字节偏移引用。 |

### 4.1 v3/v4 `BELE`（44 字节）

```text
+0x00..+0x14  f32le xx, xy, yx, yy, x, y
+0x18          u32le argb
+0x1C          u32le initial_phase
+0x20          u32le playback_mode
+0x24          u32le opaque_ref
+0x28          u32le opaque_flags
```

仿射变换为：

```text
out_x = xx * px + yx * py + x
out_y = xy * px + yy * py + y
```

`initial_phase` 是嵌套子动画初始槽位的**强推断**；跨游戏嵌套引用的范围检查和像素比较均支持这一点。`playback_mode` 仅观察到 0/1/2；将军的荣耀3和世界征服者3在实际嵌套轨道上出现值 1，支持其属于嵌套播放控制，但尚未完成游戏内扰动，因此继续只读。

### 4.2 v3/v4 时间线消费

```python
p_byal = p_bmrf = p_bxdi = 0
for element in bmti:
    for channel in range(element.channel_count):
        for frame in range(byal[p_byal].frame_count):
            current = bmrf[p_bmrf]
            for track in range(current.track_count):
                keyframe = bxdi[p_bxdi].keyframe_index
                target = bxdi[p_bxdi].element_index
                p_bxdi += 1
            p_bmrf += 1
        p_byal += 1
assert p_byal == len(byal)
assert p_bmrf == len(bmrf)
assert p_bxdi == len(bxdi)
```

同一通道使用保持帧：槽位 `t` 取最后一个满足 `frame.slot <= t` 的帧，不进行线性插值。`element_index=-1` 是合法空轨道目标，不生成绘制命令。

## 5. BILE v2：将军的荣耀1五节容器

将军的荣耀1原始验证集与新增世2、欧3样本均使用较早的 v2 容器。当前已用 **55** 个 v2 BIN（其中新增 43 个）验证下述读取模型：

```text
BELE → BMRF → BYAL → BMTI → BRTS
```

它没有独立 BXDI 节。所有 55 个样本共同满足如下结构约束：BELE 为 48 字节、BMRF 为 12 字节、BYAL 为 8 字节、BMTI 为 56 字节；按 BMTI 通道数和 BYAL 首个 dword的帧数累计，能够恰好消费 BMRF 帧记录；并且所有样本都满足 **`sum(BMRF.track_count) == BELE.count`**。早期 12 个样本恰好每帧 `track_count=1`，不能将这种巧合提升为格式规则。

| 节 | v2 宽度 | 当前解释 | 证据等级 |
|---|---:|---|---|
| `BELE` | 48 字节 | 前 24 字节仍为二维仿射矩阵与平移；`+0x18` 是 0..1 浮点候选 alpha；最后一个 `s32` 是轨道目标元素索引（或 `-1` 空目标）。 | 前半变换与末尾目标索引由 55 个样本的范围、累计消费和渲染支持；alpha 的完整运行时语义仍未完成变量样本验证。 |
| `BMRF` | 12 字节 | 已确认读取布局 `<u32 slot, u32 track_count, opaque_u32>`；一条 BMRF 帧按 `track_count` 消费连续 BELE。 | **已确认的只读结构模型**；55 个样本均满足累计轨道数等于 BELE 记录数，且新增零轨帧样本通过解析和渲染。 |
| `BYAL` | 8 字节 | `+0x00` 为顺序消费的 BMRF 帧数。 | 强推断。 |
| `BMTI` | 56 字节 | 与 v3/v4 同宽；名称、类型、通道与锚点读取规则已复用通过。 | 已确认的结构兼容。 |
| `BRTS` | 变长 | UTF-8、NUL 终止名称区。 | 已确认的结构兼容。 |

v2 的当前严格只读读取算法为：BMTI/BYAL 先顺序定位每条 BMRF 帧；每条 BMRF 从其 `slot` 给出帧时间，再从 `track_count` 消费 0 条或多条连续 BELE。被消费的每条 BELE 用最后一个有符号 dword定位 BMTI 目标元素，`-1` 代表空目标。解析器必须同时断言 BYAL、BMRF 与 BELE 三个累计游标恰好全消费，且每个 BELE 目标只能为 `-1` 或合法 BMTI 下标。新增世2与欧3的零轨帧变体及原先每帧一轨的将军的荣耀1样本均通过该模型的严格解析和代表帧渲染；然而 v2 记录中的其余保留字、浮点 alpha 的完整运行时语义，以及 v2 写回兼容性尚未经游戏内实证。

> **安全策略：** BILE v2 当前只开放打开、诊断、预览、离线序列导出和 AI 全文档导出；关键帧写入、锚点写入、候选 BIN、实验包与补丁写回均被程序拒绝。

## 6. 根动画组合与“一个单位/多个单位”

要解释跨游戏替换后可见部队数量，必须区分两个层级：

1. **BILE 根动作内部组合：** 一个动画根元素可以直接引用大量精灵，也可以并发引用多个子动画；后者可在一份三件套中形成多个完整兵模。
2. **游戏上层实例化：** Army/Unit、方向、阵列或 Formation 配置可能把同一根动作再次放在多个世界坐标。该层不在 BIN、同名图集 XML 或 `def_motion.xml` 的 `Unit/Motion` 节点中。

### 6.1 已确认的 `unit_infantry` 根动作差异

`def_motion.xml` 将 Unit 模板映射到资源基名和精确 Motion 名。将军的荣耀3 `unit_infantry` 有 115 个 Unit 变体、995 个唯一的 XML Motion 名，均能在提供的 BILE v4 动画元素中精确命中；世界征服者4提供的 `unit_infantry` 有 90 个 Unit 变体、356 个唯一 Motion 名，亦全部精确命中。二者都不是“缺动作导致只显示一个”的情况。

| Soldier 待机根动作 | 槽位/通道 | 最大并发直接子动画轨道 | 最大并发直接精灵轨道 | 递归精灵叶子 | 离线代表帧 |
|---|---:|---:|---:|---:|---|
| 将军的荣耀3 `盟军通用普通士兵待机动画` | 60 / 19 | 0 | 19 | 19 | 单个完整步兵。 |
| 世界征服者4 `通用普通步兵待机组合动画` | 48 / 3 | 3 | 0 | 18 | 三个完整步兵。 |

![单根动画离线对照：不应用上层阵列实例](../research/unit_infantry_root_animation_comparison.png)

> 因此，“将3三件套置入世4后只出现一个单位”的解释至少有一层已获强支持：将3对应根动作本身是单兵精灵组合，而世4对应根动作本身是并发嵌套三份子动画的组合根。反向替换时，世4根动作已经自带三人画面；若实际游戏中出现四人或更多，则还应检查游戏上层阵列实例。

根动作组合诊断会显示 `ROOT_ANIMATION_DIRECT_SPRITE_COMPOSITION` 或 `ROOT_ANIMATION_NESTED_COMPOSITION`。这些诊断描述的是**一份 BILE 根动作内部**的组合，不得直接标注为“格子人数”。

### 6.2 待游戏内验证的上层实例模型

为设计受控实验，可使用以下工作模型：

```text
格子可见模型数
≈ 上层 primary 实例数 × 根动作内的并发兵模子实例数
  +（若存在）上层 special 实例
```

该公式不是已确认的通用引擎规则。必须通过同版本的 Army/Unit 配置、阵列表、`def_motion.xml`、三件套和游戏内截图逐变量验证。最小实验应保持 Army 类型、地图、方向与上层配置不变，只交换根动作三件套；然后反过来只修改一个上层阵列坐标位，以区分“BIN 内三人”与“上层三次实例化”。

## 7. 直接编辑与写回边界

| 能力 | BILE v2 | BILE v3/v4 |
|---|---|---|
| 严格解析、诊断与预览 | 支持 | 支持 |
| GIF/APNG/PNG 序列导出 | 支持 | 支持 |
| AI 全文档 JSON 导出 | 支持 | 支持 |
| 仿射、ARGB、`initial_phase` 保守写回 | **禁止** | 支持经预检的 v3/v4 字段。 |
| BMTI 锚点/等字节改名 | **禁止** | 支持经预检的 v3/v4 字段。 |
| `playback_mode` 写回 | **禁止** | **禁止**；缺少运行时扰动实证。 |
| 新建/删除元素、帧、通道 | **禁止** | 实验性，尚未开放。 |

v3/v4 补丁提交前必须检查源 SHA-256、完整重解析、图循环、BRTS 偏移、累计时间线消费和 `initial_phase` 子动画帧范围。候选文件只能另存并通过游戏内实验包回归，不覆盖用户原始 BIN。

## 8. 可复现工具与回归

| 路径 | 用途 |
|---|---|
| `src/bile_workbench/bile_format.py` | v2/v3/v4 严格解析器；v2 五节、v3/v4 六节、BRTS、时间线和引用图。 |
| `src/bile_workbench/diagnostics.py` | 版本、图集、播放字段、根动画组合和只读安全边界诊断。 |
| `tools/probe_cross_generation_assets.py` | 欧4、将1、世4扩展集的三件套盘点。 |
| `tools/probe_bile_v2_layout.py` | v2/v3/v4 顶层节与记录宽度测量。 |
| `tools/verify_bile_v2_candidate_layout.py` | 将1 12 个 v2 样本的候选结构约束检查。 |
| `tools/probe_cross_era_v2_layout.py` | 世2/欧3新增 v2 的 BMRF 轨道计数、BELE 总量和零轨帧不变量审计。 |
| `tools/smoke_v2_variant_gui.py` | 世2/欧3零轨帧 v2 变体在 Ribbon 工作台中的离屏加载、预览与轨道检查器冒烟。 |
| `tools/analyze_motion_definitions.py` | `def_motion.xml` 的 Unit—资源—动作精确匹配审计。 |
| `tools/analyze_unit_infantry_composition.py` | 将3/世4 `unit_infantry` 根动作引用图和并发组合审计。 |
| `tools/render_unit_infantry_composition_comparison.py` | 单根动作离线代表帧对照，不叠加上层阵列。 |
| `tools/smoke_general1_v2_gui.py` | 将1 v2 只读 GUI 冒烟验证。 |

从项目根目录执行：

```bash
python3 tools/probe_cross_generation_assets.py
python3 tools/verify_bile_v2_candidate_layout.py
python3 tools/probe_cross_era_v2_layout.py incoming/cross_era_20260822 --output research/cross_era_v2_layout_compare_20260822.json
python3 tools/smoke_v2_variant_gui.py
python3 tools/analyze_motion_definitions.py
python3 tools/analyze_unit_infantry_composition.py
python3 tools/render_unit_infantry_composition_comparison.py
python3 -m unittest discover -s tests -v
```

## 9. 当前边界与下一步

当前项目已经从“未知 BIN”推进到 v2/v3/v4 的可审计读取、离线预览和跨游戏结构验证。v3/v4 的保守编辑可用于游戏内实验；v2 先保持只读。最有价值的下一步不是放宽写回，而是完成两个可证伪的运行时实验：其一，固定同一 Army/阵列行，仅交换单兵根动作和三人组合根动作；其二，固定三件套，仅增减一个上层坐标位。这样才能确认跨游戏可见人数中究竟有多少来自 BILE 内部组合、多少来自引擎上层实例化。

## References

[1]: https://european-war-4.boards.net/thread/14529/ew-bin-files
[2]: https://github.com/XenoHoe/animation-conqueror-4

[1] Easytech Fan Community. “`[EW4] .bin files`.” 2021-03-17。该帖提供 BILE 早期块标签、记录尺寸与 BRTS UTF-8 观察；本文仅采纳经本地样本复验的内容。

[2] XenoHoe. “`animation-conqueror-4`.” GitHub repository, accessed 2026-08-21。用于静态交叉审计；本项目的解析器、渲染器与回归均独立执行。
