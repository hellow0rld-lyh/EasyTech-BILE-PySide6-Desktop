from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

from .spine_attachment_evidence import SequenceEvidence
from .spine_sequence_timeline_evidence import SequenceTimelineEvidence


_MODE_NAMES = (
    "hold",
    "once",
    "loop",
    "pingpong",
    "once_reverse",
    "loop_reverse",
    "pingpong_reverse",
)


@dataclass(frozen=True)
class SequenceTimelineTimeAudit:
    """单个 timeline 在一个未循环 raw time 的 region-index 审计。

    `audited_region_index` 是按官方 SequenceMode 数学规则从已读取数值导出的
    整数审计值，绝不是图像帧选择、slot sequence index 写入、attachment 应用或
    renderer 输入。调用方不得将它用作播放或图像采样的授权。
    """

    animation: str
    skin: str
    slot_index: int
    attachment_key: str | None
    target_time: float
    static_start: int | None
    static_count: int | None
    timeline_key_index: int | None
    timeline_key_time: float | None
    mode_ordinal: int | None
    mode_name: str | None
    base_region_index: int | None
    delay: float | None
    elapsed_steps: int | None
    audited_region_index: int | None
    candidate_name_ordinal: int | None
    state: str
    reason: str
    frame_selection_state: str = "forbidden"
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


def _rejected(
    timeline: SequenceTimelineEvidence,
    target_time: float,
    reason: str,
    *,
    static: SequenceEvidence | None = None,
    timeline_key_index: int | None = None,
    timeline_key_time: float | None = None,
    mode_ordinal: int | None = None,
    mode_name: str | None = None,
    base_region_index: int | None = None,
    delay: float | None = None,
) -> SequenceTimelineTimeAudit:
    return SequenceTimelineTimeAudit(
        animation=timeline.animation,
        skin=timeline.skin,
        slot_index=timeline.slot_index,
        attachment_key=timeline.attachment_key,
        target_time=target_time,
        static_start=None if static is None else static.start,
        static_count=None if static is None else static.count,
        timeline_key_index=timeline_key_index,
        timeline_key_time=timeline_key_time,
        mode_ordinal=mode_ordinal,
        mode_name=mode_name,
        base_region_index=base_region_index,
        delay=delay,
        elapsed_steps=None,
        audited_region_index=None,
        candidate_name_ordinal=None,
        state="audit_rejected",
        reason=reason,
    )


def audit_sequence_region_index_at_time(
    timeline: SequenceTimelineEvidence,
    static_sequences: Iterable[SequenceEvidence],
    target_time: float,
) -> SequenceTimelineTimeAudit:
    """审计一个未循环 raw time 的 region index，拒绝未显式覆盖的运行时前置条件。"""
    static = _static_candidate(timeline, static_sequences)
    if not math.isfinite(target_time) or target_time < 0:
        return _rejected(timeline, target_time, "target_time_must_be_finite_and_nonnegative")
    if static is None:
        return _rejected(timeline, target_time, "static_attachment_key_must_match_exactly_once")
    if static.count <= 0:
        return _rejected(timeline, target_time, "static_sequence_count_must_be_positive", static=static)
    if not timeline.frames:
        return _rejected(timeline, target_time, "timeline_has_no_frames", static=static)
    if any(not math.isfinite(frame.time) for frame in timeline.frames):
        return _rejected(timeline, target_time, "timeline_key_time_must_be_finite", static=static)
    if target_time < timeline.frames[0].time:
        return _rejected(timeline, target_time, "time_before_first_key_requires_runtime_blend_context", static=static)
    key_index = max(index for index, frame in enumerate(timeline.frames) if frame.time <= target_time)
    key = timeline.frames[key_index]
    if not 0 <= key.mode_ordinal < len(_MODE_NAMES):
        return _rejected(timeline, target_time, "mode_ordinal_out_of_official_range", static=static, timeline_key_index=key_index, timeline_key_time=key.time, mode_ordinal=key.mode_ordinal, base_region_index=key.sequence_index, delay=key.delay)
    if not 0 <= key.sequence_index < static.count:
        return _rejected(timeline, target_time, "base_region_index_outside_static_count", static=static, timeline_key_index=key_index, timeline_key_time=key.time, mode_ordinal=key.mode_ordinal, mode_name=_MODE_NAMES[key.mode_ordinal], base_region_index=key.sequence_index, delay=key.delay)
    mode_name = _MODE_NAMES[key.mode_ordinal]
    if mode_name == "hold":
        steps = 0
    else:
        if not math.isfinite(key.delay) or key.delay <= 0:
            return _rejected(timeline, target_time, "non_hold_mode_requires_positive_finite_delay", static=static, timeline_key_index=key_index, timeline_key_time=key.time, mode_ordinal=key.mode_ordinal, mode_name=mode_name, base_region_index=key.sequence_index, delay=key.delay)
        steps = math.floor((target_time - key.time) / key.delay + 0.00001)
    progressed = key.sequence_index + steps
    if mode_name == "hold":
        audited = key.sequence_index
    elif mode_name == "once":
        audited = min(static.count - 1, progressed)
    elif mode_name == "loop":
        audited = progressed % static.count
    elif mode_name == "pingpong":
        period = static.count * 2 - 2
        folded = 0 if period == 0 else progressed % period
        audited = period - folded if folded >= static.count else folded
    elif mode_name == "once_reverse":
        audited = max(static.count - 1 - progressed, 0)
    elif mode_name == "loop_reverse":
        audited = static.count - 1 - (progressed % static.count)
    else:  # pingpong_reverse
        period = static.count * 2 - 2
        folded = 0 if period == 0 else (progressed + static.count - 1) % period
        audited = period - folded if folded >= static.count else folded
    return SequenceTimelineTimeAudit(
        animation=timeline.animation,
        skin=timeline.skin,
        slot_index=timeline.slot_index,
        attachment_key=timeline.attachment_key,
        target_time=target_time,
        static_start=static.start,
        static_count=static.count,
        timeline_key_index=key_index,
        timeline_key_time=key.time,
        mode_ordinal=key.mode_ordinal,
        mode_name=mode_name,
        base_region_index=key.sequence_index,
        delay=key.delay,
        elapsed_steps=steps,
        audited_region_index=audited,
        candidate_name_ordinal=static.start + audited,
        state="audited_region_index_only",
        reason="unlooped_raw_time_mode_math_without_frame_selection",
    )
