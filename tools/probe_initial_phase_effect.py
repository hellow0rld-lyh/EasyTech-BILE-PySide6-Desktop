#!/usr/bin/env python3
"""定位原包真实的非零 initial_phase 子动画轨道，并比较两种嵌套时钟画面。"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bile_workbench.bile_format import parse_file
from bile_workbench.preview_renderer import child_slot_for_reference_v4, load_atlas, render_frame


def difference(left: Image.Image, right: Image.Image) -> int:
    return sum(a != b for a, b in zip(left.getdata(), right.getdata()))


def main() -> int:
    assets = ROOT / "sample_assets"
    candidate = None
    for bin_path in sorted(assets.glob("anim_*.bin")):
        document = parse_file(bin_path)
        for parent in document.animations:
            for channel_index, channel in enumerate(parent.channels):
                for frame in channel.frames:
                    for track in frame.tracks:
                        if track.element_index < 0:
                            continue
                        child = document.elements[track.element_index]
                        keyframe = document.keyframes[track.keyframe_index]
                        if not child.has_texture and keyframe.initial_phase != 0:
                            candidate = (bin_path, document, parent, channel_index, frame, child, track, keyframe)
                            break
                    if candidate:
                        break
                if candidate:
                    break
            if candidate:
                break
        if candidate:
            break
    if candidate is None:
        raise SystemExit("原包中未找到非零 initial_phase 的子动画轨道")

    bin_path, document, parent, channel_index, frame, child, track, keyframe = candidate
    atlas = load_atlas(assets / f"{bin_path.stem}.xml", assets / f"{bin_path.stem}.webp")
    slot = frame.slot
    child_slot = child_slot_for_reference_v4(slot, frame.slot, keyframe, child.frame_count)
    legacy = render_frame(document, atlas, parent.name, slot, canvas_size=(512, 384), nested_timing="legacy_global")
    reference = render_frame(document, atlas, parent.name, slot, canvas_size=(512, 384), nested_timing="reference_v4")
    delta = difference(legacy, reference)

    header = 42
    contact = Image.new("RGBA", (1024, 426), (24, 27, 32, 255))
    contact.alpha_composite(legacy, (0, header))
    contact.alpha_composite(reference, (512, header))
    draw = ImageDraw.Draw(contact)
    draw.text((10, 6), f"legacy_global: root slot={slot} / child uses {slot}", fill=(235, 238, 244, 255))
    draw.text((522, 6), f"reference_v4: child starts at initial_phase={keyframe.initial_phase}", fill=(235, 238, 244, 255))
    draw.text((10, 23), f"{bin_path.stem} / {parent.name} -> {child.name} / pixel delta={delta}", fill=(174, 184, 200, 255))
    out = ROOT / "research" / "initial_phase_effect_compare.png"
    contact.save(out)

    print("# 非零 initial_phase 的原包画面探针\n")
    print("| 字段 | 值 |")
    print("|---|---|")
    print(f"| 资源 | `{bin_path.stem}` |")
    print(f"| 父动画 / 通道 | `{parent.name}` / {channel_index} |")
    print(f"| BMRF 槽位 | {frame.slot} |")
    print(f"| BXDI / BELE | {track.keyframe_index} / {track.keyframe_index} |")
    print(f"| 子动画 | `{child.name}`，{child.frame_count} 帧 |")
    print(f"| initial_phase | {keyframe.initial_phase} |")
    print(f"| reference_v4 的子槽位 | {child_slot} |")
    print(f"| legacy_global 的子槽位 | {slot} |")
    print(f"| 同一父动画帧像素差异 | {delta} |")
    print(f"\n接触表：`{out.relative_to(ROOT)}`")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
