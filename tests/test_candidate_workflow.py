"""候选工作流以真实原包样本验证，确保 UI 可安全委托该服务。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bile_workbench.candidate_workflow import CandidateWorkflow, CandidateWorkflowError
from bile_workbench.edit_session import EditSession
from bile_workbench.preview_renderer import load_atlas


class CandidateWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assets = ROOT / "sample_assets"
        self.binary = self.assets / "anim_failure.bin"
        self.xml = self.assets / "anim_failure.xml"
        self.image = self.assets / "anim_failure.webp"

    def _dirty_workflow(self) -> tuple[CandidateWorkflow, EditSession]:
        session = EditSession(self.binary)
        session.set_keyframe(1, {"xx": 1.0, "xy": 0.0, "yx": 0.0, "yy": 1.0, "x": 42.5, "y": -9.0}, 0x80FFFFFF, 0)
        workflow = CandidateWorkflow(self.binary, self.xml, self.image, load_atlas(self.xml, self.image), session)
        return workflow, session

    def test_rejects_clean_session_before_creating_files(self) -> None:
        session = EditSession(self.binary)
        try:
            workflow = CandidateWorkflow(self.binary, self.xml, self.image, load_atlas(self.xml, self.image), session)
            with self.assertRaises(CandidateWorkflowError):
                workflow.require_preflight()
        finally:
            session.close()

    def test_creates_diff_package_and_regression_case(self) -> None:
        workflow, session = self._dirty_workflow()
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                diff = workflow.create_diff("failure_a", root / "diff")
                impact = workflow.create_track_impact_evidence(root / "impact")
                package = workflow.create_experiment_package(root / "experiment.zip")
                case = workflow.create_regression_case(root / "case", "failure_a", [0, 16, 31])
                self.assertTrue(diff.report_path.exists())
                self.assertTrue(impact.json_path and impact.json_path.exists())
                self.assertTrue(impact.markdown_path and impact.markdown_path.exists())
                self.assertTrue(package.archive_path.exists())
                self.assertTrue(case.case_dir.joinpath("case.json").exists())
                self.assertEqual(case.diff.changed_slots, diff.changed_slots)
                self.assertEqual(case.package.candidate_sha256, package.candidate_sha256)
        finally:
            session.close()


if __name__ == "__main__":
    unittest.main()
