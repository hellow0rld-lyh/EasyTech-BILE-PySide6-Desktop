from __future__ import annotations

from pathlib import Path
import unittest

from bile_workbench.spine38_timeline import parse_spine38_pose_animation
from bile_workbench.spine41_timeline import parse_spine41_pose_animation
from bile_workbench.spine_pose import PoseAnimation, PoseFrame, PoseTrack
from bile_workbench.spine_two_color_evidence import collect_two_color_timeline_evidence


ROOT = Path(__file__).resolve().parents[1]
EU7 = ROOT / "incoming/cross_era_20260822/欧7测试/animation/Empress Matilda2.bin"
ZHENG2 = ROOT / "incoming/cross_era_20260822/征2测试/animation/EmpireCityFire01.bin"


@unittest.skipUnless(EU7.exists() and ZHENG2.exists(), "需要用户提供的欧7与征2 two-color 真实样本")
class SpineTwoColorEvidenceTests(unittest.TestCase):
    def test_real_zheng2_rgba2_rgb2_evidence_is_raw_and_rendering_forbidden(self) -> None:
        before = ZHENG2.read_bytes()
        _, animation = parse_spine41_pose_animation(ZHENG2, "Wait")
        evidence = collect_two_color_timeline_evidence("4.1", animation)
        self.assertEqual(4, len(evidence))
        self.assertEqual({"rgba2", "rgb2"}, {item.kind for item in evidence})
        rgba2 = next(item for item in evidence if item.kind == "rgba2")
        self.assertEqual(("images/火焰序列/火焰序列-2_00002", 1, 4, 3), (rgba2.slot_name, len(rgba2.frames), len(rgba2.frames[0].light_components), len(rgba2.frames[0].dark_rgb)))
        self.assertEqual(("forbidden", "forbidden", "forbidden"), (rgba2.pixel_application_state, rgba2.rendering_state, rgba2.writeback))
        self.assertEqual(before, ZHENG2.read_bytes())

    def test_current_eu7_sample_has_no_two_color_evidence_without_fallback(self) -> None:
        before = EU7.read_bytes()
        _, animation = parse_spine38_pose_animation(EU7, "Wait")
        self.assertEqual((), collect_two_color_timeline_evidence("3.8", animation))
        self.assertEqual(before, EU7.read_bytes())

    def test_invalid_two_color_values_are_rejected(self) -> None:
        invalid = PoseAnimation(
            "synthetic",
            0.0,
            (PoseTrack("slot", "rgb2", 0, "slot", (PoseFrame(0.0, (1.0, 1.0, "invalid", 0.0, 0.0, 0.0)),)),),
            (),
        )
        with self.assertRaisesRegex(ValueError, "raw 通道数量或类型无效"):
            collect_two_color_timeline_evidence("4.1", invalid)


if __name__ == "__main__":
    unittest.main()
