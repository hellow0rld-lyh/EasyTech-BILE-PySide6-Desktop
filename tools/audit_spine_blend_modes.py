from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from bile_workbench.spine38_format import Spine38FormatError, parse_file as parse_spine38
from bile_workbench.spine41_format import parse_file as parse_spine41


ROOT = Path(__file__).resolve().parents[1]
INCOMING = ROOT / "incoming"
OUTPUT = ROOT / "research/spine_blend_mode_sample_scan_20260822.json"


def main() -> int:
    resource_counts = Counter()
    slot_counts = Counter()
    non_normal: list[dict[str, object]] = []
    for path in sorted(INCOMING.rglob("*.bin")):
        for engine, parser in (("spine38", parse_spine38), ("spine41", parse_spine41)):
            try:
                document = parser(path)
            except (Spine38FormatError, OSError, ValueError):
                continue
            resource_counts[engine] += 1
            for slot in document.slots:
                slot_counts[f"{engine}:{slot.blend_mode}"] += 1
                if slot.blend_mode != 0:
                    non_normal.append(
                        {
                            "engine": engine,
                            "path": str(path.relative_to(ROOT)),
                            "slot_index": slot.index,
                            "slot_name": slot.name,
                            "blend_mode_ordinal": slot.blend_mode,
                            "state": "static_slot_fact_only",
                            "renderer_state": "forbidden; existing preview normal-alpha-composites only",
                            "writeback": "forbidden",
                        }
                    )
            break
    payload = {
        "schema": "easytech-spine-blend-mode-sample-scan/v1",
        "read_only": True,
        "writeback": "forbidden",
        "resource_counts": dict(sorted(resource_counts.items())),
        "slot_counts_by_engine_ordinal": dict(sorted(slot_counts.items())),
        "non_normal_slots": non_normal,
        "boundary": "Records static slot blend mode ordinal only. Does not name runtime behavior, compose images, render a non-normal blend, or modify Spine BIN.",
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"resource_counts": payload["resource_counts"], "slot_counts_by_engine_ordinal": payload["slot_counts_by_engine_ordinal"], "non_normal_slots": len(non_normal)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
