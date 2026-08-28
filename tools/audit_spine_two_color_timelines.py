from __future__ import annotations

import json
from pathlib import Path

from bile_workbench.spine38_format import Spine38FormatError
from bile_workbench.spine38_timeline import parse_spine38_animations
from bile_workbench.spine41_timeline import parse_spine41_animations


ROOT = Path(__file__).resolve().parents[1]
INCOMING = ROOT / "incoming"
OUTPUT = ROOT / "research" / "spine_two_color_timeline_sample_scan_20260822.json"


TWO_COLOR_KINDS = {"two_color", "rgba2", "rgb2"}


def main() -> int:
    resources = {"spine38": 0, "spine41": 0}
    timeline_counts = {"spine38": 0, "spine41": 0}
    frame_counts = {"spine38": 0, "spine41": 0}
    rows: list[dict[str, object]] = []
    for path in sorted(INCOMING.rglob("*.bin")):
        for engine, parser in (("spine38", parse_spine38_animations), ("spine41", parse_spine41_animations)):
            try:
                archive = parser(path)
            except (Spine38FormatError, OSError, ValueError):
                continue
            resources[engine] += 1
            for animation in archive.animations:
                for timeline in animation.timelines:
                    if timeline.group != "slot" or timeline.kind not in TWO_COLOR_KINDS:
                        continue
                    timeline_counts[engine] += 1
                    frame_counts[engine] += timeline.frame_count
                    rows.append(
                        {
                            "engine": engine,
                            "path": str(path.relative_to(ROOT)),
                            "animation": animation.name,
                            "kind": timeline.kind,
                            "target_slot": timeline.target,
                            "frame_count": timeline.frame_count,
                            "first_time": timeline.first_time,
                            "last_time": timeline.last_time,
                            "state": "parsed_raw_pose_track_evidence_only",
                            "renderer_state": "light_rgba_only; dark_two_color_forbidden",
                            "writeback": "forbidden",
                        }
                    )
            break
    payload = {
        "schema": "easytech-spine-two-color-timeline-sample-scan/v1",
        "read_only": True,
        "writeback": "forbidden",
        "resources": resources,
        "timeline_counts": timeline_counts,
        "frame_counts": frame_counts,
        "timelines": rows,
        "boundary": "Counts archive summaries only. It does not change PoseProjection, apply dark tint to pixels, render two-color output, or modify BIN files.",
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"resources": resources, "timeline_counts": timeline_counts, "frame_counts": frame_counts}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
