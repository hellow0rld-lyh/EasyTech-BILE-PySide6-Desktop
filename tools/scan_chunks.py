#!/usr/bin/env python3
"""只读扫描 BILE 容器的候选四字符块与相对长度关系。"""
from __future__ import annotations

import re
import struct
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "sample_assets"
OUT = ROOT / "research" / "bile_chunk_scan.md"
TAG_PATTERN = re.compile(rb"B[A-Z]{3}")


def u32(data: bytes, off: int) -> int | None:
    return struct.unpack_from("<I", data, off)[0] if off + 4 <= len(data) else None


def chunk_candidates(data: bytes) -> list[dict[str, int | str | bool | None]]:
    rows = []
    for match in TAG_PATTERN.finditer(data):
        pos = match.start()
        tag = match.group().decode("ascii")
        length = u32(data, pos + 4)
        value2 = u32(data, pos + 8)
        value3 = u32(data, pos + 12)
        relative_end = pos + length if length is not None else None
        rows.append(
            {
                "tag": tag,
                "pos": pos,
                "length": length,
                "value2": value2,
                "value3": value3,
                "relative_end": relative_end,
                "in_bounds": relative_end is not None and pos < relative_end <= len(data),
            }
        )
    return rows


def main() -> int:
    bins = sorted(ASSET_DIR.glob("anim_*.bin"))
    if not bins:
        print("未找到动画 BIN。", file=sys.stderr)
        return 2
    lines = [
        "# BILE 候选分块扫描",
        "",
        "> 扫描规则：匹配 `B[A-Z]{3}` 并将其后 4 字节按小端 `u32` 暂作‘长度候选’。只有当 `标签位置 + 长度候选` 恰为下一标签位置时，才构成强边界证据。",
        "",
    ]
    global_tags: Counter[str] = Counter()
    for path in bins:
        data = path.read_bytes()
        candidates = chunk_candidates(data)
        global_tags.update(row["tag"] for row in candidates)
        lines += [f"## `{path.name}`", "", f"文件大小：`{len(data)}` 字节；命中 `{len(candidates)}` 个候选标签。", ""]
        lines += ["| 标签 | 偏移 | 后随 `u32` | 后随 `u32 #2` | 位置 + 长度 | 块内有效 | 下一个候选偏移 | 边界相等 |", "|---|---:|---:|---:|---:|:---:|---:|:---:|"]
        for index, row in enumerate(candidates):
            next_pos = candidates[index + 1]["pos"] if index + 1 < len(candidates) else None
            end = row["relative_end"]
            equality = end == next_pos
            lines.append(
                "| `{tag}` | `0x{pos:04X}` | `{length}` | `{value2}` | `{end}` | `{valid}` | `{next}` | `{equal}` |".format(
                    tag=row["tag"],
                    pos=row["pos"],
                    length=row["length"] if row["length"] is not None else "—",
                    value2=row["value2"] if row["value2"] is not None else "—",
                    end=f"0x{end:04X}" if isinstance(end, int) else "—",
                    valid="是" if row["in_bounds"] else "否",
                    next=f"0x{next_pos:04X}" if isinstance(next_pos, int) else "—",
                    equal="是" if equality else "否",
                )
            )
        lines.append("")
    lines += ["## 全样本标签出现频次", "", "| 标签 | 命中次数 |", "|---|---:|"]
    for tag, count in sorted(global_tags.items()):
        lines.append(f"| `{tag}` | `{count}` |")
    lines.append("")
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
