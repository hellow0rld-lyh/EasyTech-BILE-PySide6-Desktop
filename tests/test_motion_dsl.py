from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from bile_workbench.motion_dsl import (
    MotionDslError,
    MotionProposalSession,
    export_proposal_evidence,
    parse_motion_proposal,
    proposal_template,
)
from bile_workbench.spine_workspace import create_pose_session, load_spine_static_workspace
from external_fixtures import require_files

ROOT = Path(__file__).resolve().parents[1]
ZHENG2 = ROOT / "incoming/cross_era_20260822/征2测试/animation/[mini]effect_ui10.bin"


class MotionDslTests(unittest.TestCase):
    def setUp(self) -> None:
        require_files(self, ZHENG2, ZHENG2.with_suffix(".atlas"), label="private Spine 4.1 sample and atlas")
        self.workspace = load_spine_static_workspace(ZHENG2)
        self.pose_session = create_pose_session(self.workspace, "Wait")
        self.payload = proposal_template(self.pose_session)
        self.payload["name"] = "UI10 root 提升只读提案"
        self.payload["operations"] = [
            {
                "id": "raise_root_01",
                "kind": "bone_delta",
                "bone": self.workspace.document.bones[0].name,
                "time": {"start": 0.0, "end": 0.1},
                "delta": {"y": 12.0, "rotation": 5.0},
            }
        ]

    def test_valid_motion_proposal_changes_only_in_memory_and_is_reversible(self) -> None:
        proposal = parse_motion_proposal(self.payload, self.pose_session)
        proposal_session = MotionProposalSession(self.pose_session)
        baseline, _ = self.pose_session.preview(0.1)
        proposal_session.apply(proposal)
        preview = proposal_session.preview(0.1)
        self.assertEqual(preview.active_operation_ids, ("raise_root_01",))
        self.assertIn("AI Motion DSL", "\n".join(preview.proposal_diagnostics))
        self.assertFalse(preview.projection.coverage_complete, "提案画面必须明确为非完整 runtime")
        self.assertAlmostEqual(preview.projection.bones[0].y, baseline.bones[0].y + 12.0)
        self.assertAlmostEqual(preview.projection.bones[0].rotation, baseline.bones[0].rotation + 5.0)
        self.assertIsNotNone(proposal_session.undo())
        restored = proposal_session.preview(0.1)
        self.assertEqual(restored.active_operation_ids, ())
        self.assertAlmostEqual(restored.projection.bones[0].y, baseline.bones[0].y)
        self.assertIsNotNone(proposal_session.redo())
        reapplied = proposal_session.preview(0.1)
        self.assertAlmostEqual(reapplied.projection.bones[0].y, baseline.bones[0].y + 12.0)

    def test_evidence_is_hash_bound_and_declares_writeback_forbidden(self) -> None:
        proposal = parse_motion_proposal(self.payload, self.pose_session)
        proposal_session = MotionProposalSession(self.pose_session)
        proposal_session.apply(proposal)
        with tempfile.TemporaryDirectory() as folder:
            evidence_path = export_proposal_evidence(Path(folder) / "proposal.evidence.json", proposal_session)
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        self.assertTrue(evidence["read_only"])
        self.assertEqual(evidence["writeback"], "forbidden")
        self.assertEqual(evidence["source"]["animation"], "Wait")
        self.assertEqual(evidence["samples"][0]["active_operation_ids"], [])
        self.assertEqual(evidence["samples"][1]["active_operation_ids"], ["raise_root_01"])
        self.assertIn("不生成任何 Spine BIN 补丁", evidence["boundary"])

    def test_hash_mismatch_and_unknown_property_are_rejected(self) -> None:
        mismatch = copy.deepcopy(self.payload)
        mismatch["source"]["sha256"] = "0" * 64
        with self.assertRaises(MotionDslError):
            parse_motion_proposal(mismatch, self.pose_session)
        bad_property = copy.deepcopy(self.payload)
        bad_property["operations"][0]["delta"] = {"world_x": 20.0}
        with self.assertRaises(MotionDslError):
            parse_motion_proposal(bad_property, self.pose_session)


if __name__ == "__main__":
    unittest.main()
