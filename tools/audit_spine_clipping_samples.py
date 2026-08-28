from __future__ import annotations

import json
from pathlib import Path

from bile_workbench.spine38_format import Spine38FormatError, parse_file as parse_spine38
from bile_workbench.spine41_format import parse_file as parse_spine41


ROOT = Path(__file__).resolve().parents[1]
INCOMING = ROOT / "incoming"
OUTPUT = ROOT / "research" / "spine_clipping_sample_scan_20260822.json"


def main() -> int:
    counts = {"spine38": 0, "spine41": 0}
    resources = {"spine38": 0, "spine41": 0}
    rows: list[dict[str, object]] = []
    for path in sorted(INCOMING.rglob("*.bin")):
        for engine, parser in (("spine38", parse_spine38), ("spine41", parse_spine41)):
            try:
                document = parser(path)
            except (Spine38FormatError, OSError, ValueError):
                continue
            resources[engine] += 1
            evidence = getattr(document, "clipping_evidence", ())
            counts[engine] += len(evidence)
            for item in evidence:
                rows.append(
                    {
                        "engine": engine,
                        "path": str(path.relative_to(ROOT)),
                        "skin": item.skin,
                        "slot_index": item.slot_index,
                        "name": item.name,
                        "attachment_key": item.attachment_key,
                        "end_slot_index": item.end_slot_index,
                        "vertex_count": item.vertex_count,
                        "vertex_application_state": item.vertex_application_state,
                        "clipping_rendering_state": item.clipping_rendering_state,
                        "writeback": item.writeback,
                    }
                )
            break
    payload = {
        "schema": "easytech-spine-clipping-sample-scan/v1",
        "read_only": True,
        "writeback": "forbidden",
        "resource_count": resources,
        "clipping_count": counts,
        "clippings": rows,
        "boundary": "Only static parser-consumed identity/end-slot/vertex-count evidence. No clipping polygon retention, vertex application, clipping, image sampling, rendering, or BIN modification.",
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"resource_count": resources, "clipping_count": counts, "total": len(rows)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
