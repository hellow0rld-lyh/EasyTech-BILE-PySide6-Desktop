#!/usr/bin/env python3
"""生成真实 anim_status initial_phase 编辑的游戏内实验包演示。"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bile_workbench.bile_format import parse_file
from bile_workbench.edit_session import EditSession
from bile_workbench.experiment_package import create_experiment_package


def locate_target(document):
    for parent in document.animations:
        for channel in parent.channels:
            for frame in channel.frames:
                for track in frame.tracks:
                    if track.element_index >= 0 and not document.elements[track.element_index].has_texture:
                        keyframe = document.keyframes[track.keyframe_index]
                        if keyframe.initial_phase != 0:
                            return track.keyframe_index, document.elements[track.element_index].frame_count
    raise RuntimeError("未找到真实非零 initial_phase 子动画轨道")


def main() -> int:
    assets = ROOT / "sample_assets"
    source = assets / "anim_status.bin"
    document = parse_file(source)
    keyframe_index, child_frames = locate_target(document)
    keyframe = document.keyframes[keyframe_index]
    transform = {field: getattr(keyframe, field) for field in ("xx", "xy", "yx", "yy", "x", "y")}
    output_dir = ROOT / "research" / "experiment_package_demo"
    output_dir.mkdir(exist_ok=True)
    archive = output_dir / "anim_status_initial_phase_experiment.zip"
    session = EditSession(source)
    try:
        session.set_keyframe(keyframe_index, transform, keyframe.argb, min(keyframe.initial_phase + 1, child_frames - 1))
        with tempfile.TemporaryDirectory(prefix="bile-demo-package-") as temp_dir:
            temp = Path(temp_dir)
            patch = temp / "source_patch.json"
            candidate = temp / "candidate.bin"
            session.write_patch(patch)
            session.write_candidate(candidate)
            result = create_experiment_package(source, candidate, assets / "anim_status.xml", assets / "anim_status.webp", archive, patch)
        summary = {
            "archive": str(result.archive_path),
            "report": str(result.report_path),
            "candidate_sha256": result.candidate_sha256,
            "checked_animations": result.checked_animations,
            "warnings": list(result.warnings),
            "edited_keyframe": keyframe_index,
            "initial_phase": {"before": keyframe.initial_phase, "after": min(keyframe.initial_phase + 1, child_frames - 1)},
        }
        (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
