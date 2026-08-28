from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path

from bile_workbench.spine38_format import parse_file as parse_spine38
from bile_workbench.spine41_format import parse_file as parse_spine41
from bile_workbench.spine38_timeline import parse_spine38_animations
from bile_workbench.spine41_timeline import parse_spine41_animations
from bile_workbench.spine_atlas import load_spine_atlas, render_region
from bile_workbench.spine_workspace import diagnostics_text, export_static_manifest, load_spine_static_workspace

ROOT = Path(__file__).resolve().parents[1]
EU7_BIN = ROOT / "incoming/cross_era_20260822/欧7测试/animation/Arthur2.bin"
EU7_ATLAS = EU7_BIN.with_suffix(".atlas")
ZHENG2_BIN = ROOT / "incoming/cross_era_20260822/征2测试/animation/EmpireCityFire01.bin"
ZHENG2_ATLAS = ZHENG2_BIN.with_suffix(".atlas")


@unittest.skipUnless(EU7_BIN.exists() and ZHENG2_BIN.exists(), "需要用户提供的欧7/征2真实样本")
class SpineNewEngineTests(unittest.TestCase):
    def test_eu7_spine38_static_prefix_and_skins(self) -> None:
        document = parse_spine38(EU7_BIN)
        self.assertEqual("3.8.99", document.header.version)
        self.assertEqual(15, len(document.bones))
        self.assertEqual(11, len(document.slots))
        self.assertGreater(document.static_end, 1000)
        self.assertGreater(document.undecoded_tail_bytes, 0)
        self.assertGreaterEqual(len(document.region_attachments), 9)
        self.assertTrue(all(item.path for item in document.region_attachments))
        self.assertEqual(document.ik_constraint_count, len(document.ik_constraints))
        self.assertEqual(document.transform_constraint_count, len(document.transform_constraints))
        self.assertTrue(all(item.bones and 0 <= item.target < len(document.bones) for item in document.ik_constraints))
        self.assertTrue(all(item.bones and 0 <= item.target < len(document.bones) for item in document.transform_constraints))
        self.assertEqual(1, len(document.mesh_attachments))
        self.assertIsNone(document.mesh_attachments[0].vertices)
        self.assertGreater(len(document.mesh_attachments[0].triangles), 0)
        influences = document.mesh_attachments[0].weighted_vertices
        self.assertIsNotNone(influences)
        assert influences is not None
        self.assertTrue(all(vertex for vertex in influences))
        self.assertTrue(all(0 <= bone < len(document.bones) and weight >= 0.0 for vertex in influences for bone, _, _, weight in vertex))
        self.assertEqual((), document.linked_mesh_evidence)

    def test_eu7_spine38_full_animation_consumption(self) -> None:
        archive = parse_spine38_animations(EU7_BIN)
        self.assertEqual(archive.animation_end, EU7_BIN.stat().st_size)
        self.assertEqual(1, len(archive.animations))
        self.assertEqual(49, len(archive.animations[0].timelines))
        self.assertGreater(archive.animations[0].duration, 0.0)
        kinds = archive.timeline_type_counts
        self.assertIn("bone:rotate", kinds)
        self.assertIn("bone:translate", kinds)
        self.assertIn("slot:attachment", kinds)

    def test_zheng2_spine41_long_hash_static_prefix_and_skins(self) -> None:
        document = parse_spine41(ZHENG2_BIN)
        self.assertEqual("4.1.24", document.header.version)
        self.assertEqual(13, len(document.bones))
        self.assertEqual(10, len(document.slots))
        self.assertGreater(document.static_end, 4000)
        self.assertGreater(document.undecoded_tail_bytes, 0)
        self.assertEqual(document.ik_constraint_count, len(document.ik_constraints))
        self.assertEqual(document.transform_constraint_count, len(document.transform_constraints))
        self.assertTrue(all(item.bend_direction in (-1, 1) for item in document.ik_constraints))
        self.assertTrue(all(item.bones and 0 <= item.target < len(document.bones) for item in document.transform_constraints))
        self.assertEqual(3, len(document.mesh_attachments))
        self.assertTrue(all(item.vertices is not None and len(item.uvs) == len(item.vertices) and len(item.triangles) % 3 == 0 for item in document.mesh_attachments))
        self.assertTrue(document.sequence_evidence)
        self.assertTrue(all(item.count > 0 and item.digits >= 0 for item in document.sequence_evidence))
        self.assertEqual((), document.linked_mesh_evidence)

    def test_atlas_dialects_and_rotation_preview(self) -> None:
        eu7 = load_spine_atlas(EU7_ATLAS)
        zheng2 = load_spine_atlas(ZHENG2_ATLAS)
        self.assertEqual("xy-size-orig-offset", eu7.dialect)
        self.assertEqual("bounds-offsets", zheng2.dialect)
        self.assertEqual((176, 176), render_region(eu7, "剑").size)
        self.assertEqual((180, 180), render_region(zheng2, "images/火焰序列/火焰序列-4_00000").size)

    def test_zheng2_spine41_full_animation_consumption(self) -> None:
        archive = parse_spine41_animations(ZHENG2_BIN)
        self.assertEqual(archive.animation_end, ZHENG2_BIN.stat().st_size)
        self.assertEqual(1, len(archive.animations))
        self.assertEqual(52, len(archive.animations[0].timelines))
        self.assertGreater(archive.animations[0].duration, 0.0)
        kinds = archive.timeline_type_counts
        self.assertIn("slot:rgba", kinds)
        self.assertIn("attachment:deform", kinds)
        self.assertIn("attachment:sequence", kinds)

    def test_zheng2_spine41_sequence_timeline_evidence_is_raw_and_forbidden(self) -> None:
        before = ZHENG2_BIN.read_bytes()
        document = parse_spine41(ZHENG2_BIN)
        archive = parse_spine41_animations(ZHENG2_BIN)
        evidence = archive.animations[0].sequence_timeline_evidence
        static_identities = {(item.skin, item.slot_index, item.name) for item in document.sequence_evidence}
        self.assertTrue(evidence)
        self.assertTrue(all(item.spine_version == "4.1" and item.animation == "Wait" for item in evidence))
        self.assertTrue(all(item.frames and item.selection_state == "forbidden" and item.rendering_state == "forbidden" for item in evidence))
        for timeline in evidence:
            self.assertIn((timeline.skin, timeline.slot_index, timeline.attachment_name), static_identities)
            self.assertEqual(list(timeline.frames), sorted(timeline.frames, key=lambda item: item.time))
            for frame in timeline.frames:
                self.assertTrue(math.isfinite(frame.time))
                self.assertTrue(math.isfinite(frame.delay))
                self.assertEqual(frame.mode_ordinal, frame.mode_and_index & 0xF)
                self.assertEqual(frame.sequence_index, frame.mode_and_index >> 4)
                self.assertIn(frame.mode_ordinal, range(5))
        self.assertEqual(before, ZHENG2_BIN.read_bytes())

    def test_read_only_workspace_manifest(self) -> None:
        before = ZHENG2_BIN.read_bytes()
        workspace = load_spine_static_workspace(ZHENG2_BIN)
        self.assertEqual("spine41", workspace.engine)
        self.assertIn("linked mesh 0 [not_captured_in_current_sample]", diagnostics_text(workspace))
        self.assertIn("sequence", diagnostics_text(workspace))
        self.assertIn("captured_static_only", diagnostics_text(workspace))
        self.assertIn("仅审计，不渲染", diagnostics_text(workspace))
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "spine-static.json"
            export_static_manifest(workspace, output)
            payload = json.loads(output.read_text(encoding="utf-8"))
        self.assertTrue(payload["read_only"])
        self.assertEqual("forbidden", payload["writeback"])
        self.assertEqual("spine41", payload["engine"])
        self.assertIsNotNone(payload["timeline_document"])
        self.assertTrue(payload["attachment_evidence"]["sequences"])
        self.assertEqual([], payload["attachment_evidence"]["linked_meshes"])
        self.assertIn("forbidden", payload["attachment_evidence"]["rendering"])
        self.assertEqual("not_captured_in_current_sample", payload["attachment_evidence"]["status"]["linked_mesh_state"])
        self.assertEqual("captured_static_only", payload["attachment_evidence"]["status"]["sequence_state"])
        self.assertEqual("forbidden", payload["attachment_evidence"]["status"]["rendering_state"])
        validations = payload["attachment_evidence"]["sequence_atlas_validations"]
        self.assertTrue(validations)
        self.assertTrue(all(item["state"] == "candidate_range_verified_static_only" for item in validations))
        self.assertTrue(all(item["rendering_state"] == "forbidden" for item in validations))
        timeline_evidence = payload["attachment_evidence"]["sequence_timeline_evidence"]
        self.assertTrue(timeline_evidence)
        self.assertEqual("forbidden", payload["attachment_evidence"]["selection"])
        self.assertTrue(all(item["selection_state"] == "forbidden" for item in timeline_evidence))
        self.assertTrue(all(item["rendering_state"] == "forbidden" for item in timeline_evidence))
        static_validations = payload["attachment_evidence"]["sequence_timeline_static_validations"]
        self.assertTrue(static_validations)
        self.assertTrue(all(item["state"] == "timeline_static_identity_verified_raw_region_index_observed_only" for item in static_validations))
        self.assertTrue(all(item["reason"] == "raw_indices_within_sequence_region_range_only" for item in static_validations))
        self.assertTrue(all(item["selection_state"] == "forbidden" and item["rendering_state"] == "forbidden" for item in static_validations))
        self.assertTrue(all(not item["raw_indices_outside_sequence_region_range"] for item in static_validations))
        self.assertIn("mode/index/delay", diagnostics_text(workspace))
        self.assertIn("Sequence timeline–static range", diagnostics_text(workspace))
        self.assertTrue(payload["timeline_document"]["full_file_consumption"])
        self.assertEqual(1, len(payload["timeline_document"]["animations"]))
        self.assertIn("constraints", payload["boundary"]["not_decoded"])
        self.assertIn("cubic Bezier", payload["boundary"]["pose_preview"])
        self.assertEqual(before, ZHENG2_BIN.read_bytes())
        self.assertIn("draw-order", payload["boundary"]["pose_preview"])


if __name__ == "__main__":
    unittest.main()
