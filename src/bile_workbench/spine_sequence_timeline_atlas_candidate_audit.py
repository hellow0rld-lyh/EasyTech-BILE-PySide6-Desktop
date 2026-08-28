from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .spine_attachment_evidence import SequenceEvidence
from .spine_atlas import SpineAtlasRegion
from .spine_sequence_atlas_validation import validate_sequence_atlas_candidates
from .spine_sequence_timeline_evidence import SequenceTimelineEvidence
from .spine_sequence_timeline_time_audit import SequenceTimelineTimeAudit, audit_sequence_region_index_at_time


@dataclass(frozen=True)
class SequenceTimelineAtlasCandidateAudit:
    """单时刻 sequence name candidate 的静态身份交叉审计。

    `candidate_region_name` 仅是由已审计的整数和 static naming range 形成的字符串。
    它不是所选图像帧、纹理采样结果、Slot attachment 或渲染层。
    """

    time_audit: SequenceTimelineTimeAudit
    static_atlas_state: str | None
    candidate_region_name: str | None
    atlas_name_match_count: int
    state: str
    reason: str
    frame_selection_state: str = "forbidden"
    image_sampling_state: str = "forbidden"
    attachment_application_state: str = "forbidden"
    rendering_state: str = "forbidden"
    writeback: str = "forbidden"


def _static_candidate(timeline: SequenceTimelineEvidence, sequences: Iterable[SequenceEvidence]) -> SequenceEvidence | None:
    matches = tuple(
        item
        for item in sequences
        if item.skin == timeline.skin
        and item.slot_index == timeline.slot_index
        and item.attachment_key == timeline.attachment_key
    )
    return matches[0] if len(matches) == 1 else None


def audit_sequence_candidate_name_at_time(
    timeline: SequenceTimelineEvidence,
    static_sequences: Iterable[SequenceEvidence],
    regions: Iterable[SpineAtlasRegion],
    target_time: float,
) -> SequenceTimelineAtlasCandidateAudit:
    """以静态证据审计候选名称唯一性，不执行图像帧选择。"""
    sequences = tuple(static_sequences)
    regions = tuple(regions)
    time_audit = audit_sequence_region_index_at_time(timeline, sequences, target_time)
    if time_audit.state != "audited_region_index_only":
        return SequenceTimelineAtlasCandidateAudit(
            time_audit, None, None, 0, "candidate_name_audit_rejected", f"time_audit_{time_audit.reason}"
        )
    static = _static_candidate(timeline, sequences)
    if static is None or time_audit.candidate_name_ordinal is None:
        return SequenceTimelineAtlasCandidateAudit(
            time_audit, None, None, 0, "candidate_name_audit_rejected", "static_attachment_key_must_match_exactly_once"
        )
    validation = validate_sequence_atlas_candidates(static, regions)
    if validation.state != "candidate_range_verified_static_only":
        return SequenceTimelineAtlasCandidateAudit(
            time_audit, validation.state, None, 0, "candidate_name_audit_rejected", "static_candidate_range_not_verified"
        )
    candidate_name = f"{static.name}{time_audit.candidate_name_ordinal:0{static.digits}d}"
    match_count = sum(region.name == candidate_name for region in regions)
    if match_count == 1:
        return SequenceTimelineAtlasCandidateAudit(
            time_audit,
            validation.state,
            candidate_name,
            match_count,
            "candidate_name_identity_verified_static_only",
            "static_name_unique_at_audited_region_index",
        )
    reason = "candidate_name_missing_from_atlas" if match_count == 0 else "candidate_name_duplicate_in_atlas"
    return SequenceTimelineAtlasCandidateAudit(
        time_audit,
        validation.state,
        candidate_name,
        match_count,
        "candidate_name_audit_rejected",
        reason,
    )
