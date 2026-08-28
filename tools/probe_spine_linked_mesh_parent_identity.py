from __future__ import annotations

import json
from pathlib import Path

from bile_workbench.spine41_format import parse_file


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "incoming/cross_era_20260822/征2测试/animation/[mini]effect_ui5.bin"


def main() -> int:
    document = parse_file(SOURCE)
    mesh_identities = {(item.skin, item.slot_index, item.name) for item in document.mesh_attachments}
    rows = []
    for linked in document.linked_mesh_evidence:
        parent_skin = linked.parent_skin or "default"
        parent = (parent_skin, linked.slot_index, linked.parent_name)
        rows.append(
            {
                "linked": {"skin": linked.skin, "slot": linked.slot_index, "name": linked.name},
                "declared_parent": {"skin": parent_skin, "slot": linked.slot_index, "name": linked.parent_name},
                "matches_parsed_nonsequence_mesh": parent in mesh_identities,
                "inherit_timelines": linked.inherit_deform,
                "rendering_state": "forbidden",
            }
        )
    print(json.dumps({"source": str(SOURCE.relative_to(ROOT)), "mesh_count": len(mesh_identities), "rows": rows}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
