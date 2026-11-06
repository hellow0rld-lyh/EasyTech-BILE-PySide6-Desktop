# BILE Workbench：跨格式动画瑞士军刀时间线增量

> **历史实现记录（2026-08-22）**：本文保留 BILE/Spine 时间线读取增量的阶段性结论与测试快照。文中的“下一阶段”是当时计划，不是当前待办；当前能力请以 README、docs/README.md 和具体技术契约为准。

**交付版本：2026-08-22；定位：BILE 保守编辑工作台 + EasyTech Spine 新引擎完整结构审阅工作台。**

本增量完成了项目此前最大的读取能力跃迁：欧7 Spine 3.8.99 与征2 Spine 4.1.x 不再只读取静态骨架，而是按各自官方 `SkeletonBinary.readAnimation` 顺序，从 skins 结束后的 event definitions 一直严格累计消费到文件末尾。新能力被接入既有 WPS/CAD 风格 Ribbon 与专业 Dock 工作区，并以统一只读 JSON 档案供人工审阅、社区研究和未来 AI/代码化动作提案使用。

## 1. 新完成的能力

| 模块 | 欧7 Spine 3.8.99 | 征2 Spine 4.1.x |
|---|---|---|
| 全样本静态骨架读取 | 212 / 212 | 468 / 468 |
| 全样本 animations 段完整消费 | **212 / 212** | **468 / 468** |
| 动画根 / timeline 总量 | 1,180 / 178,925 | 1,827 / 172,456 |
| 读取的关键 timeline | slot attachment/color；bone transform；IK/transform/path；deform；draw order；event。 | RGBA/RGB/RGBA2/RGB2/alpha；单轴 bone；IK/transform/path；deform；sequence；draw order；event。 |
| 主工作台审阅 | 动画根、时长、分组、目标、帧数、首尾时间；ATLAS 局部预览。 | 同左，支持新式 `bounds/offsets/rotate` ATLAS 方言。 |
| JSON 档案 | `easytech-spine-workspace/v2`；包含静态结构、图集、timeline 类型统计、动画时间线、完整消费标记。 | 同左。 |

## 2. 工作台变化

文件页的 **“打开 Spine 静态资源”** 现在会自动加载已验证的 Spine 3.8 或 4.1 结构与动画档案；**“导出 Spine 结构与动画档案”** 会输出统一 JSON。资源浏览器新增动画档案分组；选择动画根会同步更新检查器和状态栏。底部新增 **“Spine 动画档案”** Dock，以树状方式显示每个 animation 的时长与其 slot、bone、constraint、attachment、draw order、event 分组时间线。

Ribbon 新增只在完整 Spine 时间线读取成功时显示的 **“Spine 动画”** 上下文页。该页仅组织只读档案与预览操作。加载 Spine 时，所有 BILE 的补丁、待提交写回和游戏内实验包操作继续禁用。

## 3. 严格读取规则

读取器不会凭经验跳过不认识的字节。每份文件都必须满足版本分流、计数上限、字符串引用、骨骼/插槽/约束/皮肤索引、曲线类型、draw-order slot 次序、事件索引、单调非负时间以及 **animations 终点等于文件末尾**。若任何一项失败，工作区最多保留静态审阅，并明确报告 timeline 错误；不会把资源列为“完整动画已支持”。

征2首轮有 110 份样本被严格拒绝。通过回到官方 4.1 读取顺序并对照真实反例，确认 deform 使用“当前值 → 下一时间 → curve”，IK 使用“当前 flags → 下一数值 → curve”。修正不是降低约束，修正后六个 4.1 子版本 468 / 468 全部通过。

## 4. 未扩大边界

| 仍未实现或禁止 | 原因 |
|---|---|
| Spine pose 求解、逐帧播放、曲线求值、IK/transform/path 运行时处理、deform 网格、draw-order 实际合成 | 当前完成的是二进制结构读取与审阅，不是 Spine runtime。 |
| Spine BIN 写回、重建、补丁、实验包 | 未建立逐类型“修改 → 回读 → 官方 runtime → 游戏内播放”闭环。 |
| BILE v2 写回 | v2 继续严格只读。 |
| BILE 未实证字段与结构重排 | 既有白名单、完整重解析、SHA-256 和回归边界不变。 |

## 5. 回归和视觉证据

完整项目回归为 **58 / 58 通过**，约 58 秒。欧7 `Arthur2.bin` 和征2 `EmpireCityFire01.bin` 的离屏 GUI 冒烟均完成完整 timeline 工作区加载、动画根选择、ATLAS 区域预览、结构档案导出入口和 BILE 写回禁用断言。截图显示动画档案 Dock 与图集预览同时可读。

下一阶段的正确目标是 **Spine 只读 pose / 序列预览**，先覆盖 bone/slot attachment/color 的线性和 stepped 子集；在此前不能将完整结构读取包装成可播放，更不能提前开放任何 Spine 写回。完整能力地图、跨格式矩阵和每一阶段门槛见随包文档。
