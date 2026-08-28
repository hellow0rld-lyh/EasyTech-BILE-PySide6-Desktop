#!/usr/bin/env python3
"""只读探针：生成 BIN/XML/WebP 三件套的可复现结构报告。"""
from __future__ import annotations

import collections
import hashlib
import math
import re
import struct
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "sample_assets"
REPORT = ROOT / "research" / "bin_xml_structural_probe.md"


def printable_runs(data: bytes, minimum: int = 4) -> list[tuple[int, str]]:
    runs: list[tuple[int, str]] = []
    start: int | None = None
    for index, byte in enumerate(data + b"\0"):
        if 32 <= byte <= 126:
            if start is None:
                start = index
        elif start is not None:
            if index - start >= minimum:
                runs.append((start, data[start:index].decode("ascii", "replace")))
            start = None
    return runs


def entropy(data: bytes) -> float:
    if not data:
        return 0.0
    counts = collections.Counter(data)
    length = len(data)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


def u32_le(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def s32_le(data: bytes, offset: int) -> int:
    return struct.unpack_from("<i", data, offset)[0]


def f32_le(data: bytes, offset: int) -> float:
    return struct.unpack_from("<f", data, offset)[0]


def fmt_float(value: float) -> str:
    return f"{value:.6g}" if math.isfinite(value) else str(value)


def xml_summary(path: Path) -> dict:
    """解析标准 XML 或该游戏使用的多顶层节点 XML 片段。"""
    text = path.read_text(encoding="utf-8-sig", errors="strict")
    try:
        root = ET.fromstring(text)
        fragment = False
    except ET.ParseError:
        # 原包以 <Texture/> 开头，随后并列 <Images>、<Animation> 等顶层节点。
        # 包一层仅用于读取，输出和回写仍保留原始片段布局。
        root = ET.fromstring(f"<ResourceFragment>{text}</ResourceFragment>")
        fragment = True
    tags = collections.Counter(elem.tag for elem in root.iter())
    attributes = collections.Counter(key for elem in root.iter() for key in elem.attrib)
    children = list(root)
    return {
        "root": root,
        "tags": tags,
        "attributes": attributes,
        "children": children,
        "fragment": fragment,
    }


def candidate_offsets(data: bytes) -> list[tuple[int, int]]:
    """从 4 字节对齐单元中列出看似指向本文件的整数。"""
    candidates: list[tuple[int, int]] = []
    for pos in range(0, len(data) - 3, 4):
        value = u32_le(data, pos)
        if 0 < value < len(data) and value % 4 == 0:
            candidates.append((pos, value))
    return candidates


def format_bytes(data: bytes, limit: int = 96) -> str:
    parts = []
    for row_start in range(0, min(len(data), limit), 16):
        row = data[row_start:row_start + 16]
        hexes = " ".join(f"{b:02x}" for b in row)
        text = "".join(chr(b) if 32 <= b <= 126 else "." for b in row)
        parts.append(f"{row_start:08x}  {hexes:<47}  |{text}|")
    return "\n".join(parts)


def analyze_triplet(bin_path: Path) -> str:
    stem = bin_path.stem
    data = bin_path.read_bytes()
    xml_path = bin_path.with_suffix(".xml")
    webp_path = bin_path.with_suffix(".webp")
    lines: list[str] = [f"## `{stem}`", ""]
    lines.append("| 项目 | 值 |")
    lines.append("|---|---|")
    lines.append(f"| BIN 字节数 | `{len(data)}` |")
    lines.append(f"| SHA-256 | `{hashlib.sha256(data).hexdigest()}` |")
    lines.append(f"| 信息熵 | `{entropy(data):.4f}` bit/byte |")
    lines.append(f"| XML | `{'存在' if xml_path.exists() else '缺失'}` |")
    lines.append(f"| WebP | `{'存在' if webp_path.exists() else '缺失'}` |")
    lines.append("")
    lines.append("### BIN 起始字节")
    lines.append("")
    lines.append("```text")
    lines.append(format_bytes(data))
    lines.append("```")
    lines.append("")
    lines.append("### 前 64 字节的 32 位小端解释")
    lines.append("")
    lines.append("| 偏移 | `u32` | `s32` | `f32` |")
    lines.append("|---:|---:|---:|---:|")
    for pos in range(0, min(64, len(data) - 3), 4):
        lines.append(
            f"| `0x{pos:04X}` | `{u32_le(data, pos)}` | `{s32_le(data, pos)}` | `{fmt_float(f32_le(data, pos))}` |"
        )
    lines.append("")
    offs = candidate_offsets(data)
    lines.append("### 潜在的 4 字节对齐文件内偏移")
    lines.append("")
    lines.append(
        f"扫描到 **{len(offs)}** 个候选。下表仅列出前 96 个；该规则不代表字段已被确认。"
    )
    lines.append("")
    lines.append("| 字段位置 | 值 | 指向字节（前 16） |")
    lines.append("|---:|---:|---|")
    for pos, value in offs[:96]:
        preview = data[value:value + 16].hex(" ")
        lines.append(f"| `0x{pos:04X}` | `0x{value:04X}` / `{value}` | `{preview}` |")
    lines.append("")
    strings = printable_runs(data)
    lines.append("### ASCII 字符串")
    lines.append("")
    if strings:
        lines.append("| 偏移 | 文本 |")
        lines.append("|---:|---|")
        for pos, text in strings[:80]:
            lines.append(f"| `0x{pos:04X}` | `{text.replace('`', "'")}` |")
    else:
        lines.append("未发现长度至少为 4 的 ASCII 字符串。")
    lines.append("")
    if xml_path.exists():
        summary = xml_summary(xml_path)
        root = summary["root"]
        lines.append("### XML 结构")
        lines.append("")
        if summary["fragment"]:
            lines.append("原文件不是单根 XML 文档，而是多个并列顶层节点组成的 **XML 片段**；探针以虚拟 `<ResourceFragment>` 容器读取，绝不写回该容器。")
        else:
            lines.append(f"根元素为 `<{root.tag}>`，属性：`{dict(root.attrib)}`。")
        lines.append("")
        lines.append("| 元素 | 数量 |")
        lines.append("|---|---:|")
        for tag, count in summary["tags"].most_common():
            lines.append(f"| `{tag}` | `{count}` |")
        lines.append("")
        lines.append("| 属性名 | 出现次数 |")
        lines.append("|---|---:|")
        for attr, count in summary["attributes"].most_common():
            lines.append(f"| `{attr}` | `{count}` |")
        lines.append("")
        lines.append("```xml")
        xml_text = xml_path.read_text(encoding="utf-8", errors="replace")
        lines.extend(xml_text.splitlines()[:80])
        if len(xml_text.splitlines()) > 80:
            lines.append("<!-- 后续内容省略；原始样本保持不变 -->")
        lines.append("```")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    bins = sorted(ASSET_DIR.glob("anim_*.bin"))
    if not bins:
        print(f"未在 {ASSET_DIR} 找到 anim_*.bin", file=sys.stderr)
        return 2
    sections = [
        "# 动画三件套二进制结构探针报告",
        "",
        "> 本报告仅记录机器可复现的观察值。‘潜在偏移’是宽松启发式，不应被误读为已确认格式字段。",
        "",
        f"样本目录：`{ASSET_DIR}`。共分析 `{len(bins)}` 组 `anim_*` 三件套。",
        "",
    ]
    for bin_path in bins:
        sections.append(analyze_triplet(bin_path))
        sections.append("")
    REPORT.write_text("\n".join(sections), encoding="utf-8")
    print(REPORT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
