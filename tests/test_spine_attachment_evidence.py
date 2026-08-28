from __future__ import annotations

import unittest

from bile_workbench.spine_attachment_evidence import LinkedMeshEvidence, SequenceEvidence, attachment_evidence_status, linked_mesh_is_same_slot


class SpineAttachmentEvidenceTests(unittest.TestCase):
    def test_linked_mesh_same_slot_audit_is_explicit(self) -> None:
        linked = LinkedMeshEvidence("4.1", "default", 7, "variant", "variant", "default", "source", True)
        self.assertTrue(linked_mesh_is_same_slot(linked, 7))
        self.assertFalse(linked_mesh_is_same_slot(linked, 8))

    def test_sequence_evidence_retains_full_frame_range_identity(self) -> None:
        sequence = SequenceEvidence("4.1", "default", 3, "fire", 12, 4, 3, 2)
        self.assertEqual((sequence.count, sequence.start, sequence.digits, sequence.setup_index), (12, 4, 3, 2))

    def test_status_distinguishes_capture_from_runtime_support(self) -> None:
        sequence = SequenceEvidence("4.1", "default", 3, "fire", 12, 4, 3, 2)
        status = attachment_evidence_status((), (sequence,))
        self.assertEqual("not_captured_in_current_sample", status.linked_mesh_state)
        self.assertEqual("captured_static_only", status.sequence_state)
        self.assertEqual("forbidden", status.rendering_state)


if __name__ == "__main__":
    unittest.main()
