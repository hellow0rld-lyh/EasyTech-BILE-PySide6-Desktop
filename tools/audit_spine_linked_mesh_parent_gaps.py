from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from bile_workbench.spine38_format import Spine38FormatError, parse_file as parse_spine38
from bile_workbench.spine41_format import parse_file as parse_spine41
from bile_workbench.spine_linked_mesh_validation import validate_linked_mesh_parent


ROOT = Path(__file__).resolve().parents[1]
INCOMING = ROOT / "incoming"
OUTPUT = ROOT / "research" / "spine_linked_mesh_parent_gap_audit_20260822.json"


def _parse(path: Path):
    for engine, parser in (("spine38", parse_spine38), ("spine41", parse_spine41)):
        try:
            return engine, parser(path)
        except (Spine38FormatError, OSError, ValueError):
            continue
    return None, None


def main() -> int:
    categories: Counter[str] = Counter()
    examples: dict[str, list[dict[str, object]]] = {}
    for path in sorted(INCOMING.rglob("*.bin")):
        engine, document = _parse(path)
        if document is None:
            continue
        linked = getattr(document, "linked_mesh_evidence", ())
        if not linked:
            continue
        linked_identities = {(item.skin, item.slot_index, item.name) for item in linked}
        sequence_identities = {(item.skin, item.slot_index, item.name) for item in getattr(document, "sequence_evidence", ())}
        for item in linked:
            validation = validate_linked_mesh_parent(item, document.mesh_attachments, getattr(document, "sequence_evidence", ()))
            if validation.state != "candidate_parent_rejected":
                continue
            identity = (validation.resolved_parent_skin, item.slot_index, item.parent_name)
            if identity in linked_identities:
                category = "parent_is_linked_mesh_evidence"
            elif identity in sequence_identities:
                category = "parent_has_sequence_evidence_kind_not_captured"
            else:
                category = "parent_identity_not_captured"
            categories[category] += 1
            examples.setdefault(category, [])
            if len(examples[category]) < 10:
                examples[category].append(
                    {
                        "path": str(path.relative_to(ROOT)),
                        "engine": engine,
                        "child": [item.skin, item.slot_index, item.name],
                        "parent": list(identity),
                    }
                )
    payload = {
        "schema": "easytech-spine-linked-mesh-parent-gap-audit/v1",
        "read_only": True,
        "writeback": "forbidden",
        "categories": dict(sorted(categories.items())),
        "examples": examples,
        "boundary": "Identity comparison only; does not resolve chains, classify attachment kinds beyond existing evidence, render, or modify BIN files.",
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["categories"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
