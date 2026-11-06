from __future__ import annotations

import unittest
from pathlib import Path

from bile_workbench.spine41_timeline import parse_spine41_pose_animation
from bile_workbench.spine_deform_audit import deform_audit_text
from external_fixtures import require_files


ROOT = Path(__file__).resolve().parents[1]
ZHENG2 = ROOT / "incoming/cross_era_20260822/征2测试/animation/[mini]form_main1.bin"
ZHENG2_NO_DEFORM = ROOT / "incoming/cross_era_20260822/征2测试/animation/[mini]effect_ui10.bin"


class SpineDeformAuditTests(unittest.TestCase):
    def test_real_zheng2_audit_reports_evidence_and_preserves_source(self) -> None:
        require_files(self, ZHENG2, label="private Zheng2 deform audit sample")
        before = ZHENG2.read_bytes()
        static, animation = parse_spine41_pose_animation(ZHENG2, "Wait")
        text = deform_audit_text(static, animation)
        self.assertIn("Deform 只读审计", text)
        self.assertIn("22 条 timeline", text)
        self.assertIn("无权重精确 identity/span 预检：8 个候选", text)
        self.assertIn("未应用到顶点", text)
        self.assertEqual(before, ZHENG2.read_bytes())

    def test_no_deform_animation_reports_empty_readonly_audit(self) -> None:
        require_files(self, ZHENG2_NO_DEFORM, label="private Zheng2 no-deform sample")
        static, animation = parse_spine41_pose_animation(ZHENG2_NO_DEFORM, "Wait")
        self.assertFalse(animation.deform_evidence)
        self.assertEqual(deform_audit_text(static, animation), "Deform 审计：当前动画没有已捕获 deform evidence。")


if __name__ == "__main__":
    unittest.main()
