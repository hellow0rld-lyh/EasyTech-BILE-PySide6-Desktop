from __future__ import annotations

from pathlib import Path

from bile_workbench.spine38_timeline import parse_spine38_pose_animation
from bile_workbench.spine_pose import project_pose

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "incoming/cross_era_20260822/欧7测试/animation/Arthur2.bin"


def main() -> int:
    static, archive = parse_spine38_pose_animation(SAMPLE, "Wait")
    assert archive.tracks, "代表动画应包含可投影的 bone/slot 轨道"
    snapshots = []
    for time in (0.0, archive.duration * 0.5, archive.duration):
        pose = project_pose(static, archive, time)
        assert pose.bones, "pose 应产生骨骼 world matrix"
        snapshots.append({"time": round(time, 3), "layers": len(pose.layers), "diagnostics": len(pose.diagnostics)})
    print(f"PASS {SAMPLE.name}: tracks={len(archive.tracks)} duration={archive.duration:.3f} snapshots={snapshots}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
