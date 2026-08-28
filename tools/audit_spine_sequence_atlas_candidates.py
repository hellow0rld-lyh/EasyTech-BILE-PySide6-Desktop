from __future__ import annotations

import json
from pathlib import Path

from bile_workbench.spine_atlas import load_spine_atlas
from bile_workbench.spine41_format import parse_file

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "incoming/cross_era_20260822/征2测试/animation/EmpireCityFire01.bin"


def main() -> None:
    document = parse_file(SOURCE)
    atlas = load_spine_atlas(SOURCE.with_suffix(".atlas"))
    rows = []
    for evidence in document.sequence_evidence:
        exact = [region.name for region in atlas.regions if region.name == evidence.name]
        prefix = [region.name for region in atlas.regions if region.name.startswith(evidence.name)]
        rows.append({
            "attachment": evidence.name,
            "count": evidence.count,
            "start": evidence.start,
            "digits": evidence.digits,
            "setup_index": evidence.setup_index,
            "exact_regions": exact,
            "prefix_regions": prefix,
        })
    print(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
