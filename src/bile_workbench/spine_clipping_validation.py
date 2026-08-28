from __future__ import annotations

from dataclasses import dataclass
from typing import Sized

from .spine_attachment_evidence import ClippingEvidence


@dataclass(frozen=True)
class ClippingStaticValidation:
    """clipping attachment 的最小静态边界验证，不构建或应用裁剪多边形。"""

    skin: str
    slot_index: int
    attachment_key: str
    end_slot_index: int
    vertex_count: int
    slot_count: int
    state: str
    reason: str
    vertex_application_state: str = "forbidden"
    clipping_rendering_state: str = "forbidden"
    writeback: str = "forbidden"


def validate_clipping_static_boundary(evidence: ClippingEvidence, slots: Sized) -> ClippingStaticValidation:
    """验证已消费索引的基本静态边界；不推断 clipping 范围、裁剪结果或绘制顺序。"""
    slot_count = len(slots)
    if evidence.vertex_count <= 0:
        state, reason = "clipping_static_boundary_rejected", "vertex_count_must_be_positive"
    elif not 0 <= evidence.end_slot_index < slot_count:
        state, reason = "clipping_static_boundary_rejected", "end_slot_index_out_of_range"
    else:
        state, reason = "clipping_static_boundary_verified_only", "consumed_end_slot_and_vertex_count_in_bounds"
    return ClippingStaticValidation(
        evidence.skin,
        evidence.slot_index,
        evidence.attachment_key,
        evidence.end_slot_index,
        evidence.vertex_count,
        slot_count,
        state,
        reason,
    )
