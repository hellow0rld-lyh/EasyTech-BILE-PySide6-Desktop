#!/usr/bin/env python3
"""审计 BELE initial_phase/playback_mode 与轨道目标类型的关联；仅使用原包数据。"""
from __future__ import annotations

import collections
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bile_workbench.bile_format import parse_file


def main() -> int:
    assets = ROOT / "sample_assets"
    print("# BELE 播放字段与轨道目标类型审计\n")
    print("| 资源 | 目标类型 | 轨道数 | initial_phase 非零 | playback_mode 分布 |")
    print("|---|---|---:|---:|---|")
    totals: dict[str, list[int]] = {"子动画": [0, 0], "静态精灵": [0, 0]}
    modes: dict[str, collections.Counter[int]] = {"子动画": collections.Counter(), "静态精灵": collections.Counter()}
    for bin_path in sorted(assets.glob("anim_*.bin")):
        doc = parse_file(bin_path)
        per = {"子动画": [0, 0], "静态精灵": [0, 0]}
        counts = {"子动画": collections.Counter(), "静态精灵": collections.Counter()}
        for parent in doc.animations:
            for channel in parent.channels:
                for frame in channel.frames:
                    for track in frame.tracks:
                        if track.element_index < 0:
                            continue
                        keyframe = doc.keyframes[track.keyframe_index]
                        target = "静态精灵" if doc.elements[track.element_index].has_texture else "子动画"
                        per[target][0] += 1
                        per[target][1] += int(keyframe.initial_phase != 0)
                        counts[target][keyframe.playback_mode] += 1
                        totals[target][0] += 1
                        totals[target][1] += int(keyframe.initial_phase != 0)
                        modes[target][keyframe.playback_mode] += 1
        for target in ("子动画", "静态精灵"):
            if per[target][0]:
                text = ", ".join(f"{mode}:{count}" for mode, count in sorted(counts[target].items()))
                print(f"| `{bin_path.stem}` | {target} | {per[target][0]} | {per[target][1]} | `{text}` |")
    print("\n## 总计\n")
    print("| 目标类型 | 轨道数 | initial_phase 非零 | playback_mode 分布 |")
    print("|---|---:|---:|---|")
    for target in ("子动画", "静态精灵"):
        text = ", ".join(f"{mode}:{count}" for mode, count in sorted(modes[target].items()))
        print(f"| {target} | {totals[target][0]} | {totals[target][1]} | `{text}` |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
