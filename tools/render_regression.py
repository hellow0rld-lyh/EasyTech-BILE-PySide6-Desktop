#!/usr/bin/env python3
"""为每个原包 BILE 文件渲染代表性动画的多个槽位，并校验输出可见性。"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bile_workbench.bile_format import parse_file  # noqa: E402
from bile_workbench.preview_renderer import load_atlas, render_frame  # noqa: E402


def visible_pixels(image: Image.Image, background: tuple[int, int, int, int]) -> int:
    return sum(pixel != background for pixel in image.getdata())


def main() -> int:
    assets = ROOT / "sample_assets"
    output_dir = ROOT / "research" / "render_regression"
    output_dir.mkdir(parents=True, exist_ok=True)
    background = (35, 38, 44, 255)
    rows = []
    failures = []
    for bin_path in sorted(assets.glob("anim_*.bin")):
        stem = bin_path.stem
        try:
            document = parse_file(bin_path)
            atlas = load_atlas(assets / f"{stem}.xml", assets / f"{stem}.webp")
            target = document.animations[0]
            slots = sorted({0, max(0, target.frame_count // 2), max(0, target.frame_count - 1)})
            rendered = [render_frame(document, atlas, target.name, slot, canvas_size=(384, 288), background=background) for slot in slots]
            count = sum(visible_pixels(image, background) for image in rendered)
            if count == 0:
                raise RuntimeError("所有代表帧均为空")
            sheet = Image.new("RGBA", (384 * len(rendered), 288), background)
            for index, image in enumerate(rendered):
                sheet.alpha_composite(image, (384 * index, 0))
            sheet.save(output_dir / f"{stem}.png")
            rows.append((stem, target.name, ", ".join(map(str, slots)), count))
        except Exception as exc:  # 回归脚本需要报告单样本异常而不是中断批处理。
            failures.append((stem, f"{type(exc).__name__}: {exc}"))
    print("| 资源 | 代表动画 | 渲染槽位 | 非背景像素总数 |")
    print("|---|---|---|---:|")
    for stem, name, slots, count in rows:
        print(f"| `{stem}` | `{name}` | `{slots}` | `{count}` |")
    if failures:
        print("\n失败：")
        for stem, message in failures:
            print(f"- {stem}: {message}")
        return 1
    print(f"\n全部通过：{len(rows)} 个样本均生成非空预览。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
