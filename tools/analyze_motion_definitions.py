#!/usr/bin/env python3
"""只读分析 def_motion.xml 的单位—资源—动作映射，并对照可用 BILE 动画名。"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bile_workbench.bile_format import BileFormatError, parse_file

DEFINITIONS = {
    "将军的荣耀3": {
        "xml": ROOT / "cross_game_assets" / "motion_definitions" / "general3_def_motion.xml",
        "asset_dir": ROOT / "cross_game_assets" / "general3",
    },
    "世界征服者4": {
        "xml": ROOT / "cross_game_assets" / "motion_definitions" / "wc4_def_motion.xml",
        "asset_dir": ROOT / "cross_game_assets" / "wc4_extended",
    },
}


_TAG_RE = re.compile(r"<(?P<tag>Unit|Motion)\b(?P<body>[^>]*)>")
_ATTRIBUTE_RE = re.compile(r"\s+(?P<name>[A-Za-z_][A-Za-z0-9_.:-]*)\s*=\s*(?P<value>\"[^\"]*\"|'[^']*')")


def _parse_with_duplicate_attribute_compatibility(xml_path: Path) -> tuple[ET.Element, list[dict]]:
    """仅在内存中折叠 Unit/Motion 起始标签内的重复属性；保留首次出现值并记录差异。"""
    source = xml_path.read_text(encoding="utf-8-sig")
    repairs: list[dict] = []

    def replace_tag(match: re.Match[str]) -> str:
        tag = match.group("tag")
        attributes: list[tuple[str, str]] = []
        seen: set[str] = set()
        duplicates: list[str] = []
        for attribute in _ATTRIBUTE_RE.finditer(match.group("body")):
            name = attribute.group("name")
            value = attribute.group("value")
            if name in seen:
                duplicates.append(name)
                continue
            seen.add(name)
            attributes.append((name, value))
        if duplicates:
            repairs.append({"tag": tag, "duplicate_attributes": duplicates, "source_fragment": match.group(0)})
        closing = "/>" if match.group(0).endswith("/>") else ">"
        return "<" + tag + "".join(f" {name}={value}" for name, value in attributes) + closing

    normalized = _TAG_RE.sub(replace_tag, source)
    return ET.fromstring(normalized), repairs


def parse_definition(game: str, xml_path: Path, asset_dir: Path) -> dict:
    root, duplicate_attribute_repairs = _parse_with_duplicate_attribute_compatibility(xml_path)
    units = []
    for ordinal, node in enumerate(root.findall("Unit")):
        motions = [
            {
                "name": motion.get("name", ""),
                "type": motion.get("type", ""),
                "at": motion.get("at"),
                "effect": motion.get("effect"),
            }
            for motion in node.findall("Motion")
        ]
        units.append({
            "ordinal": ordinal,
            "name": node.get("name", ""),
            "res": node.get("res", ""),
            "strike": node.get("strike"),
            "dir": node.get("dir"),
            "x": node.get("x"),
            "y": node.get("y"),
            "scale": node.get("scale"),
            "motions": motions,
        })
    resources: dict[str, dict] = {}
    for resource in sorted({unit["res"] for unit in units if unit["res"]}):
        bin_path = asset_dir / f"{resource}.bin"
        entry: dict = {"bin": bin_path.name, "available": bin_path.exists()}
        if bin_path.exists():
            try:
                document = parse_file(bin_path)
                animations = [element.name for element in document.animations]
                entry.update({
                    "bile_version": document.header.version,
                    "bile_animation_count": len(animations),
                    "bile_sprite_count": len(document.sprites),
                    "bile_animation_names": animations,
                })
            except BileFormatError as exc:
                entry["bile_error"] = str(exc)
        resources[resource] = entry
    for unit in units:
        resource = resources.get(unit["res"], {})
        animations = set(resource.get("bile_animation_names", []))
        for motion in unit["motions"]:
            motion["exact_bile_animation_match"] = motion["name"] in animations if animations else None
    return {"game": game, "xml": str(xml_path), "units": units, "resources": resources, "duplicate_attribute_repairs": duplicate_attribute_repairs}


def write_markdown(reports: list[dict], output: Path) -> None:
    lines = [
        "# def_motion 单位—兵模—动作映射审计",
        "",
        "> 此审计将 XML 中的 `<Unit>` 与 `<Motion>` 映射到资源基名，并在对应 BILE 文件存在时核对动作名是否精确命中动画元素。它揭示的是配置和离线资源关系，不能单独证明引擎在格子上实例化的部队数量。",
        "",
    ]
    for report in reports:
        units = report["units"]
        resources = report["resources"]
        type_counts = Counter(motion["type"] for unit in units for motion in unit["motions"])
        resource_counts = Counter(unit["res"] for unit in units)
        lines.extend([
            f"## {report['game']}",
            "",
            "| 项目 | 值 |",
            "|---|---:|",
            f"| Unit 节点 | {len(units)} |",
            f"| 资源基名数量 | {len(resource_counts)} |",
            f"| Motion 节点 | {sum(len(unit['motions']) for unit in units)} |",
            f"| 内存兼容的重复属性标签 | {len(report['duplicate_attribute_repairs'])} |",
            f"| 动作类型分布 | `{dict(sorted(type_counts.items()))}` |",
            "",
            "| 资源 `res` | Unit 变体数 | 对应 BIN | BILE 状态 | 动画/精灵 | XML Motion 精确命中 BILE 动画数 |",
            "|---|---:|---|---|---:|---:|",
        ])
        for resource, unit_count in sorted(resource_counts.items()):
            source = resources[resource]
            motion_names = {motion["name"] for unit in units if unit["res"] == resource for motion in unit["motions"]}
            animations = set(source.get("bile_animation_names", []))
            matches = len(motion_names & animations) if animations else 0
            state = f"BILE v{source['bile_version']}" if "bile_version" in source else "BIN 未随样本提供"
            count_text = f"{source.get('bile_animation_count', '—')}/{source.get('bile_sprite_count', '—')}"
            lines.append(f"| `{resource}` | {unit_count} | `{source['bin']}` | {state} | {count_text} | {matches}/{len(motion_names)} |")
        lines.extend(["", "### 已提供资源的逐 Unit 映射", "", "| Unit | res | 坐标 / 朝向 / 缩放 | Motion 类型序列 | 精确动作名命中率 |", "|---|---|---|---|---:|"])
        for unit in units:
            source = resources[unit["res"]]
            if not source.get("available"):
                continue
            motions = unit["motions"]
            matches = sum(motion["exact_bile_animation_match"] is True for motion in motions)
            kinds = ", ".join(motion["type"] for motion in motions)
            transform = f"x={unit['x'] or '—'}, y={unit['y'] or '—'}, dir={unit['dir'] or '—'}, scale={unit['scale'] or '—'}"
            lines.append(f"| {unit['name']} | `{unit['res']}` | {transform} | {kinds} | {matches}/{len(motions)} |")
        if report["duplicate_attribute_repairs"]:
            lines.extend(["", "### XML 兼容读取记录", "", "> 原始 XML 未被修改。为使标准 XML 读取器可以审计该文件，以下标签在内存中保留了同名属性的首次出现值；其精确引擎取值规则仍需运行时证据。", "", "| 标签 | 重复属性 |", "|---|---|"])
            for repair in report["duplicate_attribute_repairs"]:
                lines.append(f"| `{repair['tag']}` | `{', '.join(repair['duplicate_attributes'])}` |")
        lines.append("")
    output.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    reports = [parse_definition(game, config["xml"], config["asset_dir"]) for game, config in DEFINITIONS.items()]
    research = ROOT / "research"
    json_path = research / "motion_definition_mapping.json"
    markdown_path = research / "motion_definition_mapping.md"
    json_path.write_text(json.dumps({"schema": "bile-workbench.motion-definition-mapping/v1", "games": reports}, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(reports, markdown_path)
    print(markdown_path)
    print(json_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
