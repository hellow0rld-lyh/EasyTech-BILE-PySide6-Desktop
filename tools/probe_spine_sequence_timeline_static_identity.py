from __future__ import annotations

import json
from pathlib import Path

from bile_workbench.spine41_format import parse_file
from bile_workbench.spine41_timeline import parse_spine41_animations


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "incoming/cross_era_20260822/征2测试/animation/EmpireCityFire01.bin"


def main() -> int:
    static = parse_file(SOURCE)
    archive = parse_spine41_animations(SOURCE)
    static_by_key = {(item.skin, item.slot_index, item.attachment_key): item for item in static.sequence_evidence}
    rows = []
    for animation in archive.animations:
        for timeline in animation.sequence_timeline_evidence:
            identity = (timeline.skin, timeline.slot_index, timeline.attachment_key)
            attachment = static_by_key.get(identity)
            rows.append(
                {
                    "animation": animation.name,
                    "identity": list(identity),
                    "static_match": attachment is not None,
                    "static_kind": None if attachment is None else attachment.attachment_kind,
                    "static_range": None if attachment is None else [attachment.start, attachment.start + attachment.count - 1],
                    "times": [frame.time for frame in timeline.frames],
                    "raw_sequence_indices": [frame.sequence_index for frame in timeline.frames],
                    "mode_ordinals": [frame.mode_ordinal for frame in timeline.frames],
                    "delays": [frame.delay for frame in timeline.frames],
                    "selection_state": "forbidden",
                    "rendering_state": "forbidden",
                }
            )
    print(json.dumps({"source": str(SOURCE.relative_to(ROOT)), "rows": rows}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
