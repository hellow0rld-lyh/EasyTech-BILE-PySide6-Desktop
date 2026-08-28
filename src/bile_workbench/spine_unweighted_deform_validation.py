"""Spine 无权重 deform 的纯只读预检；刻意不含顶点应用、投影或 BIN 写回。"""
from __future__ import annotations

from dataclasses import dataclass

from .spine38_format import SpineMeshAttachment
from .spine_deform_evidence import DeformTimelineEvidence


@dataclass(frozen=True)
class UnweightedDeformValidation:
    accepted: bool
    reason: str | None
    vertex_scalar_count: int
    frame_count: int


def validate_unweighted_deform_identity_and_span(
    mesh: SpineMeshAttachment,
    evidence: DeformTimelineEvidence,
) -> UnweightedDeformValidation:
    """验证 future-only 的 attachment-local deform 前置条件，不解释或应用 values。"""
    if mesh.vertices is None or mesh.weighted_vertices is not None:
        return UnweightedDeformValidation(False, "目标 attachment 不是纯无权重 mesh。", 0, len(evidence.frames))
    scalar_count = len(mesh.vertices)
    if scalar_count == 0 or scalar_count % 2:
        return UnweightedDeformValidation(False, "无权重 mesh vertices 不是非空二维标量序列。", scalar_count, len(evidence.frames))
    if evidence.attachment_name is None:
        return UnweightedDeformValidation(False, "deform evidence 缺少 attachment 名称。", scalar_count, len(evidence.frames))
    if (mesh.skin, mesh.slot_index, mesh.name) != (evidence.skin, evidence.slot_index, evidence.attachment_name):
        return UnweightedDeformValidation(False, "deform evidence 与 mesh 的 skin/slot/attachment 身份不完全一致。", scalar_count, len(evidence.frames))
    for index, frame in enumerate(evidence.frames):
        start = 0 if frame.start is None else frame.start
        if start < 0 or start % 2:
            return UnweightedDeformValidation(False, f"frame {index} 的 start 不是非负二维标量偏移。", scalar_count, len(evidence.frames))
        if len(frame.values) % 2:
            return UnweightedDeformValidation(False, f"frame {index} 的 values 不是二维标量序列。", scalar_count, len(evidence.frames))
        if start + len(frame.values) > scalar_count:
            return UnweightedDeformValidation(False, f"frame {index} 的 start/values 越过 mesh vertex 标量范围。", scalar_count, len(evidence.frames))
    return UnweightedDeformValidation(True, None, scalar_count, len(evidence.frames))
