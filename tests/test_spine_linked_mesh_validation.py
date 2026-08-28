from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import unittest

from bile_workbench.spine41_format import parse_file as parse_spine41
from bile_workbench.spine_linked_mesh_validation import validate_linked_mesh_parent
from bile_workbench.spine_workspace import diagnostics_text, static_manifest, load_spine_static_workspace


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "incoming/cross_era_20260822/征2测试/animation/[mini]effect_ui5.bin"
KEY_DIFFERENCE_SOURCE = ROOT / "incoming/cross_era_20260822/征2测试/animation/effect_50170.bin"
SEQUENCE_PARENT_SOURCE = ROOT / "incoming/cross_era_20260822/征2测试/animation/soldier_42001.bin"


@unittest.skipUnless(SOURCE.exists(), "需要用户提供的征2 linked mesh 真实样本")
class SpineLinkedMeshValidationTests(unittest.TestCase):
    def test_real_parent_identity_is_verified_static_only_without_writing(self) -> None:
        before = SOURCE.read_bytes()
        document = parse_spine41(SOURCE)
        self.assertEqual(1, len(document.linked_mesh_evidence))
        linked = document.linked_mesh_evidence[0]
        result = validate_linked_mesh_parent(linked, document.mesh_attachments)
        self.assertEqual("verified_static_identity_only", result.state)
        self.assertEqual("exact_skin_slot_attachment_key_match", result.reason)
        self.assertEqual("Style2", result.resolved_parent_skin)
        self.assertEqual(1, result.matched_parent_count)
        self.assertEqual("forbidden", result.vertex_resolution_state)
        self.assertEqual("forbidden", result.rendering_state)
        self.assertEqual("forbidden", result.writeback)
        self.assertEqual(before, SOURCE.read_bytes())

    @unittest.skipUnless(KEY_DIFFERENCE_SOURCE.exists(), "需要用户提供的 attachment key 与内部 name 不同的征2样本")
    def test_parent_lookup_uses_attachment_key_not_internal_name(self) -> None:
        before = KEY_DIFFERENCE_SOURCE.read_bytes()
        document = parse_spine41(KEY_DIFFERENCE_SOURCE)
        linked = next(item for item in document.linked_mesh_evidence if item.parent_name == "50260_靴子" and item.slot_index == 9)
        parents = [
            item for item in document.mesh_attachments
            if item.skin == linked.parent_skin and item.slot_index == linked.slot_index and item.attachment_key == linked.parent_name
        ]
        self.assertEqual(1, len(parents))
        self.assertNotEqual(linked.parent_name, parents[0].name)
        self.assertEqual("image/50260_靴子", parents[0].name)
        result = validate_linked_mesh_parent(linked, document.mesh_attachments)
        self.assertEqual(("verified_static_identity_only", "exact_skin_slot_attachment_key_match", 1), (result.state, result.reason, result.matched_parent_count))
        self.assertEqual(before, KEY_DIFFERENCE_SOURCE.read_bytes())

    @unittest.skipUnless(SEQUENCE_PARENT_SOURCE.exists(), "需要用户提供的征2 sequence mesh parent 样本")
    def test_sequence_mesh_parent_is_identity_only(self) -> None:
        before = SEQUENCE_PARENT_SOURCE.read_bytes()
        document = parse_spine41(SEQUENCE_PARENT_SOURCE)
        linked = next(item for item in document.linked_mesh_evidence if item.parent_name == "guiqidaoshen_" and item.slot_index == 34)
        sequence_parent = next(
            item for item in document.sequence_evidence
            if item.attachment_kind == "mesh"
            and item.skin == linked.parent_skin
            and item.slot_index == linked.slot_index
            and item.attachment_key == linked.parent_name
        )
        self.assertEqual("mesh", sequence_parent.attachment_kind)
        result = validate_linked_mesh_parent(linked, document.mesh_attachments, document.sequence_evidence)
        self.assertEqual(("verified_static_identity_sequence_mesh_only", "exact_skin_slot_attachment_key_match_sequence_mesh", 1), (result.state, result.reason, result.matched_parent_count))
        self.assertEqual("forbidden", result.vertex_resolution_state)
        self.assertEqual("forbidden", result.rendering_state)
        self.assertEqual(before, SEQUENCE_PARENT_SOURCE.read_bytes())

    def test_workspace_manifest_reports_parent_identity_only(self) -> None:
        before = SOURCE.read_bytes()
        workspace = load_spine_static_workspace(SOURCE)
        payload = static_manifest(workspace)
        validations = payload["attachment_evidence"]["linked_mesh_parent_validations"]
        self.assertEqual(1, len(validations))
        self.assertEqual("verified_static_identity_only", validations[0]["state"])
        self.assertEqual("exact_skin_slot_attachment_key_match", validations[0]["reason"])
        self.assertEqual("forbidden", validations[0]["vertex_resolution_state"])
        self.assertEqual("forbidden", validations[0]["rendering_state"])
        self.assertEqual("forbidden", validations[0]["writeback"])
        self.assertIn("Linked mesh 父级静态身份：普通 mesh 已核验 1", diagnostics_text(workspace))
        self.assertEqual(before, SOURCE.read_bytes())

    def test_missing_or_duplicate_parent_is_rejected(self) -> None:
        document = parse_spine41(SOURCE)
        linked = document.linked_mesh_evidence[0]
        missing = validate_linked_mesh_parent(replace(linked, parent_name="missing-parent"), document.mesh_attachments)
        duplicate = validate_linked_mesh_parent(linked, document.mesh_attachments + document.mesh_attachments)
        self.assertEqual(("candidate_parent_rejected", "parent_attachment_key_not_in_parsed_mesh_subset", 0), (missing.state, missing.reason, missing.matched_parent_count))
        self.assertEqual(("candidate_parent_rejected", "parent_identity_ambiguous", 2), (duplicate.state, duplicate.reason, duplicate.matched_parent_count))


if __name__ == "__main__":
    unittest.main()
