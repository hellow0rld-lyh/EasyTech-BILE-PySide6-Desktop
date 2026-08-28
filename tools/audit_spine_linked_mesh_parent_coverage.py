from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from bile_workbench.spine38_format import Spine38FormatError, parse_file as parse_spine38
from bile_workbench.spine41_format import parse_file as parse_spine41
from bile_workbench.spine_linked_mesh_validation import validate_linked_mesh_parent


ROOT = Path(__file__).resolve().parents[1]
INCOMING = ROOT / "incoming"
OUTPUT = ROOT / "research" / "spine_linked_mesh_parent_coverage_20260822.json"


def _parse(path: Path):
    for engine, parser in (("spine38", parse_spine38), ("spine41", parse_spine41)):
        try:
            return engine, parser(path)
        except (Spine38FormatError, OSError, ValueError):
            continue
    return None, None


def main() -> int:
    states: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    examples: dict[str, list[dict[str, object]]] = {}
    linked_count = 0
    sample_count = 0
    for path in sorted(INCOMING.rglob("*.bin")):
        engine, document = _parse(path)
        if document is None:
            continue
        linked_meshes = getattr(document, "linked_mesh_evidence", ())
        if not linked_meshes:
            continue
        sample_count += 1
        for linked in linked_meshes:
            linked_count += 1
            validation = validate_linked_mesh_parent(linked, document.mesh_attachments, getattr(document, "sequence_evidence", ()))
            states[validation.state] += 1
            reasons[validation.reason] += 1
            examples.setdefault(validation.reason, [])
            if len(examples[validation.reason]) < 8:
                examples[validation.reason].append(
                    {
                        "path": str(path.relative_to(ROOT)),
                        "engine": engine,
                        "child": [linked.skin, linked.slot_index, linked.name],
                        "parent": [validation.resolved_parent_skin, linked.slot_index, linked.parent_name],
                        "sequence_present": linked.sequence_present,
                    }
                )
    payload = {
        "schema": "easytech-spine-linked-mesh-parent-coverage/v1",
        "read_only": True,
        "writeback": "forbidden",
        "linked_mesh_resource_count": sample_count,
        "linked_mesh_count": linked_count,
        "states": dict(sorted(states.items())),
        "reasons": dict(sorted(reasons.items())),
        "examples": examples,
        "boundary": "Uses only static mesh identity subset; does not resolve linked vertices, render attachments, or select sequence frames.",
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("linked_mesh_resource_count", "linked_mesh_count", "states", "reasons")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
