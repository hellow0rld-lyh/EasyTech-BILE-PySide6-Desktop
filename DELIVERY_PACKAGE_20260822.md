# EasyTech 动画工作台交付包说明

> **历史快照（2026-08-22）**：本文只记录当日 ZIP 交付物的组成和验证结果，不代表当前仓库目录、当前测试数量或当前 Release 内容。当前安装与开发入口请以 [README](README.md) 和 [文档索引](docs/README.md) 为准。

## 包内容

本交付 ZIP 包含当前工作台的 Python/PySide6 源码、离屏测试、技术文档、研究与审计记录、辅助工具、打包配置、参考资料、随项目保存的小型样例资源，以及项目顶层说明与 `pyproject.toml`。

| 内容 | 目录或文件 |
|---|---|
| 工作台源码 | `src/` |
| 回归测试 | `tests/` |
| 专业技术文档 | `docs/` |
| 可复现研究、审计 JSON、截图与分析记录 | `research/` |
| 审计与辅助脚本 | `tools/` |
| 打包与参考材料 | `packaging/`、`reference/` |
| 项目内小型样例 | `sample_assets/` |
| 项目说明 | `README.md`、`pyproject.toml`、各增量说明文档 |

## 未包含的原始大样本

为避免将用户已提供、体积较大的游戏资源重复打包，本交付 ZIP 不包含 `incoming/` 和 `cross_game_assets/`。这些目录包含原始 BIN、ATLAS、图像及跨游戏数据集；工作台的跨样本研究结果、锚点路径和审计记录仍已保留在 `research/` 与 `docs/` 中。

> 该交付包不包含编译缓存、`__pycache__/`、临时测试输出或任何改写后的 Spine BIN。Spine 解析与审阅路径保持只读；BILE 编辑仍受版本与字段边界限制。

## 最近已验证基线

交付前最近一次完整离屏回归为 **138/138 PASS**。该基线包括 BILE、Spine 3.8/4.1、工作台 Ribbon/会话、只读 evidence、受限 two-color normal-alpha preview、源 BIN 零写入与现有回归约束。
