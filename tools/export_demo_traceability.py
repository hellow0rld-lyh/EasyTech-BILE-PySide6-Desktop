#!/usr/bin/env python3
"""生成 failure_a 平移候选的差异报告、实验包和待游戏内回归案例。"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bile_workbench.diff_analysis import compare_animation
from bile_workbench.experiment_package import create_experiment_package
from bile_workbench.interchange import SCHEMA, apply_patch
from bile_workbench.preview_renderer import load_atlas
from bile_workbench.regression_case import create_regression_case


def main() -> int:
    assets = ROOT / "sample_assets"
    source = assets / "anim_failure.bin"
    output = ROOT / "research" / "traceability_demo"
    output.mkdir(exist_ok=True)
    original = source.read_bytes()
    atlas = load_atlas(assets / "anim_failure.xml", assets / "anim_failure.webp")
    with tempfile.TemporaryDirectory(prefix="bile-traceability-demo-") as temp_dir:
        temp = Path(temp_dir)
        patch = temp / "source_patch.json"
        candidate = temp / "candidate.bin"
        patch.write_text(json.dumps({
            "schema": SCHEMA,
            "kind": "patch",
            "source_sha256": hashlib.sha256(original).hexdigest(),
            "keyframes": [{"index": 1, "transform": {"x": 19.5}}],
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        apply_patch(source, patch, candidate)
        diff = compare_animation(source, candidate, atlas, "failure_a", output / "candidate_diff", (320, 240))
        package = create_experiment_package(source, candidate, assets / "anim_failure.xml", assets / "anim_failure.webp", output / "failure_a_game_experiment.zip", patch)
        case = create_regression_case(output / "failure_a_regression_case", source, candidate, "failure_a", diff.markdown_path, [0, 16, 31], package.archive_path)
    summary = {
        "diff_markdown": str(diff.markdown_path),
        "diff_json": str(diff.report_path),
        "visible_changed_slots": diff.changed_slots,
        "total_changed_pixels": diff.total_changed_pixels,
        "binary_field_changes": diff.binary_change_count,
        "difference_artifacts": [str(path) for path in diff.artifacts],
        "experiment_package": str(package.archive_path),
        "regression_case": str(case),
        "case_readme": str(case / "README_回归案例.md"),
    }
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
