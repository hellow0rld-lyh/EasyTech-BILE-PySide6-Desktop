from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import unittest

from bile_workbench.spine_attachment_evidence import SequenceEvidence
from bile_workbench.spine41_format import parse_file as parse_spine41
from bile_workbench.spine41_timeline import parse_spine41_animations
from bile_workbench.spine_sequence_timeline_evidence import SequenceTimelineEvidence, SequenceTimelineFrameEvidence
from bile_workbench.spine_sequence_timeline_time_audit import audit_sequence_region_index_at_time


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "incoming/cross_era_20260822/征2测试/animation/EmpireCityFire01.bin"
NONZERO_START_SOURCE = ROOT / "incoming/cross_era_20260822/征2测试/animation/[mini]form_main3.bin"


def _static(*, count: int = 4, start: int = 10) -> SequenceEvidence:
    return SequenceEvidence("4.1", "default", 2, "display-name", count, start, 5, 0, "sequence-key", "mesh")


def _timeline(*, mode: int, index: int = 1, delay: float = 1.0, time: float = 0.0) -> SequenceTimelineEvidence:
    packed = (index << 4) | mode
    frame = SequenceTimelineFrameEvidence(time, packed, mode, index, delay)
    return SequenceTimelineEvidence("4.1", "audit", "default", 2, "display-name", (frame,), "sequence-key")


class SpineSequenceTimelineTimeAuditTests(unittest.TestCase):
    def test_mode_math_is_audited_without_selecting_images(self) -> None:
        expected = {
            0: ("hold", 0, 1),
            1: ("once", 4, 3),
            2: ("loop", 4, 1),
            3: ("pingpong", 4, 1),
            4: ("once_reverse", 4, 0),
            5: ("loop_reverse", 4, 2),
            6: ("pingpong_reverse", 4, 2),
        }
        for mode, (name, steps, index) in expected.items():
            with self.subTest(mode=name):
                result = audit_sequence_region_index_at_time(_timeline(mode=mode), (_static(),), 4.0)
                self.assertEqual(("audited_region_index_only", name, steps, index), (result.state, result.mode_name, result.elapsed_steps, result.audited_region_index))
                self.assertEqual(10 + index, result.candidate_name_ordinal)
                self.assertEqual("forbidden", result.frame_selection_state)
                self.assertEqual("forbidden", result.attachment_application_state)
                self.assertEqual("forbidden", result.rendering_state)
                self.assertEqual("forbidden", result.writeback)

    @unittest.skipUnless(NONZERO_START_SOURCE.exists(), "需要用户提供的征2非零 sequence start 样本")
    def test_real_nonzero_static_start_is_naming_offset_not_timeline_index_lower_bound(self) -> None:
        before = NONZERO_START_SOURCE.read_bytes()
        static = parse_spine41(NONZERO_START_SOURCE)
        archive = parse_spine41_animations(NONZERO_START_SOURCE)
        timeline = next(
            item
            for animation in archive.animations if animation.name == "Cast"
            for item in animation.sequence_timeline_evidence
            if item.slot_index == 2 and item.attachment_key == "封面流焰2-baopo1_"
        )
        result = audit_sequence_region_index_at_time(timeline, static.sequence_evidence, timeline.frames[0].time)
        self.assertEqual((54, 39, 0, "once", 0, 54), (result.static_start, result.static_count, result.base_region_index, result.mode_name, result.audited_region_index, result.candidate_name_ordinal))
        self.assertEqual("audited_region_index_only", result.state)
        self.assertEqual("forbidden", result.frame_selection_state)
        self.assertEqual(before, NONZERO_START_SOURCE.read_bytes())

    def test_rejects_inputs_requiring_runtime_context_or_invalid_data(self) -> None:
        timeline = _timeline(mode=2)
        self.assertEqual("time_before_first_key_requires_runtime_blend_context", audit_sequence_region_index_at_time(replace(timeline, frames=(replace(timeline.frames[0], time=1.0),)), (_static(),), 0.5).reason)
        self.assertEqual("non_hold_mode_requires_positive_finite_delay", audit_sequence_region_index_at_time(_timeline(mode=2, delay=0.0), (_static(),), 1.0).reason)
        self.assertEqual("mode_ordinal_out_of_official_range", audit_sequence_region_index_at_time(_timeline(mode=7), (_static(),), 1.0).reason)
        self.assertEqual("static_attachment_key_must_match_exactly_once", audit_sequence_region_index_at_time(timeline, (), 1.0).reason)
        self.assertEqual("base_region_index_outside_static_count", audit_sequence_region_index_at_time(_timeline(mode=0, index=4), (_static(),), 1.0).reason)

    @unittest.skipUnless(SOURCE.exists(), "需要用户提供的征2 sequence timeline 真实样本")
    def test_real_zheng2_loop_math_is_a_region_index_audit_only(self) -> None:
        before = SOURCE.read_bytes()
        static = parse_spine41(SOURCE)
        timeline = parse_spine41_animations(SOURCE).animations[0].sequence_timeline_evidence[0]
        result = audit_sequence_region_index_at_time(timeline, static.sequence_evidence, 0.1)
        self.assertEqual(("audited_region_index_only", "loop", 1, 1, 1), (result.state, result.mode_name, result.elapsed_steps, result.audited_region_index, result.candidate_name_ordinal))
        self.assertEqual("forbidden", result.frame_selection_state)
        self.assertEqual("forbidden", result.attachment_application_state)
        self.assertEqual("forbidden", result.rendering_state)
        self.assertEqual(before, SOURCE.read_bytes())


if __name__ == "__main__":
    unittest.main()
