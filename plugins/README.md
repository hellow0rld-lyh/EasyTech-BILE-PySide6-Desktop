# BILE Workbench 外部主题插件

本目录会在工作台启动时自动扫描。每个子目录只要包含 `plugin.json`，就是一个可发现的主题插件；也可以通过“视图 → 主题 → 导入插件文件”导入 `.bileplugin` 或 `.zip` 文件。

当前预设：

- `anime-claude-girl/`：二次元 ClaudeAI 少女，暖金、夜紫、薰衣草风格。
- `anime-openai-girl/`：二次元 OpenAI 少女，青蓝、石墨、薄荷霓虹风格。

每个插件必须自己提供 `themes/light.qss` 和 `themes/dark.qss`，并在 `plugin.json` 中提供自己的 `glass` 材质对象；可以另外提供 `assets/avatar.svg`。宿主只负责读取清单和样式资源，不执行此目录中的 Python 代码。Windows 会尝试 Mica/Acrylic，其他情况使用插件参数生成 QSS 玻璃回退。完整协议见 [`../docs/主题插件开发与安装.md`](../docs/主题插件开发与安装.md)。仓库以文件夹形式分发预设；需要 `.bileplugin` 压缩包时，可将单个插件目录内容打包为 ZIP（确保 `plugin.json` 位于压缩包根目录），再改用 `.bileplugin` 扩展名，或直接导入文件夹。

预设名称只表示视觉灵感标签，不代表与相关公司或产品存在官方隶属关系。
