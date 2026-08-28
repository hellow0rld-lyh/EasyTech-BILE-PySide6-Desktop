#!/usr/bin/env python3
"""生成将军的荣耀3与世界征服者4 unit_infantry 根动作的离线代表帧对照。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from analyze_motion_definitions import _parse_with_duplicate_attribute_compatibility
from bile_workbench.bile_format import parse_file
from bile_workbench.preview_renderer import load_atlas, render_frame

SOURCES = {
    "General 3 / BILE v4 / direct sprites": {
        "bin": ROOT / "cross_game_assets" / "general3" / "unit_infantry.bin",
        "xml": ROOT / "cross_game_assets" / "general3" / "unit_infantry.xml",
        "image": ROOT / "cross_game_assets" / "general3" / "unit_infantry.webp",
        "definition": ROOT / "cross_game_assets" / "motion_definitions" / "general3_def_motion.xml",
    },
    "World Conqueror 4 / BILE v4 / child animations": {
        "bin": ROOT / "cross_game_assets" / "wc4_extended" / "unit_infantry.bin",
        "xml": ROOT / "cross_game_assets" / "wc4_extended" / "unit_infantry.xml",
        "image": ROOT / "cross_game_assets" / "wc4_extended" / "unit_infantry.webp",
        "definition": ROOT / "cross_game_assets" / "motion_definitions" / "wc4_def_motion.xml",
    },
}


def soldier_standby_name(definition: Path) -> str:
    root, _ = _parse_with_duplicate_attribute_compatibility(definition)
    unit = next(item for item in root.findall("Unit") if item.get("name") == "Soldier" and item.get("res") == "unit_infantry")
    motion = next(item for item in unit.findall("Motion") if item.get("type") == "standby")
    return motion.get("name", "")


def nonblack_score(frame: Image.Image) -> int:
    return sum(1 for red, green, blue, alpha in frame.getdata() if alpha and max(red, green, blue) > 48)


def representative_frame(document, atlas, animation_name: str) -> tuple[int, Image.Image, int]:
    element = next(item for item in document.animations if item.name == animation_name)
    best: tuple[int, Image.Image, int] | None = None
    for slot in range(element.frame_count):
        frame = render_frame(document, atlas, animation_name, slot, canvas_size=(512, 384))
        score = nonblack_score(frame)
        if best is None or score > best[2]:
            best = (slot, frame, score)
    if best is None or best[2] <= 0:
        raise ValueError(f"未找到高对比帧：{animation_name}")
    return best


def main() -> int:
    panels = []
    records = []
    for label, source in SOURCES.items():
        document = parse_file(source["bin"])
        atlas = load_atlas(source["xml"], source["image"])
        motion_name = soldier_standby_name(source["definition"])
        slot, frame, score = representative_frame(document, atlas, motion_name)
        panels.append((label, frame, f"slot {slot} | bright pixels {score}"))
        records.append({
            "label": label,
            "bin": str(source["bin"].relative_to(ROOT)),
            "motion": motion_name,
            "slot": slot,
            "nonblack_pixels": score,
            "bile_version": document.header.version,
            "render_scope": "single def_motion root animation only; no def_array formation instances applied",
        })

    margin, caption_height = 16, 54
    width = margin + sum(frame.width + margin for _, frame, _ in panels)
    height = caption_height + panels[0][1].height + margin * 2
    sheet = Image.new("RGBA", (width, height), (22, 25, 30, 255))
    drawing = ImageDraw.Draw(sheet)
    x = margin
    for label, frame, caption in panels:
        drawing.text((x, 8), label, fill=(232, 236, 242, 255))
        drawing.text((x, 28), caption, fill=(171, 184, 198, 255))
        background = Image.new("RGBA", frame.size, (32, 36, 43, 255))
        background.alpha_composite(frame)
        sheet.alpha_composite(background, (x, caption_height))
        x += frame.width + margin

    research = ROOT / "research"
    image_path = research / "unit_infantry_root_animation_comparison.png"
    json_path = research / "unit_infantry_root_animation_comparison.json"
    sheet.convert("RGB").save(image_path)
    json_path.write_text(json.dumps({"schema": "bile-workbench.root-animation-comparison/v1", "samples": records}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(image_path)
    print(json_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
