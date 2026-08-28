from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from bile_workbench.spine_two_color_evidence_export import export_two_color_timeline_evidence
from bile_workbench.spine_workspace import create_pose_session, load_spine_static_workspace


ROOT = Path(__file__).resolve().parents[1]
EU7 = ROOT / "incoming/cross_era_20260822/欧7测试/animation/Arthur2.bin"
ZHENG2 = ROOT / "incoming/cross_era_20260822/征2测试/animation/EmpireCityFire01.bin"


@unittest.skipUnless(EU7.exists() and ZHENG2.exists(), "需要用户提供的欧7与征2 two-color 真实样本")
class SpineTwoColorEvidenceExportTests(unittest.TestCase):
    def test_real_zheng2_export_is_hash_bound_deterministic_and_forbidden(self) -> None:
        before = ZHENG2.read_bytes()
        session = create_pose_session(load_spine_static_workspace(ZHENG2), "Wait")
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.json"
            second = Path(directory) / "second.json"
            export_two_color_timeline_evidence(session, first)
            export_two_color_timeline_evidence(session, second)
            self.assertEqual(first.read_text(encoding="utf-8"), second.read_text(encoding="utf-8"))
            payload = json.loads(first.read_text(encoding="utf-8"))
        self.assertEqual(("easytech-spine-two-color-audit/v1", hashlib.sha256(before).hexdigest(), "spine41", "Wait", 4), (payload["schema"], payload["source_sha256"], payload["engine"], payload["animation"], payload["timeline_count"]))
        self.assertEqual((True, "forbidden", "forbidden", "forbidden"), (payload["read_only"], payload["pixel_application"], payload["rendering"], payload["writeback"]))
        self.assertEqual({"rgba2", "rgb2"}, {item["kind"] for item in payload["timelines"]})
        self.assertTrue(all(item["pixel_application_state"] == "forbidden" and item["rendering_state"] == "forbidden" for item in payload["timelines"]))
        self.assertEqual(before, ZHENG2.read_bytes())

    def test_current_eu7_no_two_color_is_explicit_empty_evidence(self) -> None:
        before = EU7.read_bytes()
        session = create_pose_session(load_spine_static_workspace(EU7), "Wait")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "eu7.json"
            export_two_color_timeline_evidence(session, output)
            payload = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(("spine38", 0, []), (payload["engine"], payload["timeline_count"], payload["timelines"]))
        self.assertEqual("forbidden", payload["rendering"])
        self.assertEqual(before, EU7.read_bytes())


if __name__ == "__main__":
    unittest.main()
