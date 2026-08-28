from __future__ import annotations

import json
from pathlib import Path

from bile_workbench.spine41_format import parse_file
from bile_workbench.spine38_format import Spine38FormatError


ROOT = Path(__file__).resolve().parents[1]
INCOMING = ROOT / "incoming"
OUTPUT = ROOT / "research" / "spine41_nonzero_sequence_start_audit_20260822.json"


def main() -> int:
    resource_count = 0
    static_sequence_count = 0
    nonzero: list[dict[str, object]] = []
    for path in sorted(INCOMING.rglob("*.bin")):
        try:
            document = parse_file(path)
        except (Spine38FormatError, OSError, ValueError):
            continue
        resource_count += 1
        sequences = getattr(document, "sequence_evidence", ())
        static_sequence_count += len(sequences)
        for item in sequences:
            if item.start == 0:
                continue
            nonzero.append(
                {
                    "path": str(path.relative_to(ROOT)),
                    "skin": item.skin,
                    "slot_index": item.slot_index,
                    "attachment_key": item.attachment_key,
                    "attachment_kind": item.attachment_kind,
                    "start": item.start,
                    "count": item.count,
                    "digits": item.digits,
                    "setup_index": item.setup_index,
                }
            )
    payload = {
        "schema": "easytech-spine41-nonzero-sequence-start-audit/v1",
        "read_only": True,
        "writeback": "forbidden",
        "spine41_resource_count": resource_count,
        "static_sequence_count": static_sequence_count,
        "nonzero_start_count": len(nonzero),
        "nonzero_start_sequences": nonzero,
        "boundary": "Static sequence evidence only; no timeline evaluation, frame selection, image sampling, rendering, or BIN modification.",
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("spine41_resource_count", "static_sequence_count", "nonzero_start_count")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
