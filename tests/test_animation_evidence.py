from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from bile_workbench.animation_evidence import build_animation_evidence, write_animation_evidence
from bile_workbench.bile_format import parse_file


class AnimationEvidenceTests(unittest.TestCase):
    def test_builds_static_slot_coverage_and_keyframe_reuse_audit(self) -> None:
        document = parse_file(ROOT / "sample_assets" / "anim_failure.bin")
        animation = document.animations[0]
        evidence = build_animation_evidence(document, animation.index)

        self.assertEqual(evidence.animation_name, animation.name)
        self.assertEqual(len(evidence.coverage), animation.frame_count)
        self.assertEqual(evidence.channel_count, len(animation.channels))
        self.assertGreater(evidence.static_track_count, 0)
        self.assertGreater(evidence.unique_keyframe_count, 0)
        self.assertTrue(any(row.active_track_count for row in evidence.coverage))
        for reuse in evidence.keyframe_reuse:
            self.assertGreaterEqual(reuse.document_track_count, reuse.current_animation_track_count)
            self.assertGreaterEqual(reuse.document_animation_count, 1)

    def test_writes_machine_and_human_readable_static_evidence(self) -> None:
        document = parse_file(ROOT / "sample_assets" / "anim_failure.bin")
        animation = document.animations[0]
        with tempfile.TemporaryDirectory() as temporary:
            evidence = write_animation_evidence(document, animation.index, temporary)
            assert evidence.json_path is not None
            assert evidence.markdown_path is not None
            self.assertTrue(evidence.json_path.exists())
            self.assertTrue(evidence.markdown_path.exists())
            payload = json.loads(evidence.json_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema"], "bile-workbench.animation-evidence/v1")
            self.assertIn("static parsed track references", payload["scope"])
            self.assertEqual(len(payload["slot_coverage"]), animation.frame_count)
            markdown = evidence.markdown_path.read_text(encoding="utf-8")
            self.assertIn("不等同于游戏内单位人数", markdown)
            self.assertIn("BELE 复用警戒", markdown)


if __name__ == "__main__":
    unittest.main()
