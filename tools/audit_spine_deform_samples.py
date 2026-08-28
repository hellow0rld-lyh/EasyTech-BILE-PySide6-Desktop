from __future__ import annotations

from pathlib import Path

from bile_workbench.spine38_timeline import parse_spine38_animations, parse_spine38_pose_animation
from bile_workbench.spine41_timeline import parse_spine41_animations, parse_spine41_pose_animation

ROOT = Path(__file__).resolve().parents[1]
SOURCES = (
    ("eu7", ROOT / "incoming/cross_era_20260822/欧7测试/animation", parse_spine38_animations, parse_spine38_pose_animation),
    ("zheng2", ROOT / "incoming/cross_era_20260822/征2测试/animation", parse_spine41_animations, parse_spine41_pose_animation),
)

for label, directory, archive_loader, pose_loader in SOURCES:
    matches = []
    for path in sorted(directory.glob("*.bin")):
        try:
            archive = archive_loader(path)
            for item in archive.animations:
                _static, pose = pose_loader(path, item.name)
                if pose.deform_evidence:
                    matches.append((path.name, item.name, len(pose.deform_evidence), sum(len(t.frames) for t in pose.deform_evidence), sum(len(frame.values) for t in pose.deform_evidence for frame in t.frames)))
        except (OSError, ValueError):
            continue
    print(label, *matches[:10], sep="\n")
    print(f"{label}: {len(matches)} deform-bearing animations")
