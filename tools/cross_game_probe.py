#!/usr/bin/env python3
"""对新增 EZ-Tech 资源集执行只读 BILE/XML/图集跨游戏兼容性探针。"""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from PIL import UnidentifiedImageError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bile_workbench.bile_format import BileFormatError, parse_file
from bile_workbench.preview_renderer import load_atlas, render_frame

DATASETS = {
    "将军的荣耀3": ROOT / "cross_game_assets" / "general3",
    "欧洲战争6": ROOT / "cross_game_assets" / "eu6",
    "世界征服者3": ROOT / "cross_game_assets" / "wc3",
}


def image_for(stem: Path) -> Path | None:
    for ext in (".webp", ".png"):
        candidate = stem.with_suffix(ext)
        if candidate.exists():
            return candidate
    return None


def nonuniform(image) -> bool:
    iterator = image.getdata()
    first = next(iter(iterator), None)
    return first is not None and any(pixel != first for pixel in image.getdata())


def probe_dataset(name: str, folder: Path) -> dict:
    results = []
    for bin_path in sorted(folder.glob("*.bin")):
        xml = bin_path.with_suffix(".xml")
        image = image_for(bin_path)
        raw_magic = bin_path.read_bytes()[:4]
        decoded_magic = raw_magic.decode("ascii", errors="replace")
        magic_text = decoded_magic if decoded_magic.isprintable() else f"0x{raw_magic.hex().upper()}"
        item = {
            "bin": bin_path.name,
            "bytes": bin_path.stat().st_size,
            "xml": xml.name if xml.exists() else None,
            "image": image.name if image else None,
            "magic": magic_text,
        }
        if raw_magic != b"BILE":
            item.update({"parse": "not_bile", "error": "不是 BILE 动画容器；已跳过严格 BILE 解析。"})
            results.append(item)
            continue
        try:
            document = parse_file(bin_path)
            item.update({
                "parse": "ok",
                "version": document.header.version,
                "fps": document.header.fps,
                "tags": list(document.sections),
                "keyframes": len(document.keyframes),
                "elements": len(document.elements),
                "animations": len(document.animations),
                "sprites": len(document.sprites),
                "graph_cycles": len(document.graph_cycles),
            })
            if xml.exists() and image:
                atlas = load_atlas(xml, image)
                item["atlas_regions"] = len(atlas.regions)
                unresolved = [element.name for element in document.sprites if element.name not in atlas.regions]
                item["unresolved_sprite_names"] = len(unresolved)
                if document.animations:
                    target = document.animations[0]
                    slots = sorted({0, max(0, target.frame_count // 2), max(0, target.frame_count - 1)})
                    renders = []
                    for slot in slots:
                        frame = render_frame(document, atlas, target.name, slot, canvas_size=(256, 192))
                        renders.append({"slot": slot, "nonuniform": nonuniform(frame)})
                    item["render_samples"] = renders
            else:
                item["triad"] = "missing XML or image"
        except (BileFormatError, OSError, ValueError, KeyError, ET.ParseError, UnidentifiedImageError) as exc:
            item.update({"parse": "error", "error": str(exc)})
        results.append(item)
    return {"name": name, "folder": str(folder), "files": results}


def main() -> int:
    reports = [probe_dataset(name, folder) for name, folder in DATASETS.items()]
    output = {"schema": "bile-workbench.cross-game-probe/v1", "datasets": reports}
    research = ROOT / "research"
    json_path = research / "cross_game_compatibility_probe.json"
    json_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# 跨游戏 BILE/XML/图集兼容性探针", ""]
    for dataset in reports:
        files = dataset["files"]
        parsed = [item for item in files if item.get("parse") == "ok"]
        errors = [item for item in files if item.get("parse") == "error"]
        non_bile = [item for item in files if item.get("parse") == "not_bile"]
        versions = Counter(item.get("version") for item in parsed)
        tags = Counter(tuple(item.get("tags", [])) for item in parsed)
        triads = [item for item in parsed if item.get("xml") and item.get("image")]
        rendered = [item for item in triads if item.get("render_samples")]
        lines.extend([
            f"## {dataset['name']}", "",
            "| 指标 | 值 |", "|---|---:|",
            f"| BIN 数量 | {len(files)} |",
            f"| 严格解析通过 | {len(parsed)} |",
            f"| 严格解析失败 | {len(errors)} |",
            f"| 非 BILE 二进制 | {len(non_bile)} |",
            f"| 完整三件套 | {len(triads)} |",
            f"| 已生成代表帧 | {len(rendered)} |",
            f"| BILE 版本分布 | `{dict(versions)}` |",
            f"| 顶层标签序列分布 | `{dict(tags)}` |",
            "",
        ])
        if non_bile:
            lines.extend(["### 非 BILE 二进制", "", "| 文件 | 魔数 | 处理 |", "|---|---|---|"])
            for item in non_bile:
                lines.append(f"| `{item['bin']}` | `{item['magic']}` | {item['error']} |")
            lines.append("")
        if errors:
            lines.extend(["### 未通过严格解析的 BILE", "", "| 文件 | 魔数 | 原因 |", "|---|---|---|"])
            for item in errors:
                lines.append(f"| `{item['bin']}` | `{item['magic']}` | {item['error']} |")
            lines.append("")
        lines.extend(["### 已通过样本", "", "| BIN | 版本 | FPS | 动画/精灵 | 关键帧 | 图集区域 | 未解析精灵名 |", "|---|---:|---:|---:|---:|---:|---:|"])
        for item in parsed:
            lines.append(f"| `{item['bin']}` | {item['version']} | {item['fps']:.3f} | {item['animations']}/{item['sprites']} | {item['keyframes']} | {item.get('atlas_regions', '—')} | {item.get('unresolved_sprite_names', '—')} |")
        lines.append("")
    md_path = research / "cross_game_compatibility_probe.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(md_path)
    print(json_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
