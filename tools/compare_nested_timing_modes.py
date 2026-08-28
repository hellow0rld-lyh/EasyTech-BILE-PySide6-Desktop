#!/usr/bin/env python3
"""比较 legacy_global 与 reference_v4 的嵌套动画渲染，输出差异报告与代表接触表。"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bile_workbench.bile_format import parse_file
from bile_workbench.preview_renderer import load_atlas, render_frame


def pixel_delta(left: Image.Image, right: Image.Image) -> int:
    return sum(a != b for a, b in zip(left.getdata(), right.getdata()))


def main() -> int:
    assets = ROOT / "sample_assets"
    rows: list[tuple[str, str, int, int]] = []
    contact: Image.Image | None = None
    for bin_path in sorted(assets.glob("anim_*.bin")):
        stem = bin_path.stem
        document = parse_file(bin_path)
        atlas = load_atlas(assets / f"{stem}.xml", assets / f"{stem}.webp")
        target = document.animations[0]
        slot = max(0, target.frame_count // 2)
        legacy = render_frame(document, atlas, target.name, slot, canvas_size=(512, 384), nested_timing="legacy_global")
        reference = render_frame(document, atlas, target.name, slot, canvas_size=(512, 384), nested_timing="reference_v4")
        delta = pixel_delta(legacy, reference)
        rows.append((stem, target.name, slot, delta))
        if delta and contact is None:
            header = 28
            contact = Image.new("RGBA", (1024, 412), (24, 27, 32, 255))
            contact.alpha_composite(legacy, (0, header))
            contact.alpha_composite(reference, (512, header))
            draw = ImageDraw.Draw(contact)
            draw.text((10, 8), f"legacy_global · {stem} / {target.name} / slot {slot}", fill=(235, 238, 244, 255))
            draw.text((522, 8), "reference_v4", fill=(235, 238, 244, 255))
    print("# 嵌套动画时钟模式比较\n")
    print("| 资源 | 代表动画 | 槽位 | 像素差异 |")
    print("|---|---|---:|---:|")
    for stem, name, slot, delta in rows:
        print(f"| `{stem}` | `{name}` | {slot} | {delta} |")
    if contact is not None:
        out = ROOT / "research" / "nested_timing_mode_compare.png"
        contact.save(out)
        print(f"\n首个可见差异接触表：`{out.relative_to(ROOT)}`")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
