"""工作区状态和 UI 服务中的纯数据投影测试。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bile_workbench.bile_format import parse_file
from bile_workbench.formation_config import parse_def_array_bytes
from bile_workbench.preview_renderer import load_atlas
from bile_workbench.ui_experiment_dialogs import format_formation_summary
from bile_workbench.workbench_state import Workspace
from external_fixtures import require_files


class WorkbenchStateTests(unittest.TestCase):
    def test_workspace_preserves_triplet_and_parsed_snapshot(self) -> None:
        assets = ROOT / "sample_assets"
        binary = assets / "anim_failure.bin"
        xml = assets / "anim_failure.xml"
        image = assets / "anim_failure.webp"
        require_files(self, binary, xml, image, label="private BILE workbench triplet")
        workspace = Workspace.create(binary, xml, image, parse_file(binary), load_atlas(xml, image))
        self.assertEqual(workspace.bin_path, binary)
        self.assertEqual(workspace.xml_path, xml)
        self.assertEqual(workspace.image_path, image)
        self.assertGreater(len(workspace.document.animations), 0)
        self.assertEqual(workspace.triplet.bin_sha256, workspace.triplet.bin_sha256)

    def test_formation_summary_is_a_pure_readonly_projection(self) -> None:
        config = parse_def_array_bytes(
            b"<Arrays><Array name='Default' n='1'><Pos soldier='0,0' special='0,0,4,4'/></Array></Arrays>",
            "def_array.xml",
        )
        text = format_formation_summary(config)
        self.assertIn("def_array.xml", text)
        self.assertIn("Array Default", text)
        self.assertIn("primary=[1]", text)
        self.assertIn("special=[2]", text)
        self.assertIn("只读", text)


if __name__ == "__main__":
    unittest.main()
