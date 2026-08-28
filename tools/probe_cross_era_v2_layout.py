"""比较新增 BILE v2 样本的原始记录关系；不更改解析器候选规则。"""
from __future__ import annotations

import argparse
import json
import struct
from collections import Counter
from pathlib import Path

from bile_workbench.bile_format import BileFormatError, _parse_header_and_sections, parse_file


def u32(payload: bytes, offset: int) -> int:
    return struct.unpack_from("<I", payload, offset)[0]


def inspect(path: Path, root: Path) -> dict:
    data = path.read_bytes()
    header, sections = _parse_header_and_sections(data)
    if header.version != 2:
        raise ValueError(f"不是 v2：{path}")
    bele = sections["BELE"]
    bmrf = sections["BMRF"]
    third_values = [u32(bmrf.payload, index * 12 + 8) for index in range(bmrf.count)]
    second_values = [u32(bmrf.payload, index * 12 + 4) for index in range(bmrf.count)]
    try:
        parse_file(path)
        parse_status = "PASS"
        parse_detail = "严格解析通过"
    except BileFormatError as exc:
        parse_status = "REJECT"
        parse_detail = str(exc)
    return {
        "path": str(path.relative_to(root)),
        "status": parse_status,
        "detail": parse_detail,
        "bele_count": bele.count,
        "bmrf_count": bmrf.count,
        "byal_count": sections["BYAL"].count,
        "bmti_count": sections["BMTI"].count,
        "bele_minus_bmrf": bele.count - bmrf.count,
        "third_min": min(third_values, default=None),
        "third_max": max(third_values, default=None),
        "third_unique": len(set(third_values)),
        "third_in_bele_range": sum(value < bele.count for value in third_values),
        "track_count_min": min(second_values, default=None),
        "track_count_max": max(second_values, default=None),
        "track_count_sum": sum(second_values),
        "zero_track_frame_count": sum(value == 0 for value in second_values),
        "single_track_frame_count": sum(value == 1 for value in second_values),
        "multi_track_frame_count": sum(value > 1 for value in second_values),
        "first_records": [
            {"slot": u32(bmrf.payload, index * 12), "track_count": second_values[index], "third": third_values[index]}
            for index in range(min(8, bmrf.count))
        ],
        "third_common": Counter(third_values).most_common(8),
    }


def markdown(rows: list[dict]) -> str:
    lines = [
        "# 新增 v2 样本：BMRF 结构对照",
        "",
        "> 目标是检验新增样本是否满足 `sum(BMRF.second_dword) == BELE.count`。若成立，说明第二 dword 更像每帧的 BELE/轨道数量，而非元素索引；该报告本身不授予写回语义。",
        "",
        "| 路径 | 旧解析状态 | BELE | BMRF 帧 | 轨道数和 | BELE=轨道数和 | 零轨帧 | 多轨帧 | BMTI |",
        "|---|---|---:|---:|---:|---|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| `{row['path']}` | {row['status']} | {row['bele_count']} | {row['bmrf_count']} | {row['track_count_sum']} | "
            f"{'是' if row['bele_count'] == row['track_count_sum'] else '否'} | {row['zero_track_frame_count']} | "
            f"{row['multi_track_frame_count']} | {row['bmti_count']} |"
        )
    lines.extend(["", "## 前八条 BMRF 原始记录", ""])
    for row in rows:
        lines.extend([f"### {row['path']} · {row['status']}", "", "```json", json.dumps(row["first_records"], ensure_ascii=False, indent=2), "```", ""])
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = []
    for path in sorted(args.root.rglob("*.bin")):
        if path.read_bytes()[:8] == b"BILE\x02\x00\x00\x00":
            rows.append(inspect(path, args.root))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"schema": "bile-workbench.v2-layout-compare/v1", "rows": rows}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.output.with_suffix(".md").write_text(markdown(rows), encoding="utf-8")
    print(f"已写入：{args.output}")
    print(f"已写入：{args.output.with_suffix('.md')}")


if __name__ == "__main__":
    main()
