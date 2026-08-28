from __future__ import annotations

from pathlib import Path

from bile_workbench.spine38_timeline import parse_spine38_pose_animation
from bile_workbench.spine41_timeline import parse_spine41_pose_animation

ROOT = Path(__file__).resolve().parents[1]
SOURCES = (
    ("eu7", ROOT / "incoming/cross_era_20260822/欧7测试/animation/Empress Matilda2.bin", "Wait", parse_spine38_pose_animation),
    ("zheng2", ROOT / "incoming/cross_era_20260822/征2测试/animation/[mini]form_main1.bin", "Wait", parse_spine41_pose_animation),
)

for label, path, animation_name, loader in SOURCES:
    static, animation = loader(path, animation_name)
    meshes = {(item.skin, item.slot_index, item.name): item for item in static.mesh_attachments if item.vertices is not None}
    matches = [item for item in animation.deform_evidence if (item.skin, item.slot_index, item.attachment_name) in meshes]
    print(label, "unweighted_meshes", len(meshes), "deform_timelines", len(animation.deform_evidence), "exact_matches", len(matches))
    for item in matches:
        mesh = meshes[(item.skin, item.slot_index, item.attachment_name)]
        print("  ", item.skin, item.slot_index, item.attachment_name, "vertex_scalars", len(mesh.vertices), "frames", len(item.frames))
