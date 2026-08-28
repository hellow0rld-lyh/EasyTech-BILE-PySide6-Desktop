#!/usr/bin/env python3
"""只读比较 BILE v2、v3、v4 的顶层节布局和可推导记录宽度。"""
from __future__ import annotations

import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = {
    "将军的荣耀1 · mtank": ROOT / "cross_game_assets" / "general1" / "mtank.bin",
    "将军的荣耀1 · artillery": ROOT / "cross_game_assets" / "general1" / "artillery_hd.bin",
    "欧洲战争4 · armoredcar": ROOT / "cross_game_assets" / "eu4" / "army_armoredcar.bin",
    "世界征服者4 · infantry": ROOT / "cross_game_assets" / "wc4_extended" / "unit_infantry.bin",
}


def u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def f32(data: bytes, offset: int) -> float:
    return struct.unpack_from("<f", data, offset)[0]


def layout(path: Path) -> tuple[dict, list[dict]]:
    data = path.read_bytes()
    header = {
        "version": u32(data, 4),
        "payload_size": u32(data, 8),
        "header_size": u16(data, 12),
        "section_count": u16(data, 14),
        "fps": f32(data, 16),
        "file_size": len(data),
    }
    cursor = header["header_size"]
    sections = []
    for _ in range(header["section_count"]):
        tag = data[cursor:cursor + 4].decode("ascii")
        total_size = u32(data, cursor + 4)
        count = u32(data, cursor + 8)
        header_width = 12 if tag == "BRTS" else 16
        payload_size = total_size - header_width
        sections.append({
            "tag": tag,
            "offset": cursor,
            "total_size": total_size,
            "count": count,
            "opaque": None if tag == "BRTS" else u32(data, cursor + 12),
            "payload_size": payload_size,
            "per_record": (payload_size / count) if count else None,
            "payload_offset": cursor + header_width,
        })
        cursor += total_size
    if cursor != len(data):
        raise ValueError(f"顶层节未正好消费文件：0x{cursor:X} != 0x{len(data):X}")
    return header, sections


def v2_bele_words(path: Path, sections: list[dict]) -> list[str]:
    data = path.read_bytes()
    bele = next(section for section in sections if section["tag"] == "BELE")
    start = bele["payload_offset"]
    width = int(bele["per_record"] or 0)
    return [f"+0x{offset:02X}=0x{u32(data, start + offset):08X}" for offset in range(0, width, 4)]


def main() -> int:
    lines = ["# BILE v2 / v3 / v4 顶层布局探针", "", "> 只读结构测量。`每记录字节` 仅由块载荷长度除以记录数得出，尚未被解释为完整字段语义。", ""]
    for name, path in SAMPLES.items():
        header, sections = layout(path)
        lines.extend([
            f"## {name}",
            "",
            f"- 文件：`{path.relative_to(ROOT)}`",
            f"- 头：版本 `{header['version']}`，头长 `{header['header_size']}`，节数 `{header['section_count']}`，FPS `{header['fps']:.3f}`。",
            "",
            "| 节 | 偏移 | 总长度 | 记录数 | 负载长度 | 每记录字节 | 不透明值 |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ])
        for section in sections:
            per_record = "—" if section["per_record"] is None else f"{section['per_record']:.3f}"
            opaque = "—" if section["opaque"] is None else f"0x{section['opaque']:08X}"
            lines.append(
                f"| `{section['tag']}` | 0x{section['offset']:X} | {section['total_size']} | {section['count']} | "
                f"{section['payload_size']} | {per_record} | {opaque} |"
            )
        if header["version"] == 2:
            lines.extend(["", "首条 BELE 的 32 位原始字：", "", "```text", " ".join(v2_bele_words(path, sections)), "```"])
        lines.append("")
    output = ROOT / "research" / "bile_v2_layout_probe.md"
    output.write_text("\n".join(lines), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
