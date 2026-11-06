from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bile_workbench.theme_plugins import ThemePluginError, ThemePluginLoader


class ThemePluginLoaderTests(unittest.TestCase):
    def _manifest(self, *, light: str = "themes/light.qss", dark: str = "themes/dark.qss", avatar: str | None = None) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema": "bile-workbench-plugin/v1",
            "type": "theme",
            "id": "test-plugin",
            "name": "测试主题插件",
            "version": "1.0.0",
            "description": "用于单元测试的外部主题",
            "themes": {"light": light, "dark": dark},
        }
        if avatar is not None:
            payload["assets"] = {"avatar": avatar}
        return payload

    def _write_folder(self, root: Path, manifest: dict[str, object]) -> None:
        (root / "themes").mkdir(parents=True)
        (root / "themes" / "light.qss").write_text("QWidget { color: #111111; }", encoding="utf-8")
        (root / "themes" / "dark.qss").write_text("QWidget { color: #eeeeee; }", encoding="utf-8")
        (root / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")

    def test_loads_external_folder_without_importing_code(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "folder-plugin"
            root.mkdir()
            self._write_folder(root, self._manifest())
            plugin = ThemePluginLoader.load(root)
            self.assertEqual("test-plugin", plugin.plugin_id)
            self.assertIn("#111111", plugin.qss_for("light"))
            self.assertIn("#eeeeee", plugin.qss_for("dark"))

    def test_loads_external_bileplugin_archive(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            root.mkdir()
            self._write_folder(root, self._manifest())
            archive_path = Path(directory) / "test-plugin.bileplugin"
            with zipfile.ZipFile(archive_path, "w") as archive:
                for path in root.rglob("*"):
                    if path.is_file():
                        archive.write(path, path.relative_to(root).as_posix())
            plugin = ThemePluginLoader.load(archive_path)
            self.assertEqual("test-plugin", plugin.plugin_id)
            self.assertEqual(archive_path.resolve(), plugin.source)

    def test_rejects_theme_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "unsafe-plugin"
            root.mkdir()
            manifest = self._manifest(light="../outside.qss")
            self._write_folder(root, manifest)
            with self.assertRaises(ThemePluginError):
                ThemePluginLoader.load(root)

    def test_rejects_archive_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive_path = Path(directory) / "unsafe.bileplugin"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("../escape.txt", "no")
            with self.assertRaises(ThemePluginError):
                ThemePluginLoader.load(archive_path)

    def test_bundled_preset_files_are_loadable(self) -> None:
        plugin_dir = ROOT / "plugins"
        for plugin_id in ("anime-claude-girl", "anime-openai-girl"):
            with self.subTest(plugin_id=plugin_id):
                plugin = ThemePluginLoader.load(plugin_dir / plugin_id)
                self.assertEqual(plugin_id, plugin.plugin_id)
                self.assertTrue(plugin.avatar_data)
                self.assertTrue(plugin.light_qss.strip())
                self.assertTrue(plugin.dark_qss.strip())

    def test_rejects_python_plugin_type(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "python-plugin"
            root.mkdir()
            manifest = self._manifest()
            manifest["type"] = "python"
            self._write_folder(root, manifest)
            with self.assertRaises(ThemePluginError):
                ThemePluginLoader.load(root)


if __name__ == "__main__":
    unittest.main()
