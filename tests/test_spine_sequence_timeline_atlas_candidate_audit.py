from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import unittest

from bile_workbench.spine_atlas import SpineAtlasRegion, load_spine_atlas
from bile_workbench.spine41_format import parse_file as parse_spine41
from bile_workbench.spine41_timeline import parse_spine41_animations
from bile_workbench.spine_sequence_timeline_atlas_candidate_audit import audit_sequence_candidate_name_at_time


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "incoming/cross_era_20260822/征2测试/animation/[mini]form_main3.bin"


@unittest.skipUnless(SOURCE.exists(), "需要用户提供的征2非零 sequence start 样本")
class SpineSequenceTimelineAtlasCandidateAuditTests(unittest.TestCase):
    def _inputs(self):
        document = parse_spine41(SOURCE)
        archive = parse_spine41_animations(SOURCE)
        timeline = next(
            item
            for animation in archive.animations if animation.name == "Cast"
            for item in animation.sequence_timeline_evidence
            if item.slot_index == 2 and item.attachment_key == "封面流焰2-baopo1_"
        )
        return document, timeline, load_spine_atlas(SOURCE.with_suffix(".atlas"))

    def test_real_nonzero_start_audits_unique_candidate_name_without_frame_selection(self) -> None:
        before = SOURCE.read_bytes()
        document, timeline, atlas = self._inputs()
        result = audit_sequence_candidate_name_at_time(timeline, document.sequence_evidence, atlas.regions, timeline.frames[0].time)
        self.assertEqual(("candidate_name_identity_verified_static_only", "封面流焰2-baopo1_00054", 1), (result.state, result.candidate_region_name, result.atlas_name_match_count))
        self.assertEqual("forbidden", result.frame_selection_state)
        self.assertEqual("forbidden", result.image_sampling_state)
        self.assertEqual("forbidden", result.attachment_application_state)
        self.assertEqual("forbidden", result.rendering_state)
        self.assertEqual("forbidden", result.writeback)
        self.assertEqual(before, SOURCE.read_bytes())

    def test_static_range_and_candidate_name_rejections_do_not_fallback(self) -> None:
        document, timeline, atlas = self._inputs()
        static = next(item for item in document.sequence_evidence if item.slot_index == timeline.slot_index and item.attachment_key == timeline.attachment_key)
        missing_range = audit_sequence_candidate_name_at_time(timeline, (replace(static, count=0),), atlas.regions, timeline.frames[0].time)
        self.assertEqual(("candidate_name_audit_rejected", "time_audit_static_sequence_count_must_be_positive"), (missing_range.state, missing_range.reason))
        candidate = f"{static.name}{static.start:0{static.digits}d}"
        duplicate = SpineAtlasRegion(candidate, 0, 0, 1, 1, 1, 1, 0, 0, 0, -1)
        duplicate_result = audit_sequence_candidate_name_at_time(timeline, (static,), (duplicate, duplicate), timeline.frames[0].time)
        self.assertEqual(("candidate_name_audit_rejected", "static_candidate_range_not_verified"), (duplicate_result.state, duplicate_result.reason))
        self.assertEqual("forbidden", duplicate_result.frame_selection_state)
        self.assertEqual("forbidden", duplicate_result.rendering_state)


if __name__ == "__main__":
    unittest.main()
