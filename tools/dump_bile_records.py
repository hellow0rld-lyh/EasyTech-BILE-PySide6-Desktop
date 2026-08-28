#!/usr/bin/env python3
"""只读解码 BILE 的已验证块边界，并转储小样本记录用于语义逆向。"""
from __future__ import annotations

import argparse
import math
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSET = ROOT / "sample_assets"
OUT = ROOT / "research" / "bile_record_dumps.md"
CANONICAL = (b"BELE", b"BXDI", b"BMRF", b"BYAL", b"BMTI", b"BRTS")


def u32(data: bytes, off: int) -> int:
    return struct.unpack_from("<I", data, off)[0]


def s32(data: bytes, off: int) -> int:
    return struct.unpack_from("<i", data, off)[0]


def f32(data: bytes, off: int) -> float:
    return struct.unpack_from("<f", data, off)[0]


def float_text(value: float) -> str:
    if not math.isfinite(value):
        return "NaN" if math.isnan(value) else ("+∞" if value > 0 else "-∞")
    return f"{value:.6g}"


def find_chunks(data: bytes) -> list[tuple[bytes, int, int, int, int]]:
    chunks: list[tuple[bytes, int, int, int, int]] = []
    cursor = 20
    while cursor + 12 <= len(data):
        tag = data[cursor:cursor + 4]
        if tag not in CANONICAL:
            raise ValueError(f"在 0x{cursor:X} 预期标准块，实际为 {tag!r}")
        total = u32(data, cursor + 4)
        count = u32(data, cursor + 8)
        if total < 12 or cursor + total > len(data):
            raise ValueError(f"块 {tag!r} 的长度 {total} 越界")
        header = 12 if tag == b"BRTS" else 16
        if total < header:
            raise ValueError(f"块 {tag!r} 小于头部长度")
        chunks.append((tag, cursor, total, count, header))
        cursor += total
    return chunks


def cell(raw: bytes) -> str:
    unsigned = struct.unpack("<I", raw)[0]
    signed = struct.unpack("<i", raw)[0]
    floating = struct.unpack("<f", raw)[0]
    return f"`0x{unsigned:08X}` / `{signed}` / `{float_text(floating)}`"


def markdown_for(path: Path) -> list[str]:
    data = path.read_bytes()
    chunks = find_chunks(data)
    lines = [f"## `{path.name}`", "", "| 块 | 总长度 | 条目数 | 头部长度 | 推导条目宽度 | 头部第 4 个字 |", "|---|---:|---:|---:|---:|---|"]
    for tag, offset, total, count, header in chunks:
        width = (total - header) // count if count else "—"
        fourth = f"`0x{u32(data, offset + 12):08X}`" if header == 16 else "—"
        lines.append(f"| `{tag.decode()}` | `{total}` | `{count}` | `{header}` | `{width}` | {fourth} |")
    lines.append("")
    for tag, offset, total, count, header in chunks:
        name = tag.decode()
        payload = data[offset + header:offset + total]
        lines += [f"### `{name}`", ""]
        if tag == b"BRTS":
            strings = [p.decode("utf-8", "replace") for p in payload.split(b"\0") if p]
            lines.append(f"UTF-8 零结尾字符串共 `{len(strings)}` 个：")
            lines.append("")
            lines.append("| 序号 | 起始相对偏移 | 文本 |")
            lines.append("|---:|---:|---|")
            cursor = 0
            index = 0
            while cursor < len(payload):
                end = payload.find(b"\0", cursor)
                if end < 0:
                    break
                raw = payload[cursor:end]
                if raw:
                    lines.append(f"| `{index}` | `0x{cursor:X}` | `{raw.decode('utf-8', 'replace').replace('`', "'")}` |")
                    index += 1
                cursor = end + 1
            lines.append("")
            continue
        width = (total - header) // count
        limit = count if path.stem == "anim_failure" else min(count, 8)
        lines.append(f"以下为前 `{limit}` / `{count}` 个、每个 `{width}` 字节的条目。每单元按 `u32` / `s32` / `f32` 三重解释显示，未断言语义。")
        lines.append("")
        column_count = width // 4
        lines.append("| 条目 | " + " | ".join(f"+0x{i * 4:02X}" for i in range(column_count)) + " |")
        lines.append("|---:|" + "|".join("---" for _ in range(column_count)) + "|")
        for index in range(limit):
            record = payload[index * width:(index + 1) * width]
            cols = [cell(record[pos:pos + 4]) for pos in range(0, width, 4)]
            lines.append(f"| `{index}` | " + " | ".join(cols) + " |")
        lines.append("")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("names", nargs="*", help="不含扩展名的动画名；默认选取 failure、grade、fire")
    args = parser.parse_args()
    names = args.names or ["anim_failure", "anim_grade", "anim_fire"]
    lines = [
        "# BILE 定长记录转储",
        "",
        "> 边界判定来自 `BILE` 容器的可加和长度规则。数值三重解释仅为逆向辅助；字段语义需由跨块引用和可视预览继续验证。",
        "",
    ]
    for name in names:
        path = ASSET / f"{name}.bin"
        if not path.exists():
            raise SystemExit(f"样本不存在：{path}")
        lines.extend(markdown_for(path))
        lines.append("")
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
