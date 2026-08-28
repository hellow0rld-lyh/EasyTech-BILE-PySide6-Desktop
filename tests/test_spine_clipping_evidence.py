from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import unittest

from bile_workbench.spine38_format import parse_file as parse_spine38
from bile_workbench.spine41_format import parse_file as parse_spine41
from bile_workbench.spine_clipping_validation import validate_clipping_static_boundary
from bile_workbench.spine_workspace import diagnostics_text, load_spine_static_workspace, static_manifest


ROOT = Path(__file__).resolve().parents[1]
EU7 = ROOT / "incoming/cross_era_20260822/欧7测试/animation/Arthur2.bin"
ZHENG2 = ROOT / "incoming/cross_era_20260822/征2测试/animation/[mini]form_main1.bin"


@unittest.skipUnless(EU7.exists() and ZHENG2.exists(), "需要用户提供的欧7与征2 clipping 真实样本")
class SpineClippingEvidenceTests(unittest.TestCase):
    def test_real_38_and_41_clipping_evidence_is_static_only(self) -> None:
        before38 = EU7.read_bytes()
        before41 = ZHENG2.read_bytes()
        document38 = parse_spine38(EU7)
        document41 = parse_spine41(ZHENG2)
        item38 = next(item for item in document38.clipping_evidence if item.attachment_key == "root")
        item41 = next(item for item in document41.clipping_evidence if item.attachment_key == "cq")
        self.assertEqual(("3.8", 3, 4, 4), (item38.spine_version, item38.slot_index, item38.end_slot_index, item38.vertex_count))
        self.assertEqual(("4.1", 0, 82, 4), (item41.spine_version, item41.slot_index, item41.end_slot_index, item41.vertex_count))
        for item, slots in ((item38, document38.slots), (item41, document41.slots)):
            validation = validate_clipping_static_boundary(item, slots)
            self.assertEqual(("clipping_static_boundary_verified_only", "forbidden", "forbidden", "forbidden"), (validation.state, validation.vertex_application_state, validation.clipping_rendering_state, validation.writeback))
        self.assertEqual(before38, EU7.read_bytes())
        self.assertEqual(before41, ZHENG2.read_bytes())

    def test_invalid_boundary_is_rejected_without_fallback(self) -> None:
        document = parse_spine41(ZHENG2)
        item = next(item for item in document.clipping_evidence if item.attachment_key == "cq")
        invalid_end = validate_clipping_static_boundary(replace(item, end_slot_index=len(document.slots)), document.slots)
        invalid_vertices = validate_clipping_static_boundary(replace(item, vertex_count=0), document.slots)
        self.assertEqual(("clipping_static_boundary_rejected", "end_slot_index_out_of_range"), (invalid_end.state, invalid_end.reason))
        self.assertEqual(("clipping_static_boundary_rejected", "vertex_count_must_be_positive"), (invalid_vertices.state, invalid_vertices.reason))
        self.assertEqual("forbidden", invalid_end.clipping_rendering_state)

    def test_workspace_manifest_and_diagnostics_export_clipping_evidence_only(self) -> None:
        before = ZHENG2.read_bytes()
        workspace = load_spine_static_workspace(ZHENG2)
        manifest = static_manifest(workspace)
        evidence = manifest["attachment_evidence"]
        self.assertTrue(evidence["clippings"])
        self.assertTrue(evidence["clipping_static_validations"])
        self.assertTrue(all(item["state"] == "clipping_static_boundary_verified_only" for item in evidence["clipping_static_validations"]))
        self.assertEqual("forbidden; evidence-only metadata does not select frames, render linked mesh/sequence attachments, or apply clipping", evidence["rendering"])
        self.assertIn("Clipping 静态边界：已核验", diagnostics_text(workspace))
        self.assertEqual(before, ZHENG2.read_bytes())


if __name__ == "__main__":
    unittest.main()
