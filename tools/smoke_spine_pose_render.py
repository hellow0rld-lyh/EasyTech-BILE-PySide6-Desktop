from __future__ import annotations

from pathlib import Path

from bile_workbench.spine_atlas import load_spine_atlas
from bile_workbench.spine38_timeline import parse_spine38_pose_animation
from bile_workbench.spine41_timeline import parse_spine41_pose_animation
from bile_workbench.spine_pose import project_pose
from bile_workbench.spine_pose_renderer import render_pose_layers

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = (
    ("eu7", ROOT / "incoming/cross_era_20260822/欧7测试/animation/Arthur2.bin", "Wait", parse_spine38_pose_animation, ROOT / "research/eu7_spine_pose_wait.png"),
    ("zheng2", ROOT / "incoming/cross_era_20260822/征2测试/animation/[mini]effect_ui10.bin", "Wait", parse_spine41_pose_animation, ROOT / "research/zheng2_spine_pose_ui10.png"),
)


def main() -> int:
    for label, path, animation_name, parser, output in SAMPLES:
        static, animation = parser(path, animation_name)
        pose = project_pose(static, animation, animation.duration * 0.5)
        atlas = load_spine_atlas(path.with_suffix(".atlas"))
        rendered = render_pose_layers(pose, atlas)
        assert rendered.rendered_layer_count > 0, f"{label} 无可渲染 layer: {rendered.diagnostics}"
        assert len(set(rendered.image.getdata())) > 1, f"{label} pose 图像为空"
        output.parent.mkdir(parents=True, exist_ok=True)
        rendered.image.save(output)
        print(f"PASS {label}: layers={rendered.rendered_layer_count} diagnostics={len(rendered.diagnostics)} -> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
