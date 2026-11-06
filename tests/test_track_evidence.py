"""局部轨道影响范围取证的真实 BILE 回归测试。"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bile_workbench.bile_format import parse_file
from bile_workbench.track_context import tracks_for_animation
from bile_workbench.track_evidence import build_track_impact_evidence, write_track_impact_evidence
from external_fixtures import require_files


class TrackEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        sample = ROOT / "sample_assets" / "anim_failure.bin"
        require_files(self, sample, label="private BILE track evidence sample")
        self.document = parse_file(sample)
        self.context = tracks_for_animation(self.document, self.document.animations[0].index)[0]

    def test_builds_static_reference_scope_for_real_bele(self) -> None:
        evidence = build_track_impact_evidence(self.document, [self.context.keyframe_index])
        self.assertEqual(len(evidence.impacts), 1)
        impact = evidence.impacts[0]
        self.assertEqual(impact.keyframe_index, self.context.keyframe_index)
        self.assertIn(self.context, impact.contexts)
        self.assertIn(self.context.animation_name, impact.animation_names)
        self.assertIn("静态引用", evidence.markdown())

    def test_writes_json_and_markdown_for_changed_and_unreferenced_keys(self) -> None:
        unreferenced = next(index for index in range(len(self.document.keyframes)) if index != self.context.keyframe_index)
        with tempfile.TemporaryDirectory() as temp:
            evidence = write_track_impact_evidence(self.document, [self.context.keyframe_index, unreferenced], temp)
            self.assertTrue(evidence.json_path and evidence.json_path.exists())
            self.assertTrue(evidence.markdown_path and evidence.markdown_path.exists())
            payload = json.loads(evidence.json_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["kind"], "bile_track_impact_evidence")
            self.assertEqual(len(payload["keyframes"]), 2)
            self.assertIn("BELE", evidence.markdown_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
