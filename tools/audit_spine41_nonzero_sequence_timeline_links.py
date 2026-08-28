from __future__ import annotations

import json
from pathlib import Path

from bile_workbench.spine38_format import Spine38FormatError
from bile_workbench.spine41_format import parse_file
from bile_workbench.spine41_timeline import parse_spine41_animations


ROOT = Path(__file__).resolve().parents[1]
INCOMING = ROOT / "incoming"
OUTPUT = ROOT / "research" / "spine41_nonzero_sequence_timeline_links_20260822.json"


def main() -> int:
    links: list[dict[str, object]] = []
    static_nonzero = 0
    for path in sorted(INCOMING.rglob("*.bin")):
        try:
            static = parse_file(path)
        except (Spine38FormatError, OSError, ValueError):
            continue
        candidates = [item for item in static.sequence_evidence if item.start != 0]
        static_nonzero += len(candidates)
        if not candidates:
            continue
        try:
            archive = parse_spine41_animations(path)
        except (Spine38FormatError, OSError, ValueError):
            continue
        timelines = [item for animation in archive.animations for item in animation.sequence_timeline_evidence]
        for sequence in candidates:
            for timeline in timelines:
                if (timeline.skin, timeline.slot_index, timeline.attachment_key) != (sequence.skin, sequence.slot_index, sequence.attachment_key):
                    continue
                links.append(
                    {
                        "path": str(path.relative_to(ROOT)),
                        "animation": timeline.animation,
                        "skin": sequence.skin,
                        "slot_index": sequence.slot_index,
                        "attachment_key": sequence.attachment_key,
                        "attachment_kind": sequence.attachment_kind,
                        "start": sequence.start,
                        "count": sequence.count,
                        "times": [frame.time for frame in timeline.frames],
                        "raw_indices": [frame.sequence_index for frame in timeline.frames],
                        "mode_ordinals": [frame.mode_ordinal for frame in timeline.frames],
                        "delays": [frame.delay for frame in timeline.frames],
                    }
                )
    payload = {
        "schema": "easytech-spine41-nonzero-sequence-timeline-link-audit/v1",
        "read_only": True,
        "writeback": "forbidden",
        "static_nonzero_start_count": static_nonzero,
        "timeline_link_count": len(links),
        "links": links,
        "boundary": "Identity correlation and raw evidence only; no SequenceMode evaluation, frame selection, image sampling, rendering, or BIN modification.",
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"static_nonzero_start_count": static_nonzero, "timeline_link_count": len(links)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
