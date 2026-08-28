#!/usr/bin/env python3
"""统计 BILE v4 样本中 BELE +0x1C/+0x20 的取值和嵌套引用使用情况。"""
from __future__ import annotations

import collections
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bile_workbench.bile_format import parse_file


def main() -> int:
    assets = ROOT / "sample_assets"
    print("| 资源 | BELE 数 | +0x1C 非零 | +0x20 分布 | 嵌套动画轨道 | 初始相位超子帧数 |")
    print("|---|---:|---:|---|---:|---:|")
    for path in sorted(assets.glob("anim_*.bin")):
        doc = parse_file(path)
        modes = collections.Counter(keyframe.playback_mode for keyframe in doc.keyframes)
        nonzero_phase = sum(keyframe.initial_phase != 0 for keyframe in doc.keyframes)
        nested = 0
        out_of_range = 0
        for parent in doc.animations:
            for channel in parent.channels:
                for frame in channel.frames:
                    for track in frame.tracks:
                        if track.element_index >= 0 and not doc.elements[track.element_index].has_texture:
                            nested += 1
                            phase = doc.keyframes[track.keyframe_index].initial_phase
                            child_frames = doc.elements[track.element_index].frame_count
                            if phase >= child_frames:
                                out_of_range += 1
        mode_text = ", ".join(f"{key}:{value}" for key, value in sorted(modes.items()))
        print(f"| `{path.stem}` | {len(doc.keyframes)} | {nonzero_phase} | `{mode_text}` | {nested} | {out_of_range} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
