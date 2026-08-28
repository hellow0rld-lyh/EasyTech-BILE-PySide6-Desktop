"""形成配置解析器的合成夹具测试；不构成任何游戏运行时结论。"""
from __future__ import annotations

import unittest

from bile_workbench.formation_config import FormationConfigError, diff_formation_configs, parse_def_array_bytes, summarize_formation_config


BASELINE = b"""<?xml version='1.0' encoding='utf-8'?>
<Arrays>
  <Array name='Default' n='1'><Pos soldier='0,0' /></Array>
  <Array name='Mine 2' n='4'>
    <Pos soldier='-8,0,8,0' special='-8,0,8,0,0,-12' />
    <Pos soldier='0,0' />
  </Array>
</Arrays>
"""

CANDIDATE = b"""<Arrays>
  <Array name='Default' n='1'><Pos soldier='2,0' /></Array>
  <Array name='Mine 2' n='5'>
    <Pos soldier='-8,0,8,0,0,8' special='-8,0,8,0,0,8,0,-12' />
    <Pos soldier='0,0' special='0,0,0,-12,0,-24' />
  </Array>
</Arrays>"""


class FormationConfigTests(unittest.TestCase):
    def test_parses_readonly_array_rows_and_special_shape_warning(self) -> None:
        config = parse_def_array_bytes(BASELINE, "baseline_def_array.xml")
        self.assertEqual(config.source_name, "baseline_def_array.xml")
        self.assertEqual([item.name for item in config.arrays], ["Default", "Mine 2"])
        default, mine = config.arrays
        self.assertEqual(default.rows[0].primary[0].x, 0.0)
        self.assertEqual(default.rows[0].special_has_unique_child_shape, None)
        self.assertEqual(len(mine.rows[0].primary), 2)
        self.assertTrue(mine.rows[0].special_has_unique_child_shape)
        summary = summarize_formation_config(config)
        self.assertEqual(summary["arrays"][1]["rows"][0]["primary_count"], 2)
        self.assertEqual(summary["warnings"], [])

    def test_diff_reports_only_structural_variable_changes(self) -> None:
        baseline = parse_def_array_bytes(BASELINE, "baseline.xml")
        candidate = parse_def_array_bytes(CANDIDATE, "candidate.xml")
        report = diff_formation_configs(baseline, candidate)
        kinds = {(item["array"], item["kind"]) for item in report["changes"]}
        self.assertIn(("Default", "primary_coordinates"), kinds)
        self.assertIn(("Mine 2", "declared_count"), kinds)
        self.assertIn(("Mine 2", "primary_coordinates"), kinds)
        self.assertIn(("Mine 2", "special_coordinates"), kinds)
        self.assertEqual(len(candidate.warnings), 1)

    def test_rejects_invalid_coordinate_shape_and_duplicate_names(self) -> None:
        with self.assertRaises(FormationConfigError):
            parse_def_array_bytes(b"<Arrays><Array name='X'><Pos soldier='0,1,2'/></Array></Arrays>")
        with self.assertRaises(FormationConfigError):
            parse_def_array_bytes(b"<Arrays><Array name='X'/><Array name='X'/></Arrays>")


if __name__ == "__main__":
    unittest.main()
