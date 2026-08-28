from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import unittest

from bile_workbench.spine_blend_mode_evidence import collect_non_normal_blend_evidence
from bile_workbench.spine_workspace import diagnostics_text, load_spine_static_workspace, static_manifest


ROOT = Path(__file__).resolve().parents[1]
EU7 = ROOT / "incoming/cross_era_20260822/欧7测试/animation/Arthur2.bin"
ZHENG2 = ROOT / "incoming/cross_era_20260822/征2测试/animation/EmpireCityFire01.bin"


@dataclass(frozen=True)
class _SlotFixture:
    index: int
    name: str
    blend_mode: int


class SpineBlendModeEvidenceTests(unittest.TestCase):
    def test_contract_names_known_non_normal_ordinals_and_rejects_unknown(self) -> None:
        evidence = collect_non_normal_blend_evidence(
            (_SlotFixture(0, "normal", 0), _SlotFixture(1, "add", 1), _SlotFixture(2, "multiply", 2), _SlotFixture(3, "screen", 3))
        )
        self.assertEqual(((1, "additive"), (2, "multiply"), (3, "screen")), tuple((item.blend_mode_ordinal, item.blend_mode_name) for item in evidence))
        self.assertTrue(all(item.non_normal_blend_application == "forbidden" and item.writeback == "forbidden" for item in evidence))
        with self.assertRaisesRegex(ValueError, "未验证"):
            collect_non_normal_blend_evidence((_SlotFixture(4, "unknown", 4),))

    def test_real_eu7_and_zheng2_manifest_are_static_only_and_source_unchanged(self) -> None:
        if not EU7.exists() or not ZHENG2.exists():
            self.skipTest("欧7/征2 blend evidence 验证样本未附加")
        eu7_before = EU7.read_bytes()
        zheng2_before = ZHENG2.read_bytes()
        eu7_workspace = load_spine_static_workspace(EU7)
        zheng2_workspace = load_spine_static_workspace(ZHENG2)
        eu7_evidence = collect_non_normal_blend_evidence(eu7_workspace.document.slots)
        self.assertTrue(any(item.blend_mode_name == "additive" for item in eu7_evidence))
        manifest = static_manifest(zheng2_workspace)
        payload = manifest["slot_blend_evidence"]
        self.assertEqual("forbidden", payload["non_normal_blend_application"])
        self.assertEqual("forbidden", payload["writeback"])
        self.assertTrue(any(item["blend_mode_name"] == "additive" for item in payload["non_normal_slots"]))
        diagnostics = diagnostics_text(zheng2_workspace)
        self.assertIn("非 normal slot blend 静态证据：additive", diagnostics)
        self.assertIn("非 normal 合成禁止", diagnostics)
        self.assertEqual(eu7_before, EU7.read_bytes())
        self.assertEqual(zheng2_before, ZHENG2.read_bytes())


if __name__ == "__main__":
    unittest.main()
