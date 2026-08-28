"""外部主题插件协议与加载仓库。

插件首版是纯数据资源：plugin.json + light/dark QSS + 可选头像资源。
不会执行插件目录中的 Python 代码，也不会把预设插件名称写入宿主程序。
"""
from __future__ import annotations

import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from PySide6.QtCore import QSettings

from .glass_effects import GlassSpec, parse_glass_spec


PLUGIN_SCHEMA = "bile-workbench-plugin/v1"
_PLUGIN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")
_PLUGIN_FILE_SUFFIXES = {".bileplugin", ".zip"}


class ThemePluginError(ValueError):
    """插件清单或资源不符合宿主协议。"""


@dataclass(frozen=True)
class ThemePlugin:
    """已经通过校验、可直接应用的主题插件。"""

    plugin_id: str
    name: str
    version: str
    description: str
    author: str
    source: Path
    light_qss: str
    dark_qss: str
    glass: GlassSpec
    avatar_data: bytes | None = None

    def qss_for(self, mode: str) -> str:
        if mode == "light":
            return self.light_qss
        if mode == "dark":
            return self.dark_qss
        raise ThemePluginError(f"未知基础主题：{mode}")


class ThemePluginLoader:
    """加载文件夹或 .bileplugin/.zip 文件，不导入、执行其中的代码。"""

    @classmethod
    def load(cls, source: Path) -> ThemePlugin:
        source = Path(source).expanduser()
        if source.is_dir():
            return cls._load_folder(source)
        if source.is_file() and source.suffix.lower() in _PLUGIN_FILE_SUFFIXES:
            return cls._load_archive(source)
        raise ThemePluginError(f"不是可识别的主题插件文件或文件夹：{source}")

    @classmethod
    def _load_folder(cls, root: Path) -> ThemePlugin:
        root = root.resolve()
        manifest_path = root / "plugin.json"
        if not manifest_path.is_file():
            raise ThemePluginError(f"插件文件夹缺少 plugin.json：{root}")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ThemePluginError(f"无法读取插件清单：{manifest_path.name}：{exc}") from exc

        def read_text(relative: str, label: str) -> str:
            path = cls._safe_folder_path(root, relative, label)
            if not path.is_file():
                raise ThemePluginError(f"插件资源不存在：{relative}")
            try:
                return path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                raise ThemePluginError(f"无法读取插件资源：{relative}：{exc}") from exc

        def read_bytes(relative: str | None, label: str) -> bytes | None:
            if not relative:
                return None
            path = cls._safe_folder_path(root, relative, label)
            if not path.is_file():
                raise ThemePluginError(f"插件资源不存在：{relative}")
            try:
                return path.read_bytes()
            except OSError as exc:
                raise ThemePluginError(f"无法读取插件资源：{relative}：{exc}") from exc

        return cls._build_plugin(
            manifest,
            source=root,
            light_qss=read_text(cls._theme_path(manifest, "light"), "light theme"),
            dark_qss=read_text(cls._theme_path(manifest, "dark"), "dark theme"),
            avatar_data=read_bytes(cls._asset_path(manifest, "avatar"), "avatar"),
        )

    @classmethod
    def _load_archive(cls, source: Path) -> ThemePlugin:
        source = source.resolve()
        try:
            with zipfile.ZipFile(source) as archive:
                members = archive.namelist()
                cls._validate_archive_members(members)
                try:
                    manifest = json.loads(archive.read("plugin.json").decode("utf-8"))
                except KeyError as exc:
                    raise ThemePluginError("插件压缩包缺少 plugin.json") from exc
                except (UnicodeError, json.JSONDecodeError) as exc:
                    raise ThemePluginError(f"插件压缩包的 plugin.json 无效：{exc}") from exc

                def read_text(relative: str, label: str) -> str:
                    try:
                        return archive.read(relative).decode("utf-8")
                    except KeyError as exc:
                        raise ThemePluginError(f"插件资源不存在：{relative}") from exc
                    except UnicodeError as exc:
                        raise ThemePluginError(f"插件资源不是 UTF-8 文本：{relative}") from exc

                def read_bytes(relative: str | None, label: str) -> bytes | None:
                    if not relative:
                        return None
                    try:
                        return archive.read(relative)
                    except KeyError as exc:
                        raise ThemePluginError(f"插件资源不存在：{relative}") from exc

                return cls._build_plugin(
                    manifest,
                    source=source,
                    light_qss=read_text(cls._theme_path(manifest, "light"), "light theme"),
                    dark_qss=read_text(cls._theme_path(manifest, "dark"), "dark theme"),
                    avatar_data=read_bytes(cls._asset_path(manifest, "avatar"), "avatar"),
                )
        except zipfile.BadZipFile as exc:
            raise ThemePluginError(f"插件压缩包损坏：{source.name}") from exc
        except OSError as exc:
            raise ThemePluginError(f"无法打开插件压缩包：{source.name}：{exc}") from exc

    @staticmethod
    def _validate_archive_members(members: list[str]) -> None:
        for member in members:
            path = PurePosixPath(member)
            if path.is_absolute() or ".." in path.parts:
                raise ThemePluginError(f"插件压缩包包含越界路径：{member}")
            if member.startswith("/") or "\\" in member:
                raise ThemePluginError(f"插件压缩包包含非法路径：{member}")

    @staticmethod
    def _safe_folder_path(root: Path, relative: str, label: str) -> Path:
        if not isinstance(relative, str) or not relative.strip():
            raise ThemePluginError(f"插件清单缺少 {label} 资源路径")
        candidate = (root / relative).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ThemePluginError(f"插件资源路径越界：{relative}") from exc
        return candidate

    @staticmethod
    def _theme_path(manifest: dict[str, Any], mode: str) -> str:
        themes = manifest.get("themes")
        if not isinstance(themes, dict):
            raise ThemePluginError("插件清单的 themes 必须是对象")
        value = themes.get(mode)
        if not isinstance(value, str) or not value.strip():
            raise ThemePluginError(f"插件清单缺少 {mode} 主题路径")
        if value.startswith("/") or "\\" in value or ".." in PurePosixPath(value).parts:
            raise ThemePluginError(f"插件主题路径非法：{value}")
        return value

    @staticmethod
    def _asset_path(manifest: dict[str, Any], asset_name: str) -> str | None:
        assets = manifest.get("assets", {})
        if not isinstance(assets, dict):
            raise ThemePluginError("插件清单的 assets 必须是对象")
        value = assets.get(asset_name)
        if value is None:
            return None
        if not isinstance(value, str) or value.startswith("/") or "\\" in value or ".." in PurePosixPath(value).parts:
            raise ThemePluginError(f"插件资源路径非法：{value}")
        return value

    @staticmethod
    def _build_plugin(
        manifest: Any,
        *,
        source: Path,
        light_qss: str,
        dark_qss: str,
        avatar_data: bytes | None,
    ) -> ThemePlugin:
        if not isinstance(manifest, dict):
            raise ThemePluginError("plugin.json 顶层必须是对象")
        if manifest.get("schema") != PLUGIN_SCHEMA:
            raise ThemePluginError(f"不支持的插件 schema：{manifest.get('schema')!r}")
        if manifest.get("type") != "theme":
            raise ThemePluginError("当前只支持 type=theme 的资源插件")
        plugin_id = manifest.get("id")
        if not isinstance(plugin_id, str) or not _PLUGIN_ID_RE.fullmatch(plugin_id):
            raise ThemePluginError("插件 id 必须是 2-64 位小写字母、数字、点、短横线或下划线")
        fields = {}
        for key in ("name", "version", "description"):
            value = manifest.get(key)
            if not isinstance(value, str) or not value.strip():
                raise ThemePluginError(f"插件清单缺少有效字段：{key}")
            fields[key] = value.strip()
        author = manifest.get("author", "")
        if not isinstance(author, str):
            raise ThemePluginError("插件清单的 author 必须是字符串")
        return ThemePlugin(
            plugin_id=plugin_id,
            name=fields["name"],
            version=fields["version"],
            description=fields["description"],
            author=author.strip(),
            source=source,
            light_qss=light_qss,
            dark_qss=dark_qss,
            glass=parse_glass_spec(manifest.get("glass")),
            avatar_data=avatar_data,
        )


class ThemePluginRepository:
    """管理内置插件与用户添加的外部来源，并持久化来源路径。"""

    def __init__(self, bundled_dir: Path) -> None:
        self.bundled_dir = Path(bundled_dir).resolve()
        self.settings = QSettings("py-workbench-evolution", "BILE Workbench")
        self.plugins: dict[str, ThemePlugin] = {}
        self.errors: list[str] = []
        self.base_mode = "dark"
        self.active_plugin_id: str | None = None

    @property
    def external_sources(self) -> tuple[Path, ...]:
        raw = self.settings.value("themePluginSources", [])
        if isinstance(raw, str):
            raw = [raw]
        if not isinstance(raw, (list, tuple)):
            return ()
        result = []
        for item in raw:
            if isinstance(item, str) and item.strip():
                result.append(Path(item).expanduser())
        return tuple(dict.fromkeys(result))

    def remember_source(self, source: Path) -> None:
        source = Path(source).expanduser().resolve()
        sources = list(self.external_sources)
        if source not in sources:
            sources.append(source)
            self.settings.setValue("themePluginSources", [str(item) for item in sources])
            self.settings.sync()

    def discover(self) -> tuple[ThemePlugin, ...]:
        self.plugins = {}
        self.errors = []
        sources = (self.bundled_dir, *self.external_sources)
        candidates: list[Path] = []
        for source in sources:
            candidates.extend(self._candidates_from_source(source))
        for candidate in candidates:
            try:
                plugin = ThemePluginLoader.load(candidate)
            except ThemePluginError as exc:
                self.errors.append(f"{candidate}: {exc}")
                continue
            if plugin.plugin_id in self.plugins:
                self.errors.append(f"重复插件 id，已保留先发现者：{plugin.plugin_id}（{candidate}）")
                continue
            self.plugins[plugin.plugin_id] = plugin
        self.base_mode = self.settings.value("themeBaseMode", "dark")
        if self.base_mode not in {"light", "dark"}:
            self.base_mode = "dark"
        remembered = self.settings.value("activeThemePlugin", "")
        self.active_plugin_id = remembered if isinstance(remembered, str) and remembered in self.plugins else None
        return tuple(self.plugins.values())

    def set_base_mode(self, mode: str) -> None:
        if mode not in {"light", "dark"}:
            raise ThemePluginError(f"未知基础主题：{mode}")
        self.base_mode = mode
        self.settings.setValue("themeBaseMode", mode)
        self.settings.sync()

    def set_active_plugin(self, plugin_id: str | None) -> None:
        if plugin_id is not None and plugin_id not in self.plugins:
            raise ThemePluginError(f"未找到主题插件：{plugin_id}")
        self.active_plugin_id = plugin_id
        self.settings.setValue("activeThemePlugin", plugin_id or "")
        self.settings.sync()

    def active_plugin(self) -> ThemePlugin | None:
        return self.plugins.get(self.active_plugin_id) if self.active_plugin_id else None

    @staticmethod
    def _candidates_from_source(source: Path) -> list[Path]:
        source = Path(source).expanduser()
        if not source.exists():
            return []
        if source.is_file():
            return [source] if source.suffix.lower() in _PLUGIN_FILE_SUFFIXES else []
        if (source / "plugin.json").is_file():
            return [source]
        result: list[Path] = []
        for entry in sorted(source.iterdir(), key=lambda item: item.name.casefold()):
            if entry.is_dir() and (entry / "plugin.json").is_file():
                result.append(entry)
            elif entry.is_file() and entry.suffix.lower() in _PLUGIN_FILE_SUFFIXES:
                result.append(entry)
        return result
