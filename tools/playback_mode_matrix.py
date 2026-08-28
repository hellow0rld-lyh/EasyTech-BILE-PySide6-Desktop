#!/usr/bin/env python3
"""从原包实际嵌套轨道提取 playback_mode 实验矩阵，不构造虚拟 BILE 数据。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bile_workbench.bile_format import parse_file
from bile_workbench.preview_renderer import child_slot_for_reference_v4


def main() -> int:
    assets = ROOT / "sample_assets"
    candidates: dict[int, tuple[str, object, int, object, object]] = {}
    for bin_path in sorted(assets.glob("anim_*.bin")):
        document = parse_file(bin_path)
        for parent in document.animations:
            for channel in parent.channels:
                for frame in channel.frames:
                    for track in frame.tracks:
                        if track.element_index < 0:
                            continue
                        child = document.elements[track.element_index]
                        if child.has_texture:
                            continue
                        keyframe = document.keyframes[track.keyframe_index]
                        if keyframe.playback_mode in (0, 1, 2) and keyframe.playback_mode not in candidates:
                            candidates[keyframe.playback_mode] = (bin_path.stem, parent, frame.slot, child, keyframe)
    mode_names = {0: "Loop（循环）", 1: "OneShotStop（单次停止）", 2: "ManualFrameHold（手动保持）"}
    print("# BILE v4 嵌套播放模式实验矩阵\n")
    print("> 每行均取自原包中真实的“父动画 → BXDI → 子动画”轨道。`child_slot` 使用工作台 `reference_v4` 规则；这验证规则如何作用于真实字段，但不替代游戏内画面判定。\n"
    )
    print("| 模式 | 原包来源 | 父动画 | 子动画 | BELE initial_phase | 子帧数 | 父槽位序列 | 推导子槽位序列 |")
    print("|---|---|---|---|---:|---:|---|---|")
    for mode in (0, 1, 2):
        if mode not in candidates:
            print(f"| {mode_names[mode]} | — | — | — | — | — | — | — |")
            continue
        stem, parent, marker, child, keyframe = candidates[mode]
        slots = [marker, marker + 1, marker + 2, marker + child.frame_count, marker + child.frame_count + 2]
        child_slots = [child_slot_for_reference_v4(slot, marker, keyframe, child.frame_count) for slot in slots]
        print(
            f"| {mode_names[mode]} | `{stem}` | `{parent.name}` | `{child.name}` | {keyframe.initial_phase} | {child.frame_count} | "
            f"`{', '.join(map(str, slots))}` | `{', '.join(map(str, child_slots))}` |"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
