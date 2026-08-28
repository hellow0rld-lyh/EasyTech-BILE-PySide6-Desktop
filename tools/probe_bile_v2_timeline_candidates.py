#!/usr/bin/env python3
"""只读展示 BILE v2 五节容器中可能合并的 BMRF/BXDI 时间线记录。"""
from __future__ import annotations

import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "cross_game_assets" / "general1"


def u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def s32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<i", data, offset)[0]


def u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def sections(data: bytes) -> dict[str, dict]:
    cursor = u16(data, 12)
    result = {}
    for _ in range(u16(data, 14)):
        tag = data[cursor:cursor + 4].decode("ascii")
        total = u32(data, cursor + 4)
        header = 12 if tag == "BRTS" else 16
        result[tag] = {"offset": cursor, "count": u32(data, cursor + 8), "payload": cursor + header, "payload_size": total - header}
        cursor += total
    return result


def names(data: bytes, brts: dict) -> dict[int, str]:
    payload = data[brts["payload"]:brts["payload"] + brts["payload_size"]]
    result = {}
    offset = 0
    while offset < len(payload):
        end = payload.find(b"\0", offset)
        if end < 0:
            break
        if end > offset:
            result[offset] = payload[offset:end].decode("utf-8")
        offset = end + 1
    return result


def main() -> int:
    sample_paths = sorted(FOLDER.glob("*.bin"))
    lines = [
        "# 将军的荣耀1 BILE v2 时间线候选字段探针",
        "",
        "> 所有值均为原始小端整数视图。该报告不将候选字段提前命名为已确认语义。",
        "",
    ]
    for path in sample_paths:
        data = path.read_bytes()
        section = sections(data)
        if u32(data, 4) != 2:
            continue
        bele, bmrf, byal, bmti, brts = (section[tag] for tag in ("BELE", "BMRF", "BYAL", "BMTI", "BRTS"))
        string_map = names(data, brts)
        element_rows = []
        for index in range(bmti["count"]):
            offset = bmti["payload"] + index * 56
            element_rows.append((index, u32(data, offset), string_map.get(u32(data, offset + 4), f"<bad@{u32(data, offset + 4):X}>"), u32(data, offset + 24), u32(data, offset + 28), u32(data, offset + 32)))
        bmrf_rows = []
        for index in range(bmrf["count"]):
            offset = bmrf["payload"] + index * 12
            raw = (u32(data, offset), u32(data, offset + 4), u32(data, offset + 8))
            bmrf_rows.append((index, *raw, s32(data, offset + 4)))
        lines.extend([
            f"## `{path.name}`",
            "",
            f"- 计数：BELE={bele['count']}，BMRF={bmrf['count']}，BYAL={byal['count']}，BMTI={bmti['count']}。",
            f"- 记录宽度：BELE={bele['payload_size'] // bele['count']}，BMRF={bmrf['payload_size'] // bmrf['count']}，BYAL={byal['payload_size'] // byal['count']}，BMTI={bmti['payload_size'] // bmti['count']}。",
            "",
            "### BMTI 元素壳",
            "",
            "| 序号 | 自索引 | 名称 | type@0x18 | frame_count@0x1C | channel_count@0x20 |",
            "|---:|---:|---|---:|---:|---:|",
        ])
        for row in element_rows:
            lines.append(f"| {row[0]} | {row[1]} | {row[2]} | {row[3]} | {row[4]} | {row[5]} |")
        lines.extend([
            "",
            "### BMRF 的 12 字节原始字",
            "",
            "| 序号 | dword@+0x00 | dword@+0x04（有符号） | dword@+0x08 |",
            "|---:|---:|---:|---:|",
        ])
        for index, first, second, third, signed_second in bmrf_rows:
            lines.append(f"| {index} | {first} | {second} / {signed_second} | {third} |")
        lines.extend([
            "",
            "### BYAL 的 8 字节原始字",
            "",
            "| 序号 | dword@+0x00 | dword@+0x04 |",
            "|---:|---:|---:|",
        ])
        for index in range(byal["count"]):
            offset = byal["payload"] + index * 8
            lines.append(f"| {index} | {u32(data, offset)} | {u32(data, offset + 4)} |")
        lines.append("")
    output = ROOT / "research" / "bile_v2_timeline_candidate_probe.md"
    output.write_text("\n".join(lines), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
