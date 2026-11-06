from __future__ import annotations

import unittest
from pathlib import Path

from bile_workbench.spine38_format import SpineMeshAttachment
from bile_workbench.spine41_timeline import parse_spine41_pose_animation
from bile_workbench.spine_deform_evidence import DeformFrameEvidence, DeformTimelineEvidence
from bile_workbench.spine_unweighted_deform_validation import validate_unweighted_deform_identity_and_span
from external_fixtures import require_files


ROOT = Path(__file__).resolve().parents[1]
ZHENG2 = ROOT / "incoming/cross_era_20260822/征2测试/animation/[mini]form_main1.bin"


def _mesh(vertices: tuple[float, ...] = (0.0, 0.0, 1.0, 1.0), *, weighted: bool = False) -> SpineMeshAttachment:
    return SpineMeshAttachment(
        "default", 2, "mesh", "mesh", 0xFFFFFFFF, (0.0, 0.0, 1.0, 1.0), (0, 1, 1),
        None if weighted else vertices, 0, (((0, 0.0, 0.0, 1.0),),) if weighted else None,
    )


class UnweightedDeformValidationTests(unittest.TestCase):
    def test_accepts_real_zheng2_exact_unweighted_identity_without_projecting(self) -> None:
        require_files(self, ZHENG2, label="private Zheng2 deform sample")
        before = ZHENG2.read_bytes()
        static, animation = parse_spine41_pose_animation(ZHENG2, "Wait")
        meshes = {(mesh.skin, mesh.slot_index, mesh.name): mesh for mesh in static.mesh_attachments if mesh.vertices is not None}
        evidence = next(item for item in animation.deform_evidence if (item.skin, item.slot_index, item.attachment_name) in meshes)
        result = validate_unweighted_deform_identity_and_span(meshes[(evidence.skin, evidence.slot_index, evidence.attachment_name)], evidence)
        self.assertTrue(result.accepted, result)
        self.assertEqual(before, ZHENG2.read_bytes())

    def test_rejects_identity_weighting_alignment_and_span_errors(self) -> None:
        evidence = DeformTimelineEvidence("default", 2, "mesh", (DeformFrameEvidence(0.0, 0, (0.0, 0.0)),))
        self.assertTrue(validate_unweighted_deform_identity_and_span(_mesh(), evidence).accepted)
        self.assertFalse(validate_unweighted_deform_identity_and_span(_mesh(), DeformTimelineEvidence("default", 3, "mesh", evidence.frames)).accepted)
        self.assertFalse(validate_unweighted_deform_identity_and_span(_mesh(weighted=True), evidence).accepted)
        odd_start = DeformTimelineEvidence("default", 2, "mesh", (DeformFrameEvidence(0.0, 1, (0.0, 0.0)),))
        self.assertFalse(validate_unweighted_deform_identity_and_span(_mesh(), odd_start).accepted)
        overflow = DeformTimelineEvidence("default", 2, "mesh", (DeformFrameEvidence(0.0, 2, (0.0, 0.0, 1.0, 1.0)),))
        self.assertFalse(validate_unweighted_deform_identity_and_span(_mesh(), overflow).accepted)


if __name__ == "__main__":
    unittest.main()
