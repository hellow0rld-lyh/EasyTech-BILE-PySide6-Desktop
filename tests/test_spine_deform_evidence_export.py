from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from bile_workbench.spine_deform_evidence_export import export_deform_audit_evidence
from bile_workbench.spine_workspace import create_pose_session, load_spine_static_workspace
from external_fixtures import require_files


ROOT = Path(__file__).resolve().parents[1]
ZHENG2 = ROOT / "incoming/cross_era_20260822/征2测试/animation/[mini]form_main1.bin"


class SpineDeformEvidenceExportTests(unittest.TestCase):
    def setUp(self) -> None:
        require_files(self, ZHENG2, label="private Spine deform evidence sample")

    def test_exports_hash_bound_readonly_deform_audit_without_source_mutation(self) -> None:
        before = ZHENG2.read_bytes()
        session = create_pose_session(load_spine_static_workspace(ZHENG2), "Wait")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "form_main1.deform-audit.json"
            result = export_deform_audit_evidence(session, output)
            first_text = result.read_text(encoding="utf-8")
            payload = json.loads(first_text)
            repeat = Path(directory) / "form_main1.deform-audit.repeat.json"
            self.assertEqual(first_text, export_deform_audit_evidence(session, repeat).read_text(encoding="utf-8"))
        self.assertEqual(payload["schema"], "easytech-spine-deform-audit/v1")
        self.assertTrue(payload["read_only"])
        self.assertEqual(payload["writeback"], "forbidden")
        self.assertEqual(payload["vertex_application"], "forbidden")
        self.assertEqual(payload["source_sha256"], hashlib.sha256(before).hexdigest())
        self.assertEqual(payload["animation"], "Wait")
        self.assertEqual(len(payload["timelines"]), 22)
        self.assertTrue(any(item["unweighted_identity_span_validation"]["accepted"] for item in payload["timelines"] if item["unweighted_identity_span_validation"] is not None))
        self.assertEqual(before, ZHENG2.read_bytes())


if __name__ == "__main__":
    unittest.main()
