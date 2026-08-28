from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .spine_attachment_evidence import SequenceEvidence
from .spine_sequence_timeline_evidence import SequenceTimelineEvidence


@dataclass(frozen=True)
class SequenceTimelineStaticRangeValidation:
    """4.1 sequence timeline 与静态 sequence attachment 的只读交叉审计。

    `raw_indices_within_sequence_region_range_only` 只说明已消费的 packed raw index
    落在 sequence 的零基 region index 范围 `0..count-1` 内。static `start` 仅是
    命名偏移，不参与该 index 上界。它不是 SequenceMode 求值、播放时刻
    的实际帧选择或可渲染性证明。
    """

    animation: str
    skin: str
    slot_index: int
    attachment_key: str | None
    attachment_name: str | None
    static_attachment_kind: str | None
    static_start: int | None
    static_count: int | None
    frame_count: int
    raw_sequence_indices: tuple[int, ...]
    raw_indices_outside_sequence_region_range: tuple[int, ...]
    state: str
    reason: str
    selection_state: str = "forbidden"
    rendering_state: str = "forbidden"
    writeback: str = "forbidden"


def validate_sequence_timeline_static_range(
    timeline: SequenceTimelineEvidence,
    static_sequences: Iterable[SequenceEvidence],
) -> SequenceTimelineStaticRangeValidation:
    """核验 identity 与零基 raw region index 范围，绝不实现 SequenceMode 或 frame selection。"""
    candidates = tuple(
        item
        for item in static_sequences
        if item.skin == timeline.skin
        and item.slot_index == timeline.slot_index
        and item.attachment_key == timeline.attachment_key
    )
    raw_indices = tuple(frame.sequence_index for frame in timeline.frames)
    common = (
        timeline.animation,
        timeline.skin,
        timeline.slot_index,
        timeline.attachment_key,
        timeline.attachment_name,
    )
    if not candidates:
        return SequenceTimelineStaticRangeValidation(*common, None, None, None, len(timeline.frames), raw_indices, (), "timeline_static_attachment_rejected", "static_attachment_key_not_captured")
    if len(candidates) != 1:
        return SequenceTimelineStaticRangeValidation(*common, None, None, None, len(timeline.frames), raw_indices, (), "timeline_static_attachment_rejected", "static_attachment_key_ambiguous")
    static = candidates[0]
    if static.count <= 0:
        return SequenceTimelineStaticRangeValidation(*common, static.attachment_kind, static.start, static.count, len(timeline.frames), raw_indices, (), "timeline_static_attachment_rejected", "static_sequence_range_invalid")
    outside = tuple(index for index in raw_indices if not 0 <= index < static.count)
    if outside:
        state = "timeline_static_identity_verified_raw_region_index_outside_only"
        reason = "raw_index_outside_sequence_region_range"
    else:
        state = "timeline_static_identity_verified_raw_region_index_observed_only"
        reason = "raw_indices_within_sequence_region_range_only"
    return SequenceTimelineStaticRangeValidation(
        *common,
        static.attachment_kind,
        static.start,
        static.count,
        len(timeline.frames),
        raw_indices,
        outside,
        state,
        reason,
    )
