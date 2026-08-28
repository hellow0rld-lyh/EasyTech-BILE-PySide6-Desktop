from __future__ import annotations

import json
from pathlib import Path

from bile_workbench.spine38_format import Spine38FormatError, parse_file as parse_spine38
from bile_workbench.spine41_format import parse_file as parse_spine41


ROOT = Path(__file__).resolve().parents[1]
INCOMING = ROOT / "incoming"
OUTPUT = ROOT / "research" / "spine_linked_mesh_sample_scan_20260822.json"


def _parse(path: Path):
    failures: list[str] = []
    for engine, parser in (("spine38", parse_spine38), ("spine41", parse_spine41)):
        try:
            return engine, parser(path), failures
        except (Spine38FormatError, OSError, ValueError) as exc:
            failures.append(f"{engine}: {exc}")
    return None, None, failures


def main() -> int:
    records: list[dict[str, object]] = []
    parsed = 0
    for path in sorted(INCOMING.rglob("*.bin")):
        engine, document, failures = _parse(path)
        if document is None:
            continue
        parsed += 1
        linked = getattr(document, "linked_mesh_evidence", ())
        if linked:
            records.append(
                {
                    "path": str(path.relative_to(ROOT)),
                    "engine": engine,
                    "header_version": document.header.version,
                    "linked_meshes": [
                        {
                            "spine_version": item.spine_version,
                            "skin": item.skin,
                            "slot_index": item.slot_index,
                            "name": item.name,
                            "path": item.path,
                            "parent_skin": item.parent_skin,
                            "parent_name": item.parent_name,
                            "inherit_deform": item.inherit_deform,
                            "sequence_present": item.sequence_present,
                        }
                        for item in linked
                    ],
                }
            )
    payload = {
        "schema": "easytech-spine-linked-mesh-sample-scan/v1",
        "read_only": True,
        "writeback": "forbidden",
        "scanned_bin_count": sum(1 for _ in INCOMING.rglob("*.bin")),
        "recognized_spine_static_count": parsed,
        "linked_mesh_sample_count": len(records),
        "samples": records,
        "boundary": "Static evidence discovery only; does not resolve parents, project vertices, select sequence frames, render attachments, or modify BIN files.",
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("scanned_bin_count", "recognized_spine_static_count", "linked_mesh_sample_count")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
