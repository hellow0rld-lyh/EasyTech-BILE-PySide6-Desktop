#!/usr/bin/env python3
"""跨样本验证 BILE v2 五节容器的保守候选时间线解码约束。"""
from __future__ import annotations

import math
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "cross_game_assets" / "general1"


def u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def s32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<i", data, offset)[0]


def f32(data: bytes, offset: int) -> float:
    return struct.unpack_from("<f", data, offset)[0]


def parse_sections(data: bytes) -> dict[str, dict]:
    cursor = u16(data, 12)
    output = {}
    for _ in range(u16(data, 14)):
        tag = data[cursor:cursor + 4].decode("ascii")
        total_size = u32(data, cursor + 4)
        header_size = 12 if tag == "BRTS" else 16
        output[tag] = {
            "payload": cursor + header_size,
            "payload_size": total_size - header_size,
            "count": u32(data, cursor + 8),
        }
        cursor += total_size
    if cursor != len(data):
        raise ValueError("顶层节未完整消费文件")
    return output


def main() -> int:
    files = sorted(FOLDER.glob("*.bin"))
    rows = []
    for path in files:
        data = path.read_bytes()
        sections = parse_sections(data)
        assert data[:4] == b"BILE"
        assert u32(data, 4) == 2
        assert tuple(sections) == ("BELE", "BMRF", "BYAL", "BMTI", "BRTS")
        assert sections["BELE"]["payload_size"] == sections["BELE"]["count"] * 48
        assert sections["BMRF"]["payload_size"] == sections["BMRF"]["count"] * 12
        assert sections["BYAL"]["payload_size"] == sections["BYAL"]["count"] * 8
        assert sections["BMTI"]["payload_size"] == sections["BMTI"]["count"] * 56
        assert sections["BELE"]["count"] == sections["BMRF"]["count"]
        element_count = sections["BMTI"]["count"]
        element_cursor = 0
        channel_cursor = 0
        frame_cursor = 0
        for element_index in range(element_count):
            offset = sections["BMTI"]["payload"] + element_index * 56
            assert u32(data, offset) == element_index
            channel_count = u32(data, offset + 32)
            for _ in range(channel_count):
                channel_offset = sections["BYAL"]["payload"] + channel_cursor * 8
                frame_count = u32(data, channel_offset)
                for _ in range(frame_count):
                    frame_offset = sections["BMRF"]["payload"] + frame_cursor * 12
                    slot = u32(data, frame_offset)
                    target = s32(data, frame_offset + 4)
                    assert slot < 1_000_000
                    assert target == -1 or 0 <= target < element_count
                    frame_cursor += 1
                channel_cursor += 1
            element_cursor += 1
        assert element_cursor == element_count
        assert channel_cursor == sections["BYAL"]["count"]
        assert frame_cursor == sections["BMRF"]["count"]
        alphas = [f32(data, sections["BELE"]["payload"] + index * 48 + 24) for index in range(sections["BELE"]["count"])]
        assert all(math.isfinite(alpha) and 0.0 <= alpha <= 1.0 for alpha in alphas)
        rows.append((path.name, len(alphas), min(alphas), max(alphas)))

    output = ROOT / "research" / "bile_v2_candidate_constraint_check.md"
    lines = [
        "# 将军的荣耀1 BILE v2 候选解析约束检查",
        "",
        "> 此检查验证的是跨样本的结构约束，不单独确认所有字段的运行时语义。",
        "",
        "| 文件 | BELE / BMRF 数 | BELE +0x18 浮点范围 |",
        "|---|---:|---|",
    ]
    for name, count, low, high in rows:
        lines.append(f"| `{name}` | {count} | {low:.6f} .. {high:.6f} |")
    lines.extend([
        "",
        "全部样本均满足：v2 五节顺序 `BELE → BMRF → BYAL → BMTI → BRTS`；BELE 为 48 字节、BMRF 为 12 字节、BYAL 为 8 字节、BMTI 为 56 字节；BELE 与 BMRF 计数相等；按 BMTI 通道数和 BYAL 首字的帧数累计可恰好消费 BMRF；每个 BMRF 的第二个 dword 落在有效 BMTI 索引或 -1 内。",
    ])
    output.write_text("\n".join(lines), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
