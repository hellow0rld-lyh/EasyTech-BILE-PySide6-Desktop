#!/usr/bin/env python3
"""生成将军的荣耀3单兵根动作移植到世界征服者4 unit_infantry 的受控实验包。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bile_workbench.composition_experiment import create_composition_experiment_package
from bile_workbench.regression_case import create_regression_case


def main() -> int:
    target = ROOT / "cross_game_assets" / "wc4_extended" / "unit_infantry"
    candidate = ROOT / "cross_game_assets" / "general3" / "unit_infantry"
    output = ROOT / "research" / "wc4_unit_infantry_from_general3_composition_experiment.zip"
    result = create_composition_experiment_package(
        target.with_suffix(".bin"), target.with_suffix(".xml"), target.with_suffix(".webp"),
        candidate.with_suffix(".bin"), candidate.with_suffix(".xml"), candidate.with_suffix(".webp"),
        "通用普通步兵待机组合动画", "盟军通用普通士兵待机动画", output,
        target_unit_name="Soldier", target_motion_type="standby", target_resource="unit_infantry",
    )
    case_dir = ROOT / "research" / "wc4_unit_infantry_from_general3_composition_regression"
    if not case_dir.exists():
        manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
        create_regression_case(
            case_dir,
            target.with_suffix(".bin"), candidate.with_suffix(".bin"), "盟军通用普通士兵待机动画",
            target_slots=[0], experiment_package=result.archive_path,
            experiment_context={
                "kind": "cross-game-root-composition",
                "manifest": str(result.manifest_path),
                "binding_recipe": str(result.binding_recipe_path),
                "target_root_animation": "通用普通步兵待机组合动画",
                "candidate_root_animation": "盟军通用普通士兵待机动画",
                "fixed_variables": manifest["controlled_variables"]["must_remain_target_side"],
                "formation_snapshot": "",
            },
        )
    print(result.archive_path)
    print(result.manifest_path)
    print(result.binding_recipe_path)
    print(result.validation_report_path)
    print(case_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
