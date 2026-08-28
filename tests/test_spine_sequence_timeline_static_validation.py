from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import unittest

from bile_workbench.spine41_format import parse_file as parse_spine41
from bile_workbench.spine41_timeline import parse_spine41_animations
from bile_workbench.spine_sequence_timeline_static_validation import validate_sequence_timeline_static_range


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "incoming/cross_era_20260822/征2测试/animation/EmpireCityFire01.bin"


@unittest.skipUnless(SOURCE.exists(), "需要用户提供的征2 sequence timeline 真实样本")
class SpineSequenceTimelineStaticValidationTests(unittest.TestCase):
    def test_real_timeline_keys_bind_static_sequence_and_observe_raw_span(self) -> None:
        before = SOURCE.read_bytes()
        static = parse_spine41(SOURCE)
        archive = parse_spine41_animations(SOURCE)
        timelines = archive.animations[0].sequence_timeline_evidence
        results = tuple(validate_sequence_timeline_static_range(item, static.sequence_evidence) for item in timelines)
        self.assertTrue(results)
        self.assertTrue(all(item.state == "timeline_static_identity_verified_raw_region_index_observed_only" for item in results))
        self.assertTrue(all(item.reason == "raw_indices_within_sequence_region_range_only" for item in results))
        self.assertTrue(all(item.static_attachment_kind == "mesh" for item in results))
        self.assertTrue(all(item.static_start == 0 and item.static_count == 16 for item in results))
        self.assertTrue(all(not item.raw_indices_outside_sequence_region_range for item in results))
        self.assertTrue(all(item.selection_state == "forbidden" and item.rendering_state == "forbidden" and item.writeback == "forbidden" for item in results))
        self.assertEqual(before, SOURCE.read_bytes())

    def test_missing_static_key_and_outside_raw_index_remain_audit_states(self) -> None:
        static = parse_spine41(SOURCE)
        timeline = parse_spine41_animations(SOURCE).animations[0].sequence_timeline_evidence[0]
        missing = validate_sequence_timeline_static_range(replace(timeline, attachment_key="missing"), static.sequence_evidence)
        self.assertEqual(("timeline_static_attachment_rejected", "static_attachment_key_not_captured"), (missing.state, missing.reason))
        first = timeline.frames[0]
        outside_index = 16
        outside_frame = replace(first, mode_and_index=(outside_index << 4) | first.mode_ordinal, sequence_index=outside_index)
        outside_timeline = replace(timeline, frames=(outside_frame,) + timeline.frames[1:])
        outside = validate_sequence_timeline_static_range(outside_timeline, static.sequence_evidence)
        self.assertEqual(("timeline_static_identity_verified_raw_region_index_outside_only", "raw_index_outside_sequence_region_range", (outside_index,)), (outside.state, outside.reason, outside.raw_indices_outside_sequence_region_range))
        self.assertEqual("forbidden", outside.selection_state)
        self.assertEqual("forbidden", outside.rendering_state)


if __name__ == "__main__":
    unittest.main()
