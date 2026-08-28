from __future__ import annotations

from pathlib import Path

from bile_workbench.spine38_timeline import parse_spine38_animations, parse_spine38_pose_animation
from bile_workbench.spine41_timeline import parse_spine41_animations, parse_spine41_pose_animation
from bile_workbench.spine_pose import project_pose

ROOT = Path(__file__).resolve().parents[1]
TARGETS = (
    ("eu7", ROOT / "incoming/cross_era_20260822/欧7测试/animation", parse_spine38_animations, parse_spine38_pose_animation),
    ("zheng2", ROOT / "incoming/cross_era_20260822/征2测试/animation", parse_spine41_animations, parse_spine41_pose_animation),
)


def main() -> int:
    for label, directory, read_archive, read_pose in TARGETS:
        hits = []
        checked = 0
        for path in sorted(directory.glob("*.bin")):
            archive = read_archive(path)
            if not archive.animations:
                continue
            name = archive.animations[0].name
            static, pose_archive = read_pose(path, name)
            pose = project_pose(static, pose_archive, min(pose_archive.duration * 0.5, 0.5))
            checked += 1
            if pose.layers:
                hits.append((path.name, name, pose_archive.duration, len(pose.layers), len(pose.diagnostics)))
                if len(hits) >= 5:
                    break
        print(f"{label}: checked={checked} visible_candidates={hits}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
