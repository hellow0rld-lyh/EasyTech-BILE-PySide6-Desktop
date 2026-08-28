"""按 BMTI/BYAL 累计关系检查 BILE v2 时间线分段；仅输出取证报告。"""
from __future__ import annotations

import argparse
import json
import struct
from collections import Counter
from pathlib import Path

from bile_workbench.bile_format import _parse_header_and_sections, _parse_strings


def u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def inspect(path: Path, root: Path) -> dict:
    data = path.read_bytes()
    header, sections = _parse_header_and_sections(data)
    if header.version != 2:
        raise ValueError("不是 v2")
    strings = _parse_strings(sections["BRTS"].payload)
    bmti = sections["BMTI"]
    byal = sections["BYAL"]
    bmrf = sections["BMRF"]
    channel_cursor = 0
    frame_cursor = 0
    elements = []
    for index in range(bmti.count):
        offset = bmti.payload_offset + index * 56
        name_offset = u32(data, offset + 4)
        name = strings.get(name_offset, f"<invalid:0x{name_offset:X}>")
        has_texture = u32(data, offset + 24) != 0
        declared_frame_count = u32(data, offset + 28)
        channel_count = u32(data, offset + 32)
        channel_rows = []
        element_start = frame_cursor
        for channel_index in range(channel_count):
            byal_offset = byal.payload_offset + channel_cursor * 8
            record_count = u32(data, byal_offset)
            targets = [struct.unpack_from("<i", bmrf.payload, (frame_cursor + pos) * 12 + 4)[0] for pos in range(record_count)]
            slots = [u32(bmrf.payload, (frame_cursor + pos) * 12) for pos in range(record_count)]
            channel_rows.append({
                "channel": channel_index,
                "bmrf_start": frame_cursor,
                "bmrf_count": record_count,
                "slot_min": min(slots, default=None),
                "slot_max": max(slots, default=None),
                "targets": Counter(targets).most_common(),
            })
            channel_cursor += 1
            frame_cursor += record_count
        elements.append({
            "index": index,
            "name": name,
            "has_texture": has_texture,
            "declared_frame_count": declared_frame_count,
            "channel_count": channel_count,
            "bmrf_start": element_start,
            "bmrf_count": frame_cursor - element_start,
            "channels": channel_rows,
        })
    return {
        "path": str(path.relative_to(root)),
        "bele_count": sections["BELE"].count,
        "bmrf_count": bmrf.count,
        "byal_count": byal.count,
        "elements": elements,
        "consumed": {"channels": channel_cursor, "frames": frame_cursor},
    }


def markdown(rows: list[dict]) -> str:
    lines = ["# BILE v2：BMTI / BYAL / BMRF 时间线分段", "", "> `targets` 是 BMRF 第二 dword 的原始有符号整数频数。当前报告不把它重新命名为“已确认元素引用”。", ""]
    for report in rows:
        lines.extend([f"## `{report['path']}`", "", f"BELE：{report['bele_count']}；BMRF：{report['bmrf_count']}；BYAL：{report['byal_count']}；累计帧：{report['consumed']['frames']}。", "", "| 元素 | 名称 | 纹理 | 声明槽位 | 通道 | BMRF 起点 | BMRF 记录 |", "|---:|---|---|---:|---:|---:|---:|"])
        for element in report["elements"]:
            lines.append(f"| {element['index']} | `{element['name']}` | {'是' if element['has_texture'] else '否'} | {element['declared_frame_count']} | {element['channel_count']} | {element['bmrf_start']} | {element['bmrf_count']} |")
        lines.extend(["", "### 通道分段", "", "| 元素 | 通道 | BMRF 起点 | 记录 | 槽位范围 | BMRF 第二 dword 频数 |", "|---:|---:|---:|---:|---|---|"])
        for element in report["elements"]:
            for channel in element["channels"]:
                targets = ", ".join(f"{value}:{count}" for value, count in channel["targets"])
                lines.append(f"| {element['index']} | {channel['channel']} | {channel['bmrf_start']} | {channel['bmrf_count']} | {channel['slot_min']}–{channel['slot_max']} | `{targets}` |")
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    reports = [inspect(path, args.root) for path in args.files]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"schema": "bile-workbench.v2-timeline-segments/v1", "reports": reports}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.output.with_suffix(".md").write_text(markdown(reports), encoding="utf-8")
    print(f"已写入：{args.output}")
    print(f"已写入：{args.output.with_suffix('.md')}")


if __name__ == "__main__":
    main()
