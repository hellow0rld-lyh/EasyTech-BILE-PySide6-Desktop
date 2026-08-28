#!/usr/bin/env python3
"""使用独立解析/合成器渲染原包动画接触表。"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bile_workbench.bile_format import parse_file  # noqa: E402
from bile_workbench.preview_renderer import load_atlas, render_frame  # noqa: E402


def main() -> int:
    assets = ROOT / "sample_assets"
    out = ROOT / "research" / "rendered_failure_contact_sheet.png"
    stem = "anim_failure"
    document = parse_file(assets / f"{stem}.bin")
    atlas = load_atlas(assets / f"{stem}.xml", assets / f"{stem}.webp")
    animation = next(item for item in document.animations if item.name == "failure_a")
    slots = [0, 5, 10, 15, max(0, animation.frame_count - 1)]
    frames = [render_frame(document, atlas, animation.name, slot, canvas_size=(512, 384)) for slot in slots]
    sheet = Image.new("RGBA", (512 * len(frames), 420), (22, 24, 28, 255))
    draw = ImageDraw.Draw(sheet)
    for index, (slot, frame) in enumerate(zip(slots, frames)):
        sheet.alpha_composite(frame, (index * 512, 36))
        draw.text((index * 512 + 12, 12), f"{animation.name} / slot {slot}", fill=(230, 232, 238, 255))
    sheet.save(out)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
