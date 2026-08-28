#!/usr/bin/env python3
"""只读盘点新增跨代 EZ-Tech 三件套，并严格验证 BILE 容器与 XML 图集。"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from PIL import UnidentifiedImageError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bile_workbench.bile_format import BileFormatError, parse_file
from bile_workbench.preview_renderer import load_atlas

DATASETS = {
    "欧洲战争4": ROOT / "cross_game_assets" / "eu4",
    "将军的荣耀1": ROOT / "cross_game_assets" / "general1",
    "世界征服者4（扩展集）": ROOT / "cross_game_assets" / "wc4_extended",
}


def paired_image(bin_path: Path) -> Path | None:
    for suffix in (".webp", ".png"):
        candidate = bin_path.with_suffix(suffix)
        if candidate.exists():
            return candidate
    return None


def magic_label(raw_magic: bytes) -> str:
    decoded = raw_magic.decode("ascii", errors="replace")
    return decoded if decoded.isprintable() else f"0x{raw_magic.hex().upper()}"


def probe_dataset(label: str, folder: Path) -> dict:
    entries: list[dict] = []
    for bin_path in sorted(folder.glob("*.bin")):
        xml_path = bin_path.with_suffix(".xml")
        image_path = paired_image(bin_path)
        raw_magic = bin_path.read_bytes()[:4]
        entry: dict = {
            "file": bin_path.name,
            "bytes": bin_path.stat().st_size,
            "magic": magic_label(raw_magic),
            "xml": xml_path.name if xml_path.exists() else None,
            "image": image_path.name if image_path else None,
        }
        if raw_magic != b"BILE":
            entry.update({"status": "not_bile", "note": "非 BILE 文件，未调用 BILE 解析器。"})
            entries.append(entry)
            continue
        try:
            document = parse_file(bin_path)
            entry.update({
                "status": "parsed",
                "version": document.header.version,
                "fps": document.header.fps,
                "sections": list(document.sections),
                "keyframes": len(document.keyframes),
                "elements": len(document.elements),
                "animations": len(document.animations),
                "sprites": len(document.sprites),
                "graph_cycles": len(document.graph_cycles),
            })
            if xml_path.exists() and image_path is not None:
                atlas = load_atlas(xml_path, image_path)
                entry.update({
                    "atlas_status": "loaded",
                    "atlas_regions": len(atlas.regions),
                    "atlas_format": atlas.source_image_format,
                    "xml_declaration": atlas.xml_had_declaration,
                    "xml_stripped_controls": atlas.stripped_control_chars,
                    "fractional_geometry_regions": atlas.fractional_geometry_regions,
                    "unresolved_sprite_names": sum(sprite.name not in atlas.regions for sprite in document.sprites),
                })
            else:
                entry["atlas_status"] = "missing_triplet_member"
        except (BileFormatError, OSError, ValueError, KeyError, UnidentifiedImageError) as exc:
            entry.update({"status": "error", "note": str(exc)})
        entries.append(entry)
    return {"dataset": label, "folder": str(folder), "files": entries}


def write_markdown(reports: list[dict], target: Path) -> None:
    lines = [
        "# 新增跨代 BILE / 三件套资产盘点",
        "",
        "> 本报告由只读探针生成。BILE 通过意味着文件已满足当前解析器的容器、记录边界和累计时间线校验；并不单独证明游戏运行时的兵模组合行为。",
        "",
    ]
    for report in reports:
        files = report["files"]
        parsed = [item for item in files if item["status"] == "parsed"]
        failed = [item for item in files if item["status"] == "error"]
        non_bile = [item for item in files if item["status"] == "not_bile"]
        triads = [item for item in parsed if item.get("atlas_status") == "loaded"]
        versions = Counter(item["version"] for item in parsed)
        sections = Counter(tuple(item["sections"]) for item in parsed)
        formats = Counter(item.get("atlas_format") for item in triads)
        lines.extend([
            f"## {report['dataset']}",
            "",
            "| 指标 | 值 |",
            "|---|---:|",
            f"| BIN 文件 | {len(files)} |",
            f"| 严格 BILE 解析通过 | {len(parsed)} |",
            f"| 严格 BILE 解析失败 | {len(failed)} |",
            f"| 非 BILE 二进制 | {len(non_bile)} |",
            f"| 可加载同名三件套 | {len(triads)} |",
            f"| BILE 版本 | `{dict(versions)}` |",
            f"| 图集格式 | `{dict(formats)}` |",
            f"| 顶层块序列 | `{dict(sections)}` |",
            "",
            "| BIN | BILE | FPS | 动画/精灵 | 图集 | 图集区域 | 未解析精灵名 |",
            "|---|---:|---:|---:|---|---:|---:|",
        ])
        for item in parsed:
            lines.append(
                f"| `{item['file']}` | v{item['version']} | {item['fps']:.3f} | "
                f"{item['animations']}/{item['sprites']} | {item.get('atlas_format', '—').upper()} | "
                f"{item.get('atlas_regions', '—')} | {item.get('unresolved_sprite_names', '—')} |"
            )
        if failed or non_bile:
            lines.extend(["", "### 未纳入 BILE 三件套通过统计的文件", "", "| 文件 | 分类 | 原因 |", "|---|---|---|"])
            for item in [*failed, *non_bile]:
                lines.append(f"| `{item['file']}` | {item['status']} | {item.get('note', '')} |")
        lines.append("")
    target.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    reports = [probe_dataset(label, folder) for label, folder in DATASETS.items()]
    research = ROOT / "research"
    json_path = research / "cross_generation_asset_inventory.json"
    md_path = research / "cross_generation_asset_inventory.md"
    json_path.write_text(json.dumps({"schema": "bile-workbench.cross-generation-inventory/v1", "datasets": reports}, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(reports, md_path)
    print(md_path)
    print(json_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
