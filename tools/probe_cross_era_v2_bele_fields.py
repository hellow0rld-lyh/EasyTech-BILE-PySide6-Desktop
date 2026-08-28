"""探测 BILE v2 BELE 后半记录与 BMRF 的潜在关联，仅生成证据。"""
from __future__ import annotations

import argparse
import json
import struct
from collections import Counter
from pathlib import Path

from bile_workbench.bile_format import BileFormatError, _parse_header_and_sections, parse_file


FIELD_OFFSETS = {"u28": 28, "u32": 32, "u36": 36, "u40": 40, "u44": 44}


def fields(payload: bytes, count: int) -> dict[str, list[int]]:
    return {
        name: [struct.unpack_from("<I", payload, index * 48 + offset)[0] for index in range(count)]
        for name, offset in FIELD_OFFSETS.items()
    }


def summarize(values: list[int], bmrf_count: int) -> dict:
    counts = Counter(values)
    return {
        "min": min(values, default=None),
        "max": max(values, default=None),
        "unique": len(counts),
        "zero": counts.get(0, 0),
        "in_bmrf_index_range": sum(value < bmrf_count for value in values),
        "common": counts.most_common(6),
    }


def greedy_sequence_alignment(needle: list[tuple[int, int]], haystack: list[tuple[int, int]]) -> dict:
    """只测一组记录对能否保序嵌入另一组记录；不将其直接升级为格式语义。"""
    cursor = 0
    positions: list[int] = []
    for item in needle:
        while cursor < len(haystack) and haystack[cursor] != item:
            cursor += 1
        if cursor >= len(haystack):
            return {"complete": False, "matched": len(positions), "positions": positions[:12]}
        positions.append(cursor)
        cursor += 1
    return {"complete": True, "matched": len(positions), "positions": positions[:12]}


def greedy_slot_alignment(bele_slots: list[int], bmrf_slots: list[int]) -> dict:
    """只测顺序槽位能否贪婪对齐；不把对齐本身解释为运行时索引语义。"""
    cursor = 0
    positions: list[int] = []
    for slot in bele_slots:
        while cursor < len(bmrf_slots) and bmrf_slots[cursor] != slot:
            cursor += 1
        if cursor >= len(bmrf_slots):
            return {"complete": False, "matched": len(positions), "positions": positions[:12]}
        positions.append(cursor)
        cursor += 1
    return {"complete": True, "matched": len(positions), "positions": positions[:12]}


def inspect(path: Path, root: Path) -> dict:
    data = path.read_bytes()
    header, sections = _parse_header_and_sections(data)
    if header.version != 2:
        raise ValueError("不是 v2")
    try:
        parse_file(path)
        status, detail = "PASS", "严格解析通过"
    except BileFormatError as exc:
        status, detail = "REJECT", str(exc)
    bele = sections["BELE"]
    bmrf = sections["BMRF"]
    grouped = fields(bele.payload, bele.count)
    bmrf_slots = [struct.unpack_from("<I", bmrf.payload, index * 12)[0] for index in range(bmrf.count)]
    bmrf_elements = [struct.unpack_from("<i", bmrf.payload, index * 12 + 4)[0] for index in range(bmrf.count)]
    bele_slots = grouped["u28"]
    bele_elements = [struct.unpack_from("<i", bele.payload, index * 48 + 44)[0] for index in range(bele.count)]
    bele_pairs = list(zip(bele_slots, bele_elements))
    bmrf_pairs = list(zip(bmrf_slots, bmrf_elements))
    bmti_count = sections["BMTI"].count
    return {
        "path": str(path.relative_to(root)),
        "status": status,
        "detail": detail,
        "bele_count": bele.count,
        "bmrf_count": bmrf.count,
        "field_summary": {name: summarize(values, bmrf.count) for name, values in grouped.items()},
        "u28_matches_bmrf_positionally": sum(left == right for left, right in zip(bele_slots, bmrf_slots)),
        "u28_bmrf_slot_multiset_equal": Counter(bele_slots) == Counter(bmrf_slots),
        "u28_greedy_bmrf_alignment": greedy_slot_alignment(bele_slots, bmrf_slots),
        "u28_u44_matches_bmrf_positionally": sum(left == right for left, right in zip(bele_pairs, bmrf_pairs)),
        "u28_u44_bmrf_pair_multiset_equal": Counter(bele_pairs) == Counter(bmrf_pairs),
        "u28_u44_greedy_bmrf_pair_alignment": greedy_sequence_alignment(bele_pairs, bmrf_pairs),
        "bmti_count": bmti_count,
        "u44_valid_target_count": sum(value == -1 or 0 <= value < bmti_count for value in bele_elements),
        "u44_negative_count": sum(value == -1 for value in bele_elements),
        "first_bele": [
            {name: values[index] for name, values in grouped.items()}
            for index in range(min(8, bele.count))
        ],
    }


def markdown(rows: list[dict]) -> str:
    lines = [
        "# 新增 v2 样本：BELE 后半字段对照",
        "",
        "> 该报告只比较原始 dword 分布与 BMRF 计数。一个字段值落在某个索引范围内不构成引用语义证明；它仅用于筛选下一轮可证伪映射假设。",
        "",
        "| 路径 | 状态 | BELE | BMRF | BMTI | u44 合法目标 | u44=-1 | 对贪婪对齐 |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        summary = row["field_summary"]
        lines.append(
            f"| `{row['path']}` | {row['status']} | {row['bele_count']} | {row['bmrf_count']} | {row['bmti_count']} | "
            f"{row['u44_valid_target_count']}/{row['bele_count']} | {row['u44_negative_count']} | "
            f"{'是' if row['u28_u44_greedy_bmrf_pair_alignment']['complete'] else '否'} |"
        )
    lines.extend(["", "## 拒绝样本的字段摘要", ""])
    for row in rows:
        if row["status"] == "REJECT":
            lines.extend([f"### {row['path']}", "", "```json", json.dumps(row["field_summary"], ensure_ascii=False, indent=2), "```", ""])
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
    payload = {"schema": "bile-workbench.v2-bele-field-probe/v1", "rows": rows}
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.output.with_suffix(".md").write_text(markdown(rows), encoding="utf-8")
    print(f"已写入：{args.output}")
    print(f"已写入：{args.output.with_suffix('.md')}")


if __name__ == "__main__":
    main()
