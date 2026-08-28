"""Spine deform evidence 的只读审计摘要；不包含顶点应用、渲染或 BIN 写回。"""
from __future__ import annotations

from collections import Counter

from .spine_deform_evidence import DeformTimelineEvidence
from .spine_pose import PoseAnimation
from .spine_unweighted_deform_validation import validate_unweighted_deform_identity_and_span


def deform_audit_text(static: object, animation: PoseAnimation) -> str:
    evidence = tuple(item for item in animation.deform_evidence if isinstance(item, DeformTimelineEvidence))
    if not evidence:
        return "Deform 审计：当前动画没有已捕获 deform evidence。"
    frames = tuple(frame for item in evidence for frame in item.frames)
    curves = Counter("none" if frame.curve is None else frame.curve if isinstance(frame.curve, str) else "bezier" for frame in frames)
    meshes = {(item.skin, item.slot_index, item.name): item for item in getattr(static, "mesh_attachments", ()) if item.vertices is not None}
    results = []
    for item in evidence:
        mesh = meshes.get((item.skin, item.slot_index, item.attachment_name))
        if mesh is not None:
            results.append(validate_unweighted_deform_identity_and_span(mesh, item))
    accepted = sum(item.accepted for item in results)
    rejected = len(results) - accepted
    return (
        "Deform 只读审计："
        f"{len(evidence)} 条 timeline · {len(frames)} 帧 · {sum(len(frame.values) for frame in frames)} values\n"
        f"曲线 evidence：linear {curves['linear']} · stepped {curves['stepped']} · bezier {curves['bezier']} · 末帧/无后继 {curves['none']}\n"
        f"无权重精确 identity/span 预检：{len(results)} 个候选 · {accepted} 通过 · {rejected} 拒绝。"
        " 该结果仅供审阅；deform values 未应用到顶点，Spine BIN 保持只读。"
    )
