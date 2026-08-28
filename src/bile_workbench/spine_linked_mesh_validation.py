from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol

from .spine_attachment_evidence import LinkedMeshEvidence, SequenceEvidence


class _MeshIdentity(Protocol):
    skin: str
    slot_index: int
    name: str
    attachment_key: str | None


@dataclass(frozen=True)
class LinkedMeshParentValidation:
    """linked mesh 到普通 mesh 的静态 identity 核验结果。

    ``verified_static_identity_only`` 只说明二进制声明的 parent skin、slot 与
    skin attachment table key 在当前已解析的普通 mesh 集合中恰好命中一次。它不复制 parent 顶点、
    不解释 inherit timelines/deform，也绝不把 linked mesh 交给 pose 或 renderer。
    """

    spine_version: str
    child_skin: str
    slot_index: int
    child_name: str
    declared_parent_skin: str | None
    resolved_parent_skin: str
    parent_name: str | None
    matched_parent_count: int
    state: str
    reason: str
    vertex_resolution_state: str = "forbidden"
    rendering_state: str = "forbidden"
    writeback: str = "forbidden"


def validate_linked_mesh_parent(
    linked: LinkedMeshEvidence,
    mesh_attachments: Iterable[_MeshIdentity],
    sequence_evidence: Iterable[SequenceEvidence] = (),
    *,
    default_skin: str = "default",
) -> LinkedMeshParentValidation:
    """严格验证 linked mesh 声明的 parent attachment key，绝不解析或应用 parent 几何。"""
    resolved_parent_skin = linked.parent_skin or default_skin
    if not linked.parent_name:
        return LinkedMeshParentValidation(
            linked.spine_version,
            linked.skin,
            linked.slot_index,
            linked.name,
            linked.parent_skin,
            resolved_parent_skin,
            linked.parent_name,
            0,
            "candidate_parent_rejected",
            "parent_name_missing",
        )
    matches = tuple(
        mesh
        for mesh in mesh_attachments
        if mesh.skin == resolved_parent_skin
        and mesh.slot_index == linked.slot_index
        and getattr(mesh, "attachment_key", None) == linked.parent_name
    )
    sequence_meshes = tuple(
        item
        for item in sequence_evidence
        if item.attachment_kind == "mesh"
        and item.skin == resolved_parent_skin
        and item.slot_index == linked.slot_index
        and item.attachment_key == linked.parent_name
    )
    candidates = len(matches) + len(sequence_meshes)
    if len(matches) == 1 and not sequence_meshes:
        state = "verified_static_identity_only"
        reason = "exact_skin_slot_attachment_key_match"
    elif not matches and len(sequence_meshes) == 1:
        state = "verified_static_identity_sequence_mesh_only"
        reason = "exact_skin_slot_attachment_key_match_sequence_mesh"
    elif not candidates:
        state = "candidate_parent_rejected"
        reason = "parent_attachment_key_not_in_parsed_mesh_subset"
    else:
        state = "candidate_parent_rejected"
        reason = "parent_identity_ambiguous"
    return LinkedMeshParentValidation(
        linked.spine_version,
        linked.skin,
        linked.slot_index,
        linked.name,
        linked.parent_skin,
        resolved_parent_skin,
        linked.parent_name,
        candidates,
        state,
        reason,
    )
