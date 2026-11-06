# BILE Workbench

**BILE Workbench** 是面向 EasyTech 系列游戏动画资源的 Windows 桌面工作台。它用于检查和预览 BILE 动画三件套、理解动画层级与时间线、进行受限字段编辑，并以可追溯的候选文件和验证报告完成离线审阅。

> **当前版本：** [v0.1.0-rc.1（公开预发布）](https://github.com/hellow0rld-lyh/EasyTech-BILE-PySide6-Desktop/releases/tag/v0.1.0-rc.1)
> Windows x64 · 未签名便携包 · MIT License

[下载 Windows x64](https://github.com/hellow0rld-lyh/EasyTech-BILE-PySide6-Desktop/releases/download/v0.1.0-rc.1/BILEWorkbench-Windows-x64.zip) · [SHA-256 校验文件](https://github.com/hellow0rld-lyh/EasyTech-BILE-PySide6-Desktop/releases/download/v0.1.0-rc.1/BILEWorkbench-Windows-x64.zip.sha256) · [全部 Releases](https://github.com/hellow0rld-lyh/EasyTech-BILE-PySide6-Desktop/releases)

> 这是预发布版本，不是稳定版。自动化测试和成功打包不等于真实桌面交互验收，更不等于目标游戏内验收。请先使用副本和实验文件，不要把唯一原始资源作为编辑目标。

## 能做什么

| 模块 | 当前能力 | 边界 |
|---|---|---|
| BILE 解析 | 严格读取 v2、v3、v4 容器、记录、引用和时间线结构。 | v2 只读；版本与字段语义按证据范围区分。 |
| 动画预览 | 动画层级、精灵/子动画引用、离散时间线、图集区域与参考点预览。 | 离线画面不代表游戏运行时画面完全一致。 |
| 保守编辑 | v3/v4 已验证字段的暂存编辑、撤销/重做、补丁导出和预检。 | 不开放任意增删元素、帧、Track 或字符串重排；playback_mode 不写回。 |
| Project Model / Edit Set | 以外部资源引用建立工程，记录有序、可审计的字段变更。 | Reference-only：工程不会把原始游戏资源复制进项目。 |
| Overlay Compiler | 顺序重放 Edit Set、逐步验证并生成独立候选 BIN。 | 不原位覆盖源 BIN。 |
| Canonical Validation | 独立重放变更并逐字节核对候选文件，输出验证结果。 | 离线验证不能证明目标游戏接受候选。 |
| Spine 只读审阅 | 对文档明确覆盖的 Spine 3.8/4.1 资源进行静态结构审阅与预览。 | 不是通用 Spine 编辑器；不提供 Spine 写回。 |
| 诊断与回归 | 结构诊断、候选差异、轨道影响范围和实验记录。 | 游戏内结论必须由独立人工/设备证据支持。 |
| 主题插件 | 加载外部 QSS 主题插件，支持文件夹和压缩包导入。 | 插件主题资源不等于可执行 Python 扩展。 |

详细的功能状态、格式约束与证据边界见[文档索引](docs/README.md)。

## 下载与安装

1. 从 [v0.1.0-rc.1 Release](https://github.com/hellow0rld-lyh/EasyTech-BILE-PySide6-Desktop/releases/tag/v0.1.0-rc.1) 下载 ZIP 和 .sha256 文件。
2. 校验 ZIP 的 SHA-256。
3. 将 ZIP **完整解压**到一个目录。
4. 运行解压目录中的 BILEWorkbench.exe。

这是 PyInstaller one-folder 便携包，不是安装程序。不要把 EXE 单独移动出来；Qt 和应用资源位于同一目录。当前构建未签名，Windows SmartScreen 或杀毒软件可能显示未知发布者提示。项目不提供自动更新器。

PowerShell 校验示例：

    Get-FileHash .\BILEWorkbench-Windows-x64.zip -Algorithm SHA256
    Get-Content .\BILEWorkbench-Windows-x64.zip.sha256

比较两处输出的哈希值；一致后再解压运行。

## 第一次打开资源

BILE 资源通常由同名文件组成：

    example.bin
    example.xml
    example.webp   # 有些资源使用 .png

将三件套放在同一目录，从工作台打开 BIN。程序会按同名资源查找 XML 和图集图像；缺少 WebP 时会尝试 PNG。建议：

- 首次操作前备份原始三件套；
- 优先使用副本或单独实验目录；
- 编辑后先运行预检、导出候选并做独立验证；
- 记录候选文件哈希和对应游戏版本；
- 只有完成目标游戏内回归后，才把某个效果标记为游戏内确认。

BILE v2 只支持读取、诊断和预览。v3/v4 也只能使用工作台明确开放的保守字段编辑能力。

## 从源码运行

推荐使用 Python 3.11。Windows PowerShell：

    py -3.11 -m venv .venv
    .\.venv\Scripts\Activate.ps1
    python -m pip install --upgrade pip
    python -m pip install -e .
    bile-workbench

也可以直接运行模块：

    $env:PYTHONPATH = "$PWD\src"
    python -m bile_workbench.app

## 开发验证

    python -m compileall -q src tests
    python -m pip check
    python -m unittest discover -s tests -v

GitHub Actions 对 Python 3.11、3.12、3.13 执行公开测试，并在 Windows 上构建 x64 one-folder 包。依赖原版游戏资源、私有样本或本地素材的测试不会随公开仓库分发；缺少素材时应标记为 Skip/NotRun，而不是计为通过。

Windows 打包：

    .\packaging\build_windows.ps1

产物位于 dist\BILEWorkbench\。构建成功不代表真实桌面交互验收通过。

## 文档与研究

- **普通用户：** [文档索引](docs/README.md)、[Project UI 工作流](docs/BILE_Project_UI_Workflow.md)、[主题插件安装](docs/主题插件开发与安装.md)。
- **格式与编辑：** [BILE 格式技术说明](docs/BILE_动画格式技术说明.md)、[安全写入契约](docs/BILE_安全写入与事务契约.md)、[专业轨道编辑指南](docs/专业轨道编辑与取证指南.md)。
- **工程化工作流：** [Project Model / Edit Set](docs/BILE_Project_Model_与_Edit_Set.md)、[Overlay Compiler](docs/BILE_Overlay_Compiler.md)、[Canonical Candidate Validation](docs/BILE_Canonical_Candidate_Validation.md)、[Workflow Service](docs/BILE_Project_Workflow_Service.md)。
- **AI 与场景提案：** [AI 动画中转格式](docs/AI_动画中转格式使用说明.md)、[AI Motion DSL 只读契约](docs/AI_Motion_DSL_只读提案契约_v1.md)、[Scene Interchange](docs/BILE_Scene_Interchange_v1_只读场景契约.md)。
- **Spine 与跨游戏：** [Spine 静态工作区说明](docs/Spine_新引擎静态工作区技术说明.md)、[跨游戏兼容性报告](docs/跨游戏BILE兼容性报告.md)、[跨代资源格式边界](docs/跨代资源格式边界报告.md)。
- **项目规则：** [产品治理](PRODUCT_GOVERNANCE.md)、[发布流程](RELEASE_PROCESS.md)、[变更日志](CHANGELOG.md)。

## 项目边界与许可

源码和项目自有文档采用 [MIT License](LICENSE)。仓库不提供原始游戏 BIN/XML/图集、APK/SO/DEX、私有测试素材或用户工程。EasyTech、Spine 及其他第三方名称和商标归其各自权利人所有；BILE Workbench 是非官方社区工具，不代表任何厂商背书。

请自行确认你对输入、修改和分发的游戏资源拥有相应权利。产品范围、证据等级和发布验收要求见 [PRODUCT_GOVERNANCE.md](PRODUCT_GOVERNANCE.md)。
