"""验证欧7/征2 Spine ATLAS 的加载和区域预览；仅输出 PNG 证据。"""
from __future__ import annotations

from pathlib import Path

from bile_workbench.spine_atlas import load_spine_atlas, render_region

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = [
    (ROOT / "incoming/cross_era_20260822/欧7测试/animation/Arthur2.atlas", "剑", ROOT / "research/eu7_atlas_region_sword.png"),
    (ROOT / "incoming/cross_era_20260822/征2测试/animation/EmpireCityFire01.atlas", "images/火焰序列/火焰序列-4_00000", ROOT / "research/zheng2_atlas_region_fire.png"),
]


def main() -> int:
    for path, region, output in SAMPLES:
        atlas = load_spine_atlas(path)
        image = render_region(atlas, region)
        output.parent.mkdir(parents=True, exist_ok=True)
        image.save(output)
        print(f"{path.name}: {atlas.dialect}, 区域 {region!r}, {len(atlas.regions)} 个区域, 预览 {image.size}, 输出 {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
