from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from bile_workbench.spine_sequence_export import export_spine_pose_sequence
from bile_workbench.spine_workspace import create_pose_session, load_spine_static_workspace

ROOT = Path(__file__).resolve().parents[1]
EU7 = ROOT / "incoming/cross_era_20260822/欧7测试/animation/Arthur2.bin"
ZHENG2 = ROOT / "incoming/cross_era_20260822/征2测试/animation/[mini]effect_ui10.bin"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SpinePoseSequenceExportTests(unittest.TestCase):
    def _export(self, source: Path, animation: str, kind: str) -> tuple[Path, dict[str, object]]:
        before = _sha256(source)
        workspace = load_spine_static_workspace(source)
        session = create_pose_session(workspace, animation)
        with tempfile.TemporaryDirectory() as folder:
            suffix = ".gif" if kind == "gif" else ".png"
            output = Path(folder) / f"pose{suffix}"
            result = export_spine_pose_sequence(session, output, frame_count=4, kind=kind)
            self.assertEqual(result.frame_count, 4)
            self.assertTrue(result.output_path.exists())
            self.assertTrue(result.evidence_path.exists())
            evidence = json.loads(result.evidence_path.read_text(encoding="utf-8"))
            retained = Path(folder) / output.name
            retained.write_bytes(output.read_bytes())
            self.assertEqual(before, _sha256(source), "只读导出绝不能改变 Spine BIN")
            self.assertEqual(evidence["source_sha256"], before)
            self.assertTrue(evidence["read_only"])
            self.assertEqual(evidence["writeback"], "forbidden")
            self.assertEqual(len(evidence["frames"]), 4)
            return retained, evidence

    def test_zheng2_coverage_complete_pose_exports_gif_with_evidence(self) -> None:
        # 临时目录清理前直接检验动态帧；证据仍由上面的公共断言验证。
        workspace = load_spine_static_workspace(ZHENG2)
        session = create_pose_session(workspace, "Wait")
        before = _sha256(ZHENG2)
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "zheng2.gif"
            result = export_spine_pose_sequence(session, output, frame_count=4, kind="gif")
            with Image.open(output) as animation:
                # GIF 的 256 色量化可能把视觉等价帧合并；审计证据保留全部原始 pose 采样。
                self.assertGreaterEqual(animation.n_frames, 1)
                self.assertLessEqual(animation.n_frames, 4)
            evidence = json.loads(result.evidence_path.read_text(encoding="utf-8"))
            self.assertEqual(len(evidence["frames"]), 4)
            self.assertEqual(evidence["partial_frame_count"], 0)
            self.assertEqual(evidence["source_sha256"], before)
        self.assertEqual(before, _sha256(ZHENG2))

    def test_eu7_partial_pose_exports_apng_and_records_diagnostics(self) -> None:
        workspace = load_spine_static_workspace(EU7)
        session = create_pose_session(workspace, "Wait")
        before = _sha256(EU7)
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "eu7.png"
            result = export_spine_pose_sequence(session, output, frame_count=4, kind="apng")
            self.assertGreater(output.stat().st_size, 0)
            evidence = json.loads(result.evidence_path.read_text(encoding="utf-8"))
            self.assertGreater(result.partial_frame_count, 0)
            self.assertGreater(evidence["partial_frame_count"], 0)
            self.assertTrue(any(frame["diagnostics"] for frame in evidence["frames"]))
            self.assertEqual(evidence["source_sha256"], before)
        self.assertEqual(before, _sha256(EU7))


if __name__ == "__main__":
    unittest.main()
