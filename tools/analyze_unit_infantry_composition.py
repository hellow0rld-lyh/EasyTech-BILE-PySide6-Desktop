#!/usr/bin/env python3
"""只读量化将军的荣耀3与世界征服者4 unit_infantry 的 BILE 动画组合深度。"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bile_workbench.bile_format import BileDocument, parse_file
from analyze_motion_definitions import _parse_with_duplicate_attribute_compatibility

SOURCES = {
    "将军的荣耀3": {
        "bin": ROOT / "cross_game_assets" / "general3" / "unit_infantry.bin",
        "definition": ROOT / "cross_game_assets" / "motion_definitions" / "general3_def_motion.xml",
    },
    "世界征服者4": {
        "bin": ROOT / "cross_game_assets" / "wc4_extended" / "unit_infantry.bin",
        "definition": ROOT / "cross_game_assets" / "motion_definitions" / "wc4_def_motion.xml",
    },
}


def active_tracks(element, slot: int):
    tracks = []
    for channel in element.channels:
        active = None
        for frame in channel.frames:
            if frame.slot <= slot:
                active = frame
            else:
                break
        if active is not None:
            tracks.extend(active.tracks)
    return tracks


def referenced_motion_names(definition: Path) -> tuple[dict[str, Counter[str]], list[dict]]:
    root, repairs = _parse_with_duplicate_attribute_compatibility(definition)
    by_type: dict[str, Counter[str]] = {}
    for unit in root.findall("Unit"):
        if unit.get("res") != "unit_infantry":
            continue
        for motion in unit.findall("Motion"):
            by_type.setdefault(motion.get("type", ""), Counter())[motion.get("name", "")] += 1
    return by_type, repairs


def descendant_leaf_sprites(document: BileDocument, root_index: int) -> set[int]:
    leaves: set[int] = set()
    visited: set[int] = set()

    def visit(index: int) -> None:
        if index in visited:
            return
        visited.add(index)
        element = document.elements[index]
        for channel in element.channels:
            for frame in channel.frames:
                for track in frame.tracks:
                    if track.element_index < 0:
                        continue
                    target = document.elements[track.element_index]
                    if target.has_texture:
                        leaves.add(target.index)
                    else:
                        visit(target.index)

    visit(root_index)
    return leaves


def animation_metrics(document: BileDocument, name: str) -> dict:
    root = next(element for element in document.animations if element.name == name)
    direct_targets = {track.element_index for channel in root.channels for frame in channel.frames for track in frame.tracks if track.element_index >= 0}
    direct_animations = sorted(index for index in direct_targets if not document.elements[index].has_texture)
    direct_sprites = sorted(index for index in direct_targets if document.elements[index].has_texture)
    max_tracks = 0
    max_sprite_tracks = 0
    max_animation_tracks = 0
    for slot in range(root.frame_count):
        tracks = active_tracks(root, slot)
        max_tracks = max(max_tracks, len(tracks))
        max_sprite_tracks = max(max_sprite_tracks, sum(track.element_index >= 0 and document.elements[track.element_index].has_texture for track in tracks))
        max_animation_tracks = max(max_animation_tracks, sum(track.element_index >= 0 and not document.elements[track.element_index].has_texture for track in tracks))
    return {
        "root": name,
        "frame_count": root.frame_count,
        "channel_count": root.channel_count,
        "direct_target_count": len(direct_targets),
        "direct_animation_target_count": len(direct_animations),
        "direct_sprite_target_count": len(direct_sprites),
        "max_concurrent_direct_tracks": max_tracks,
        "max_concurrent_direct_animation_tracks": max_animation_tracks,
        "max_concurrent_direct_sprite_tracks": max_sprite_tracks,
        "descendant_leaf_sprite_count": len(descendant_leaf_sprites(document, root.index)),
        "contains_combination_word": "组合" in name,
    }


def audit(game: str, config: dict[str, Path]) -> dict:
    document = parse_file(config["bin"])
    by_type, repairs = referenced_motion_names(config["definition"])
    available = {element.name for element in document.animations}
    metrics = []
    for motion_type, names in sorted(by_type.items()):
        for name, unit_bindings in sorted(names.items()):
            item = {"motion_type": motion_type, "unit_bindings": unit_bindings, "bile_animation_exists": name in available}
            if name in available:
                item.update(animation_metrics(document, name))
            metrics.append(item)
    return {
        "game": game,
        "bin": str(config["bin"]),
        "version": document.header.version,
        "metrics": metrics,
        "definition_repairs": repairs,
    }


def write_markdown(reports: list[dict], target: Path) -> None:
    lines = [
        "# unit_infantry 跨游戏 BILE 组合深度审计",
        "",
        "> `并发直接轨道` 和 `递归精灵叶子` 是离线 BILE 图结构指标：它们描述一个根动作引用的渲染组件数量，**不是**游戏格子上的部队实例数。后者仍需运行时实验或原生读取逻辑证据。",
        "",
    ]
    for report in reports:
        metrics = report["metrics"]
        present = [item for item in metrics if item["bile_animation_exists"]]
        summary = {
            "motion_roots": len(metrics),
            "matched_roots": len(present),
            "combination_named_roots": sum(item.get("contains_combination_word", False) for item in present),
            "max_direct_tracks": max((item["max_concurrent_direct_tracks"] for item in present), default=0),
            "max_direct_animation_tracks": max((item["max_concurrent_direct_animation_tracks"] for item in present), default=0),
            "max_leaf_sprites": max((item["descendant_leaf_sprite_count"] for item in present), default=0),
        }
        lines.extend([
            f"## {report['game']} · BILE v{report['version']}",
            "",
            "| 指标 | 值 |",
            "|---|---:|",
            f"| def_motion 绑定的 unit_infantry 根动作 | {summary['motion_roots']} |",
            f"| 同名 BILE 根动画存在 | {summary['matched_roots']} |",
            f"| 名称含“组合”的根动作 | {summary['combination_named_roots']} |",
            f"| 最大同槽直接轨道数 | {summary['max_direct_tracks']} |",
            f"| 最大同槽直接子动画轨道数 | {summary['max_direct_animation_tracks']} |",
            f"| 最大递归精灵叶子数 | {summary['max_leaf_sprites']} |",
            "",
            "| Motion 类型 | 根动画 | 绑定 Unit 数 | 槽位/通道 | 同槽直接轨道（总/子动画/精灵） | 递归精灵叶子 |",
            "|---|---|---:|---:|---:|---:|",
        ])
        for item in present:
            lines.append(
                f"| `{item['motion_type']}` | {item['root']} | {item['unit_bindings']} | {item['frame_count']}/{item['channel_count']} | "
                f"{item['max_concurrent_direct_tracks']}/{item['max_concurrent_direct_animation_tracks']}/{item['max_concurrent_direct_sprite_tracks']} | "
                f"{item['descendant_leaf_sprite_count']} |"
            )
        missing = [item for item in metrics if not item["bile_animation_exists"]]
        if missing:
            lines.extend(["", f"> 有 {len(missing)} 个 XML 动作名未在提供的 BILE 动画中发现；未将它们纳入组合统计。"])
        lines.append("")
    target.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    reports = [audit(game, config) for game, config in SOURCES.items()]
    research = ROOT / "research"
    json_path = research / "unit_infantry_composition_audit.json"
    markdown_path = research / "unit_infantry_composition_audit.md"
    json_path.write_text(json.dumps({"schema": "bile-workbench.unit-infantry-composition/v1", "games": reports}, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(reports, markdown_path)
    print(markdown_path)
    print(json_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
