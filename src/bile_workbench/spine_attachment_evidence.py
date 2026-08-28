"""Spine linked mesh / sequence 的静态只读证据模型；不包含运行时解析、渲染或 BIN 写回。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class LinkedMeshEvidence:
    spine_version: str
    skin: str
    slot_index: int
    name: str
    path: str | None
    parent_skin: str | None
    parent_name: str | None
    inherit_deform: bool
    sequence_present: bool = False
    attachment_key: str | None = None


@dataclass(frozen=True)
class SequenceEvidence:
    spine_version: str
    skin: str
    slot_index: int
    name: str
    count: int
    start: int
    digits: int
    setup_index: int
    attachment_key: str | None = None
    attachment_kind: str | None = None


@dataclass(frozen=True)
class ClippingEvidence:
    """Spine clipping attachment 的已消费静态边界证据。

    不保留顶点坐标，也不构建裁剪多边形；end slot 与 vertex count 仅供审计。
    """

    spine_version: str
    skin: str
    slot_index: int
    name: str
    attachment_key: str
    end_slot_index: int
    vertex_count: int
    vertex_application_state: str = "forbidden"
    clipping_rendering_state: str = "forbidden"
    writeback: str = "forbidden"


@dataclass(frozen=True)
class AttachmentEvidenceStatus:
    linked_mesh_count: int
    sequence_count: int
    linked_mesh_state: str
    sequence_state: str
    rendering_state: str = "forbidden"


def attachment_evidence_status(linked_meshes: Iterable[LinkedMeshEvidence], sequences: Iterable[SequenceEvidence]) -> AttachmentEvidenceStatus:
    """生成仅反映已捕获静态元数据的审计状态，绝不推断运行时渲染支持。"""
    linked_count = len(tuple(linked_meshes))
    sequence_count = len(tuple(sequences))
    return AttachmentEvidenceStatus(
        linked_count,
        sequence_count,
        "captured_static_only" if linked_count else "not_captured_in_current_sample",
        "captured_static_only" if sequence_count else "not_captured_in_current_sample",
    )


def linked_mesh_is_same_slot(candidate: LinkedMeshEvidence, parent_slot_index: int) -> bool:
    """只读审计辅助：linked mesh 与其 source 必须同 slot，未验证时返回 False。"""
    return candidate.slot_index == parent_slot_index
