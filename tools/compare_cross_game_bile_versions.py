#!/usr/bin/env python3
"""比较新增 EZ-Tech 样本中 BILE v3/v4 的已验证结构与字段分布。"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bile_workbench.bile_format import parse_file

DATASETS = {
    "将军的荣耀3": ROOT / "cross_game_assets" / "general3",
    "欧洲战争6": ROOT / "cross_game_assets" / "eu6",
    "世界征服者3": ROOT / "cross_game_assets" / "wc3",
    "世界征服者4（原包）": ROOT / "sample_assets",
}


def nested_keyframes(document) -> set[int]:
    indices: set[int] = set()
    for element in document.animations:
        for channel in element.channels:
            for frame in channel.frames:
                for track in frame.tracks:
                    if 0 <= track.element_index < len(document.elements) and not document.elements[track.element_index].has_texture:
                        indices.add(track.keyframe_index)
    return indices


def summarize(name: str, folder: Path) -> dict:
    rows = []
    for path in sorted(folder.glob("*.bin")):
        if path.read_bytes()[:4] != b"BILE":
            continue
        document = parse_file(path)
        nested = nested_keyframes(document)
        modes_all = Counter(keyframe.playback_mode for keyframe in document.keyframes)
        modes_nested = Counter(document.keyframes[index].playback_mode for index in nested)
        nonzero_phase_nested = sum(document.keyframes[index].initial_phase != 0 for index in nested)
        rows.append({
            "file": path.name,
            "version": document.header.version,
            "fps": document.header.fps,
            "header_size": document.header.header_size,
            "section_count": document.header.section_count,
            "tags": list(document.sections),
            "section_record_counts": {tag: section.count for tag, section in document.sections.items()},
            "section_opaque_values": {tag: section.opaque_value for tag, section in document.sections.items() if section.opaque_value is not None},
            "keyframes": len(document.keyframes),
            "elements": len(document.elements),
            "animations": len(document.animations),
            "sprites": len(document.sprites),
            "graph_cycles": len(document.graph_cycles),
            "playback_modes_all": dict(modes_all),
            "playback_modes_nested": dict(modes_nested),
            "nested_keyframes": len(nested),
            "nonzero_phase_nested": nonzero_phase_nested,
        })
    return {"name": name, "rows": rows}


def compact_counter(values) -> dict:
    result = Counter(values)
    return {str(key): count for key, count in sorted(result.items(), key=lambda entry: str(entry[0]))}


def main() -> int:
    datasets = [summarize(name, folder) for name, folder in DATASETS.items()]
    output = {"schema": "bile-workbench.cross-game-bile-compare/v1", "datasets": datasets}
    json_path = ROOT / "research" / "cross_game_bile_version_compare.json"
    json_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# BILE v3/v4 跨游戏结构比较", ""]
    for dataset in datasets:
        rows = dataset["rows"]
        versions = compact_counter(row["version"] for row in rows)
        fps = compact_counter(row["fps"] for row in rows)
        header_sizes = compact_counter(row["header_size"] for row in rows)
        section_counts = compact_counter(row["section_count"] for row in rows)
        tags = compact_counter(tuple(row["tags"]) for row in rows)
        cycles = sum(row["graph_cycles"] for row in rows)
        nested = sum(row["nested_keyframes"] for row in rows)
        nonzero = sum(row["nonzero_phase_nested"] for row in rows)
        mode_all = Counter()
        mode_nested = Counter()
        for row in rows:
            mode_all.update({int(key): value for key, value in row["playback_modes_all"].items()})
            mode_nested.update({int(key): value for key, value in row["playback_modes_nested"].items()})
        lines.extend([
            f"## {dataset['name']}", "",
            "| 字段 | 分布或总计 |", "|---|---|",
            f"| BIN 数 | {len(rows)} |",
            f"| 版本 | `{versions}` |",
            f"| FPS | `{fps}` |",
            f"| 头长度 | `{header_sizes}` |",
            f"| 顶层节数 | `{section_counts}` |",
            f"| 顶层标签序列 | `{tags}` |",
            f"| 动画引用图循环 | {cycles} |",
            f"| 全部 BELE playback_mode | `{dict(sorted(mode_all.items()))}` |",
            f"| 嵌套动画 BELE playback_mode | `{dict(sorted(mode_nested.items()))}` |",
            f"| 嵌套动画引用关键帧 | {nested} |",
            f"| 嵌套引用的非零 initial_phase | {nonzero} |",
            "",
        ])
    md_path = ROOT / "research" / "cross_game_bile_version_compare.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(md_path)
    print(json_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
