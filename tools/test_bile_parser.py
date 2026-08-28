#!/usr/bin/env python3
"""对原包全部 BILE 动画执行严格解析回归，并输出时间线统计。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bile_workbench.bile_format import BileFormatError, parse_file  # noqa: E402


def main() -> int:
    assets = ROOT / "sample_assets"
    rows = []
    failures = []
    for path in sorted(assets.glob("anim_*.bin")):
        try:
            document = parse_file(path)
            channels = sum(len(element.channels) for element in document.elements)
            frames = sum(len(channel.frames) for element in document.elements for channel in element.channels)
            tracks = sum(len(frame.tracks) for element in document.elements for channel in element.channels for frame in channel.frames)
            max_slot = max((frame.slot for element in document.elements for channel in element.channels for frame in channel.frames), default=0)
            rows.append((path.stem, len(document.keyframes), len(document.sprites), len(document.animations), channels, frames, tracks, max_slot))
        except (BileFormatError, OSError) as exc:
            failures.append((path.name, str(exc)))
    print("| 动画 | BELE | 精灵项 | 动画项 | 通道 | 帧 | 轨道 | 最大槽位 |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|")
    for row in rows:
        print("| " + " | ".join(f"`{value}`" if isinstance(value, str) else str(value) for value in row) + " |")
    if failures:
        print("\n失败：")
        for name, message in failures:
            print(f"- {name}: {message}")
        return 1
    print(f"\n全部通过：{len(rows)} 个样本。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
