#!/usr/bin/env python3
"""生成新增三款游戏的代表动画接触表。"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bile_workbench.bile_format import parse_file
from bile_workbench.preview_renderer import load_atlas, render_frame

SAMPLES = [
    ("General 3 / BILE v4", ROOT / "cross_game_assets" / "general3" / "anim_fire.bin"),
    ("European War 6 / BILE v4", ROOT / "cross_game_assets" / "eu6" / "anim_newui.bin"),
    ("World Conqueror 3 / BILE v3", ROOT / "cross_game_assets" / "wc3" / "anim_gameover.bin"),
]


def image_for(path: Path) -> Path:
    for extension in (".webp", ".png"):
        image = path.with_suffix(extension)
        if image.exists():
            return image
    raise FileNotFoundError(f"缺少图集：{path.stem}")


def main() -> int:
    cell = (320, 240)
    header = 28
    canvas = Image.new("RGBA", (cell[0] * 3, (cell[1] + header) * len(SAMPLES)), (24, 27, 32, 255))
    draw = ImageDraw.Draw(canvas)
    metadata = []
    for row, (label, bin_path) in enumerate(SAMPLES):
        document = parse_file(bin_path)
        atlas = load_atlas(bin_path.with_suffix(".xml"), image_for(bin_path))
        target = document.animations[0]
        slots = sorted({0, target.frame_count // 2, target.frame_count - 1})
        metadata.append({"label": label, "bin": bin_path.name, "version": document.header.version, "animation": target.name, "slots": slots})
        y = row * (cell[1] + header)
        for column, slot in enumerate(slots):
            frame = render_frame(document, atlas, target.name, slot, canvas_size=cell)
            canvas.alpha_composite(frame, (column * cell[0], y + header))
            draw.text((column * cell[0] + 8, y + 8), f"{label} · {target.name} · slot {slot}", fill=(235, 238, 244, 255))
    out = ROOT / "research" / "cross_game_render_contact_sheet.png"
    canvas.save(out)
    (ROOT / "research" / "cross_game_render_samples.json").write_text(__import__("json").dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
