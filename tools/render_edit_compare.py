#!/usr/bin/env python3
"""生成一次保守 BILE 编辑的原始/暂存帧对比图，不覆盖原始 BIN。"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bile_workbench.bile_format import parse_file
from bile_workbench.edit_session import EditSession
from bile_workbench.preview_renderer import load_atlas, render_frame


def main() -> int:
    assets = ROOT / "sample_assets"
    source = assets / "anim_failure.bin"
    original = parse_file(source)
    atlas = load_atlas(assets / "anim_failure.xml", assets / "anim_failure.webp")
    session = EditSession(source)
    try:
        # BELE[1] 是 failure_a 在槽位 16 的一条可见活动轨道。
        keyframe = original.keyframes[1]
        session.set_keyframe(
            1,
            {"xx": keyframe.xx, "xy": keyframe.xy, "yx": keyframe.yx, "yy": keyframe.yy, "x": keyframe.x + 12.5, "y": keyframe.y},
            keyframe.argb,
            keyframe.initial_phase,
        )
        staged = session.preview_document()
        before = render_frame(original, atlas, "failure_a", 16)
        after = render_frame(staged, atlas, "failure_a", 16)
        diff_pixels = sum(a != b for a, b in zip(before.getdata(), after.getdata()))
        if diff_pixels == 0:
            raise RuntimeError("暂存编辑未产生可见像素差异")
        header = 30
        output = Image.new("RGBA", (before.width * 2, before.height + header), (24, 27, 32, 255))
        output.alpha_composite(before, (0, header))
        output.alpha_composite(after, (before.width, header))
        draw = ImageDraw.Draw(output)
        draw.text((12, 9), "Original / slot 16", fill=(235, 238, 244, 255))
        draw.text((before.width + 12, 9), "Staged / BELE[1].x + 12.5", fill=(235, 238, 244, 255))
        out_path = ROOT / "research" / "edit_before_after_compare.png"
        output.save(out_path)
        print(f"差异像素：{diff_pixels}")
        print(out_path)
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
