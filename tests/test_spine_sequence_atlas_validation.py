from __future__ import annotations

import unittest
from pathlib import Path

from bile_workbench.spine_atlas import SpineAtlasRegion, load_spine_atlas
from bile_workbench.spine41_format import parse_file as parse_spine41
from bile_workbench.spine_sequence_atlas_validation import validate_sequence_atlas_candidates

ROOT = Path(__file__).resolve().parents[1]
ZHENG2 = ROOT / "incoming/cross_era_20260822/征2测试/animation/EmpireCityFire01.bin"


@unittest.skipUnless(ZHENG2.exists(), "需要用户提供的征2 sequence 真实样本")
class SpineSequenceAtlasValidationTests(unittest.TestCase):
    def test_real_sequence_static_range_matches_atlas_without_rendering(self) -> None:
        before = ZHENG2.read_bytes()
        document = parse_spine41(ZHENG2)
        atlas = load_spine_atlas(ZHENG2.with_suffix(".atlas"))
        evidence = next(item for item in document.sequence_evidence if item.name == "images/火焰序列/火焰序列-4_")
        result = validate_sequence_atlas_candidates(evidence, atlas.regions)
        self.assertEqual("candidate_range_verified_static_only", result.state)
        self.assertEqual(16, len(result.matched_region_names))
        self.assertEqual((), result.missing_region_names)
        self.assertEqual("forbidden", result.rendering_state)
        self.assertEqual(before, ZHENG2.read_bytes())

    def test_missing_and_duplicate_names_are_rejected(self) -> None:
        document = parse_spine41(ZHENG2)
        evidence = next(item for item in document.sequence_evidence if item.name == "images/火焰序列/火焰序列-4_")
        region = SpineAtlasRegion(f"{evidence.name}00000", 0, 0, 1, 1, 1, 1, 0, 0, 0, -1)
        result = validate_sequence_atlas_candidates(evidence, (region, region))
        self.assertEqual("candidate_range_rejected", result.state)
        self.assertTrue(result.missing_region_names)
        self.assertEqual((f"{evidence.name}00000",), result.duplicate_region_names)


if __name__ == "__main__":
    unittest.main()
