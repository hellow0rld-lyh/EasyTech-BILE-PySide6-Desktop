from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from bile_workbench.spine_sequence_timeline_time_evidence_export import export_sequence_time_audit_evidence
from bile_workbench.spine_workspace import load_spine_static_workspace


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "incoming/cross_era_20260822/征2测试/animation/EmpireCityFire01.bin"


@unittest.skipUnless(SOURCE.exists(), "需要用户提供的征2 sequence timeline 真实样本")
class SpineSequenceTimelineTimeEvidenceExportTests(unittest.TestCase):
    def test_export_is_hash_bound_deterministic_and_forbids_frame_selection(self) -> None:
        before = SOURCE.read_bytes()
        workspace = load_spine_static_workspace(SOURCE)
        with tempfile.TemporaryDirectory() as temporary:
            first = Path(temporary) / "first.json"
            second = Path(temporary) / "second.json"
            export_sequence_time_audit_evidence(workspace, "Wait", 0.1, first)
            export_sequence_time_audit_evidence(workspace, "Wait", 0.1, second)
            self.assertEqual(first.read_text(encoding="utf-8"), second.read_text(encoding="utf-8"))
            payload = json.loads(first.read_text(encoding="utf-8"))
        self.assertEqual("easytech-spine-sequence-time-audit/v1", payload["schema"])
        self.assertEqual(hashlib.sha256(before).hexdigest(), payload["source_sha256"])
        self.assertEqual((True, "forbidden", "forbidden", "forbidden", "forbidden", "forbidden"), (payload["read_only"], payload["frame_selection"], payload["image_sampling"], payload["attachment_application"], payload["rendering"], payload["writeback"]))
        self.assertEqual("unlooped_raw_animation_time_only", payload["time_domain"])
        self.assertTrue(payload["audits"])
        first_audit = payload["audits"][0]
        self.assertEqual(("audited_region_index_only", "loop", 1, "forbidden", "forbidden", "forbidden"), (first_audit["state"], first_audit["mode_name"], first_audit["audited_region_index"], first_audit["frame_selection_state"], first_audit["attachment_application_state"], first_audit["rendering_state"]))
        self.assertEqual(len(payload["audits"]), len(payload["candidate_name_audits"]))
        candidate_audit = payload["candidate_name_audits"][0]
        self.assertEqual(("candidate_name_identity_verified_static_only", "forbidden", "forbidden", "forbidden"), (candidate_audit["state"], candidate_audit["frame_selection_state"], candidate_audit["image_sampling_state"], candidate_audit["rendering_state"]))
        self.assertEqual(before, SOURCE.read_bytes())

    def test_rejected_time_is_exported_as_audit_evidence_not_a_fallback(self) -> None:
        workspace = load_spine_static_workspace(SOURCE)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "rejected.json"
            export_sequence_time_audit_evidence(workspace, "Wait", -1.0, output)
            payload = json.loads(output.read_text(encoding="utf-8"))
        self.assertTrue(payload["audits"])
        self.assertTrue(all(item["state"] == "audit_rejected" for item in payload["audits"]))
        self.assertTrue(all(item["reason"] == "target_time_must_be_finite_and_nonnegative" for item in payload["audits"]))
        self.assertTrue(all(item["frame_selection_state"] == "forbidden" and item["rendering_state"] == "forbidden" for item in payload["audits"]))
        self.assertTrue(all(item["state"] == "candidate_name_audit_rejected" and item["frame_selection_state"] == "forbidden" and item["image_sampling_state"] == "forbidden" for item in payload["candidate_name_audits"]))


if __name__ == "__main__":
    unittest.main()
