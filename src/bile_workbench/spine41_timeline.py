"""征2标准 Spine 4.1.x animations 段的严格只读解析。"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .spine38_format import Spine38FormatError, _Reader, _count
from .spine41_format import Spine41StaticDocument, parse_file
from .spine_deform_evidence import DeformCurve, DeformFrameEvidence, DeformTimelineEvidence
from .spine_pose import PoseAnimation, PoseFrame, PoseTrack
from .spine_sequence_timeline_evidence import (
    SequenceTimelineEvidence,
    SequenceTimelineFrameEvidence,
    unpack_sequence_mode_and_index,
)

SLOT_TYPES = {0: ("attachment", None), 1: ("rgba", 4), 2: ("rgb", 3), 3: ("rgba2", 7), 4: ("rgb2", 6), 5: ("alpha", 1)}
BONE_TYPES = {0: ("rotate", 1), 1: ("translate", 2), 2: ("translate_x", 1), 3: ("translate_y", 1), 4: ("scale", 2), 5: ("scale_x", 1), 6: ("scale_y", 1), 7: ("shear", 2), 8: ("shear_x", 1), 9: ("shear_y", 1)}
PATH_TYPES = {0: ("position", 1), 1: ("spacing", 1), 2: ("mix", 3)}
ATTACHMENT_TYPES = {0: ("deform", 1), 1: ("sequence", None)}


@dataclass(frozen=True)
class Spine41Timeline:
    group: str
    kind: str
    target: str
    frame_count: int
    first_time: float
    last_time: float


@dataclass(frozen=True)
class Spine41Animation:
    name: str
    duration: float
    timelines: tuple[Spine41Timeline, ...]
    sequence_timeline_evidence: tuple[SequenceTimelineEvidence, ...] = ()


@dataclass(frozen=True)
class Spine41AnimationArchive:
    static: Spine41StaticDocument
    event_names: tuple[str | None, ...]
    animations: tuple[Spine41Animation, ...]
    animation_start: int
    animation_end: int

    @property
    def timeline_type_counts(self) -> dict[str, int]:
        return dict(Counter(f"{item.group}:{item.kind}" for animation in self.animations for item in animation.timelines))


@dataclass(frozen=True)
class _EventDefinition:
    name: str | None
    audio_path: str | None


def _time(reader: _Reader, label: str, previous: float | None) -> float:
    value = reader.f32(label)
    if value < 0 or previous is not None and value < previous:
        raise Spine38FormatError(f"{label} 不是单调非负时间：{value}")
    return value


def _curve(reader: _Reader, label: str, properties: int) -> DeformCurve:
    """读取曲线并保留原始语义；既有 timeline 调用可继续忽略返回值。"""
    curve = reader.byte(f"{label}.curve")
    if curve == 0:
        return "linear"
    if curve == 1:
        return "stepped"
    if curve != 2:
        raise Spine38FormatError(f"{label} curve 类型未知：{curve}")
    return tuple(
        tuple(reader.f32(f"{label}.bezier[{property_index}][{point}") for point in range(4))
        for property_index in range(properties)
    )


def _continuous(reader: _Reader, label: str, frame_count: int, value_bytes: int = 0, value_floats: int = 0, curve_properties: int = 0) -> tuple[float, float]:
    """读取4.1连续 timeline：首帧值，随后每段为下一帧值与曲线。"""
    if frame_count <= 0:
        raise Spine38FormatError(f"{label} 帧数为零")
    first = current = _time(reader, f"{label}.frame[0].time", None)
    for index in range(value_bytes):
        reader.byte(f"{label}.frame[0].byte[{index}]")
    for index in range(value_floats):
        reader.f32(f"{label}.frame[0].float[{index}]")
    for frame in range(frame_count - 1):
        current = _time(reader, f"{label}.frame[{frame + 1}].time", current)
        for index in range(value_bytes):
            reader.byte(f"{label}.frame[{frame + 1}].byte[{index}]")
        for index in range(value_floats):
            reader.f32(f"{label}.frame[{frame + 1}].float[{index}]")
        _curve(reader, f"{label}.frame[{frame}]", curve_properties)
    return first, current


def _slot(reader: _Reader, static: Spine41StaticDocument, output: list[Spine41Timeline]) -> float:
    duration = 0.0
    for group in range(_count(reader, "animation.slot_groups")):
        slot = reader.varint(f"slot_group[{group}].slot")
        if not 0 <= slot < len(static.slots):
            raise Spine38FormatError(f"slot timeline 索引越界：{slot}/{len(static.slots)}")
        target = static.slots[slot].name
        for index in range(_count(reader, f"slot[{target}].timeline_count")):
            type_id = reader.byte(f"slot[{target}].timeline[{index}].type")
            definition = SLOT_TYPES.get(type_id)
            if definition is None:
                raise Spine38FormatError(f"slot[{target}] timeline 类型未知：{type_id}")
            kind, channels = definition
            frames = _count(reader, f"slot[{target}].timeline[{index}].frame_count")
            if kind == "attachment":
                first = last = 0.0
                for frame in range(frames):
                    time = _time(reader, f"slot[{target}].attachment[{frame}].time", last if frame else None)
                    if frame == 0:
                        first = time
                    last = time
                    reader.ref_string(static.shared_strings, f"slot[{target}].attachment[{frame}].name")
            else:
                reader.varint(f"slot[{target}].{kind}.bezier_count")
                first, last = _continuous(reader, f"slot[{target}].{kind}", frames, value_bytes=channels or 0, curve_properties=channels or 0)
            output.append(Spine41Timeline("slot", kind, target, frames, first, last))
            duration = max(duration, last)
    return duration


def _bone(reader: _Reader, static: Spine41StaticDocument, output: list[Spine41Timeline]) -> float:
    duration = 0.0
    for group in range(_count(reader, "animation.bone_groups")):
        bone = reader.varint(f"bone_group[{group}].bone")
        if not 0 <= bone < len(static.bones):
            raise Spine38FormatError(f"bone timeline 索引越界：{bone}/{len(static.bones)}")
        target = static.bones[bone].name
        for index in range(_count(reader, f"bone[{target}].timeline_count")):
            type_id = reader.byte(f"bone[{target}].timeline[{index}].type")
            definition = BONE_TYPES.get(type_id)
            if definition is None:
                raise Spine38FormatError(f"bone[{target}] timeline 类型未知：{type_id}")
            kind, components = definition
            frames = _count(reader, f"bone[{target}].{kind}.frame_count")
            reader.varint(f"bone[{target}].{kind}.bezier_count")
            first, last = _continuous(reader, f"bone[{target}].{kind}", frames, value_floats=components, curve_properties=components)
            output.append(Spine41Timeline("bone", kind, target, frames, first, last))
            duration = max(duration, last)
    return duration


def _ik(reader: _Reader, static: Spine41StaticDocument, output: list[Spine41Timeline]) -> float:
    duration = 0.0
    for index in range(_count(reader, "animation.ik_count")):
        target = reader.varint(f"ik[{index}].constraint")
        if not 0 <= target < static.ik_constraint_count:
            raise Spine38FormatError(f"ik timeline 索引越界：{target}/{static.ik_constraint_count}")
        frames = _count(reader, f"ik[{target}].frame_count")
        reader.varint(f"ik[{target}].bezier_count")
        # 每帧：time, mix, softness, bend(byte), compress(bool), stretch(bool)。
        if frames <= 0:
            raise Spine38FormatError("ik timeline 帧数为零")
        first = last = _time(reader, f"ik[{target}].frame[0].time", None)
        reader.f32(f"ik[{target}].frame[0].mix"); reader.f32(f"ik[{target}].frame[0].softness")
        for frame in range(frames):
            reader.byte(f"ik[{target}].frame[{frame}].bend"); reader.bool(f"ik[{target}].frame[{frame}].compress"); reader.bool(f"ik[{target}].frame[{frame}].stretch")
            if frame < frames - 1:
                last = _time(reader, f"ik[{target}].frame[{frame + 1}].time", last)
                reader.f32(f"ik[{target}].frame[{frame + 1}].mix"); reader.f32(f"ik[{target}].frame[{frame + 1}].softness")
                _curve(reader, f"ik[{target}].frame[{frame}]", 2)
        output.append(Spine41Timeline("ik", "mix", str(target), frames, first, last))
        duration = max(duration, last)
    return duration


def _transform(reader: _Reader, static: Spine41StaticDocument, output: list[Spine41Timeline]) -> float:
    duration = 0.0
    for index in range(_count(reader, "animation.transform_count")):
        target = reader.varint(f"transform[{index}].constraint")
        if not 0 <= target < static.transform_constraint_count:
            raise Spine38FormatError(f"transform timeline 索引越界：{target}/{static.transform_constraint_count}")
        frames = _count(reader, f"transform[{target}].frame_count")
        reader.varint(f"transform[{target}].bezier_count")
        first, last = _continuous(reader, f"transform[{target}]", frames, value_floats=6, curve_properties=6)
        output.append(Spine41Timeline("transform", "mix", str(target), frames, first, last))
        duration = max(duration, last)
    return duration


def _path(reader: _Reader, static: Spine41StaticDocument, output: list[Spine41Timeline]) -> float:
    duration = 0.0
    for group in range(_count(reader, "animation.path_groups")):
        target = reader.varint(f"path_group[{group}].constraint")
        if not 0 <= target < static.path_constraint_count:
            raise Spine38FormatError(f"path timeline 索引越界：{target}/{static.path_constraint_count}")
        for index in range(_count(reader, f"path[{target}].timeline_count")):
            type_id = reader.byte(f"path[{target}].timeline[{index}].type")
            definition = PATH_TYPES.get(type_id)
            if definition is None:
                raise Spine38FormatError(f"path[{target}] timeline 类型未知：{type_id}")
            kind, components = definition
            frames = _count(reader, f"path[{target}].{kind}.frame_count")
            reader.varint(f"path[{target}].{kind}.bezier_count")
            first, last = _continuous(reader, f"path[{target}].{kind}", frames, value_floats=components, curve_properties=components)
            output.append(Spine41Timeline("path", kind, str(target), frames, first, last))
            duration = max(duration, last)
    return duration


def _attachment(
    reader: _Reader,
    static: Spine41StaticDocument,
    output: list[Spine41Timeline],
    evidence: list[DeformTimelineEvidence] | None = None,
    sequence_evidence: list[SequenceTimelineEvidence] | None = None,
) -> float:
    duration = 0.0
    for skin_group in range(_count(reader, "animation.attachment_skins")):
        skin = reader.varint(f"attachment_skin[{skin_group}].skin")
        if not 0 <= skin < len(static.skin_names):
            raise Spine38FormatError(f"attachment skin 索引越界：{skin}/{len(static.skin_names)}")
        skin_name = static.skin_names[skin]
        for slot_group in range(_count(reader, f"attachment[{skin_name}].slot_groups")):
            slot = reader.varint(f"attachment[{skin_name}].slot[{slot_group}].index")
            if not 0 <= slot < len(static.slots):
                raise Spine38FormatError(f"attachment slot 索引越界：{slot}/{len(static.slots)}")
            for index in range(_count(reader, f"attachment[{skin_name}].slot[{slot}].timeline_count")):
                name = reader.ref_string(static.shared_strings, f"attachment[{skin_name}].slot[{slot}].timeline[{index}].name")
                type_id = reader.byte(f"attachment[{skin_name}].slot[{slot}].timeline[{index}].type")
                definition = ATTACHMENT_TYPES.get(type_id)
                if definition is None:
                    raise Spine38FormatError(f"attachment timeline 类型未知：{type_id}")
                kind, curve_properties = definition
                frames = _count(reader, f"attachment[{skin_name}].slot[{slot}].{kind}.frame_count")
                if kind == "deform":
                    reader.varint(f"attachment[{skin_name}].slot[{slot}].deform.bezier_count")
                    if frames <= 0:
                        raise Spine38FormatError("deform timeline 帧数为零")
                    first = last = _time(reader, f"deform[{skin_name}:{slot}:{name}].frame[0].time", None)
                    evidence_frames: list[DeformFrameEvidence] = []
                    for frame in range(frames):
                        frame_time = last
                        start, values = _deform_values(reader, f"deform[{skin_name}:{slot}:{name}].frame[{frame}]")
                        curve = None
                        if frame < frames - 1:
                            last = _time(reader, f"deform[{skin_name}:{slot}:{name}].frame[{frame + 1}].time", last)
                            curve = _curve(reader, f"deform[{skin_name}:{slot}:{name}].frame[{frame}]", curve_properties or 0)
                        evidence_frames.append(DeformFrameEvidence(frame_time, start, values, curve))
                else:
                    first = last = 0.0
                    sequence_frames: list[SequenceTimelineFrameEvidence] = []
                    for frame in range(frames):
                        time = _time(reader, f"sequence[{skin_name}:{slot}:{name}].frame[{frame}].time", last if frame else None)
                        if frame == 0:
                            first = time
                        last = time
                        mode_and_index = reader.int32(f"sequence[{skin_name}:{slot}:{name}].frame[{frame}].mode_index")
                        mode_ordinal, sequence_index = unpack_sequence_mode_and_index(mode_and_index)
                        if mode_ordinal > 4:
                            raise Spine38FormatError(f"sequence mode 越界：{mode_ordinal}")
                        delay = reader.f32(f"sequence[{skin_name}:{slot}:{name}].frame[{frame}].delay")
                        sequence_frames.append(SequenceTimelineFrameEvidence(time, mode_and_index, mode_ordinal, sequence_index, delay))
                output.append(Spine41Timeline("attachment", kind, f"{skin_name}:{slot}:{name or '—'}", frames, first, last))
                if kind == "deform" and evidence is not None:
                    evidence.append(DeformTimelineEvidence(skin_name, slot, name, tuple(evidence_frames)))
                if kind == "sequence" and sequence_evidence is not None:
                    sequence_evidence.append(SequenceTimelineEvidence("4.1", "", skin_name, slot, name, tuple(sequence_frames), name))
                duration = max(duration, last)
    return duration


def _deform_values(reader: _Reader, label: str) -> tuple[int | None, tuple[float, ...]]:
    length = _count(reader, f"{label}.length", 2_000_000)
    if not length:
        return None, ()
    start = reader.varint(f"{label}.start")
    return start, tuple(reader.f32(f"{label}.value[{value}]") for value in range(length))


def _decode_draw_order(reader: _Reader, static: Spine41StaticDocument, label: str) -> tuple[int, ...]:
    """独立实现 4.1 draw-order offset → setup slot index 重排；二进制 offset 为正 varint。"""
    offset_count = _count(reader, f"{label}.offset_count", len(static.slots))
    slot_count = len(static.slots)
    order = [-1] * slot_count
    unchanged = [0] * (slot_count - offset_count)
    original_index = 0
    unchanged_index = 0
    previous_slot = -1
    for offset_index in range(offset_count):
        slot_index = reader.varint(f"{label}.offset[{offset_index}].slot")
        if not previous_slot < slot_index < slot_count:
            raise Spine38FormatError(f"draw order slot 索引不递增或越界：{slot_index}")
        previous_slot = slot_index
        while original_index < slot_index:
            unchanged[unchanged_index] = original_index
            unchanged_index += 1
            original_index += 1
        destination = original_index + reader.varint(f"{label}.offset[{offset_index}].value")
        if not 0 <= destination < slot_count or order[destination] != -1:
            raise Spine38FormatError(f"draw order 目标槽位无效或重复：{destination}")
        order[destination] = original_index
        original_index += 1
    while original_index < slot_count:
        unchanged[unchanged_index] = original_index
        unchanged_index += 1
        original_index += 1
    for index in range(slot_count - 1, -1, -1):
        if order[index] == -1:
            unchanged_index -= 1
            order[index] = unchanged[unchanged_index]
    return tuple(order)


def _draw_order(reader: _Reader, static: Spine41StaticDocument, output: list[Spine41Timeline]) -> float:
    frames = _count(reader, "animation.draw_order.frame_count")
    if frames == 0:
        return 0.0
    first = last = 0.0
    for frame in range(frames):
        time = _time(reader, f"draw_order.frame[{frame}].time", last if frame else None)
        if frame == 0:
            first = time
        last = time
        _decode_draw_order(reader, static, f"draw_order.frame[{frame}]")
    output.append(Spine41Timeline("draw_order", "order", "slots", frames, first, last))
    return last


def _capture_pose_ik_tracks(reader: _Reader, static: Spine41StaticDocument, tracks: list[PoseTrack], summaries: list[Spine41Timeline]) -> float:
    duration = 0.0
    for group in range(_count(reader, "animation.ik_count")):
        target = reader.varint(f"ik[{group}].constraint")
        if not 0 <= target < static.ik_constraint_count:
            raise Spine38FormatError(f"ik timeline 索引越界：{target}/{static.ik_constraint_count}")
        count = _count(reader, f"ik[{target}].frame_count")
        reader.varint(f"ik[{target}].bezier_count")
        if count <= 0:
            raise Spine38FormatError("ik timeline 帧数为零")
        mix_frames: list[PoseFrame] = []
        state_frames: list[PoseFrame] = []
        time = _time(reader, f"ik[{target}].frame[0].time", None)
        mix = reader.f32(f"ik[{target}].frame[0].mix")
        softness = reader.f32(f"ik[{target}].frame[0].softness")
        first = time
        for frame in range(count):
            raw_bend = reader.byte(f"ik[{target}].frame[{frame}].bend")
            bend = raw_bend - 256 if raw_bend > 127 else raw_bend
            compress = int(reader.bool(f"ik[{target}].frame[{frame}].compress"))
            stretch = int(reader.bool(f"ik[{target}].frame[{frame}].stretch"))
            curve = None
            if frame < count - 1:
                next_time = _time(reader, f"ik[{target}].frame[{frame + 1}].time", time)
                next_mix = reader.f32(f"ik[{target}].frame[{frame + 1}].mix")
                next_softness = reader.f32(f"ik[{target}].frame[{frame + 1}].softness")
                curve = _capture_curve(reader, f"ik[{target}].frame[{frame}]", 2)
            mix_frames.append(PoseFrame(time, (mix, softness), curve))
            state_frames.append(PoseFrame(time, (bend, compress, stretch)))
            if frame < count - 1:
                time, mix, softness = next_time, next_mix, next_softness
        name = static.ik_constraints[target].name
        tracks.extend((PoseTrack("ik", "mix", target, name, tuple(mix_frames)), PoseTrack("ik", "state", target, name, tuple(state_frames))))
        summaries.append(Spine41Timeline("ik", "mix", name, count, first, time))
        duration = max(duration, time)
    return duration


def _capture_pose_transform_tracks(reader: _Reader, static: Spine41StaticDocument, tracks: list[PoseTrack], summaries: list[Spine41Timeline]) -> float:
    duration = 0.0
    for group in range(_count(reader, "animation.transform_count")):
        target = reader.varint(f"transform[{group}].constraint")
        if not 0 <= target < static.transform_constraint_count:
            raise Spine38FormatError(f"transform timeline 索引越界：{target}/{static.transform_constraint_count}")
        count = _count(reader, f"transform[{target}].frame_count")
        reader.varint(f"transform[{target}].bezier_count")
        frames, first, last = _capture_continuous(reader, f"transform[{target}]", count, 6)
        name = static.transform_constraints[target].name
        tracks.append(PoseTrack("transform", "mix", target, name, frames))
        summaries.append(Spine41Timeline("transform", "mix", name, count, first, last))
        duration = max(duration, last)
    return duration


def _capture_pose_draw_order(reader: _Reader, static: Spine41StaticDocument, tracks: list[PoseTrack], summaries: list[Spine41Timeline]) -> float:
    count = _count(reader, "animation.draw_order.frame_count")
    if count == 0:
        return 0.0
    frames: list[PoseFrame] = []
    first = last = 0.0
    for frame in range(count):
        time = _time(reader, f"draw_order.frame[{frame}].time", last if frame else None)
        if frame == 0:
            first = time
        last = time
        frames.append(PoseFrame(time, _decode_draw_order(reader, static, f"draw_order.frame[{frame}]")))
    tracks.append(PoseTrack("draw_order", "order", -1, "slots", tuple(frames)))
    summaries.append(Spine41Timeline("draw_order", "order", "slots", count, first, last))
    return last


def _event(reader: _Reader, events: tuple[_EventDefinition, ...], output: list[Spine41Timeline]) -> float:
    frames = _count(reader, "animation.events.frame_count")
    if frames == 0:
        return 0.0
    first = last = 0.0
    for frame in range(frames):
        time = _time(reader, f"events.frame[{frame}].time", last if frame else None)
        if frame == 0:
            first = time
        last = time
        index = reader.varint(f"events.frame[{frame}].event")
        if not 0 <= index < len(events):
            raise Spine38FormatError(f"event timeline 索引越界：{index}/{len(events)}")
        reader.varint(f"events.frame[{frame}].int", positive=False); reader.f32(f"events.frame[{frame}].float")
        if reader.bool(f"events.frame[{frame}].has_string"):
            reader.string(f"events.frame[{frame}].string")
        if events[index].audio_path is not None:
            reader.f32(f"events.frame[{frame}].volume"); reader.f32(f"events.frame[{frame}].balance")
    output.append(Spine41Timeline("event", "event", "events", frames, first, last))
    return last


def _animation(reader: _Reader, static: Spine41StaticDocument, events: tuple[_EventDefinition, ...], name: str) -> Spine41Animation:
    reader.varint(f"animation[{name}].timeline_capacity")
    timelines: list[Spine41Timeline] = []
    sequence_evidence: list[SequenceTimelineEvidence] = []
    duration = max(_slot(reader, static, timelines), _bone(reader, static, timelines), _ik(reader, static, timelines), _transform(reader, static, timelines), _path(reader, static, timelines), _attachment(reader, static, timelines, sequence_evidence=sequence_evidence), _draw_order(reader, static, timelines), _event(reader, events, timelines))
    evidence = tuple(
        SequenceTimelineEvidence(item.spine_version, name, item.skin, item.slot_index, item.attachment_name, item.frames, item.attachment_key)
        for item in sequence_evidence
    )
    return Spine41Animation(name, duration, tuple(timelines), evidence)


def _capture_curve(reader: _Reader, label: str, properties: int) -> str | tuple[tuple[float, float, float, float], ...]:
    curve = reader.byte(f"{label}.curve")
    if curve == 0:
        return "linear"
    if curve == 1:
        return "stepped"
    if curve != 2:
        raise Spine38FormatError(f"{label} curve 类型未知：{curve}")
    return tuple(
        tuple(reader.f32(f"{label}.bezier[{property_index}][{point}]") for point in range(4))
        for property_index in range(properties)
    )


def _capture_continuous(reader: _Reader, label: str, count: int, components: int) -> tuple[tuple[PoseFrame, ...], float, float]:
    if count <= 0:
        raise Spine38FormatError(f"{label} 帧数为零")
    first = last = _time(reader, f"{label}.frame[0].time", None)
    raw: list[list[object]] = [[first, tuple(reader.f32(f"{label}.frame[0].value[{item}]") for item in range(components)), None]]
    for frame in range(count - 1):
        current = _time(reader, f"{label}.frame[{frame + 1}].time", last)
        values = tuple(reader.f32(f"{label}.frame[{frame + 1}].value[{item}]") for item in range(components))
        raw[-1][2] = _capture_curve(reader, f"{label}.frame[{frame}]", components)
        raw.append([current, values, None])
        last = current
    return tuple(PoseFrame(float(item[0]), item[1], item[2]) for item in raw), first, last


def _capture_slot_continuous(reader: _Reader, label: str, count: int, components: int) -> tuple[tuple[PoseFrame, ...], float, float]:
    """4.1 slot color timelines use packed 0..255 channel bytes, unlike bone float timelines."""
    if count <= 0:
        raise Spine38FormatError(f"{label} 帧数为零")
    first = last = _time(reader, f"{label}.frame[0].time", None)
    raw: list[list[object]] = [[first, tuple(reader.byte(f"{label}.frame[0].value[{item}]") / 255.0 for item in range(components)), None]]
    for frame in range(count - 1):
        current = _time(reader, f"{label}.frame[{frame + 1}].time", last)
        values = tuple(reader.byte(f"{label}.frame[{frame + 1}].value[{item}]") / 255.0 for item in range(components))
        raw[-1][2] = _capture_curve(reader, f"{label}.frame[{frame}]", components)
        raw.append([current, values, None])
        last = current
    return tuple(PoseFrame(float(item[0]), item[1], item[2]) for item in raw), first, last


def _capture_pose_slot_tracks(reader: _Reader, static: Spine41StaticDocument, tracks: list[PoseTrack], summaries: list[Spine41Timeline]) -> float:
    duration = 0.0
    for group in range(_count(reader, "animation.slot_groups")):
        slot = reader.varint(f"slot_group[{group}].slot")
        if not 0 <= slot < len(static.slots):
            raise Spine38FormatError(f"slot timeline 索引越界：{slot}/{len(static.slots)}")
        target = static.slots[slot].name
        for index in range(_count(reader, f"slot[{target}].timeline_count")):
            type_id = reader.byte(f"slot[{target}].timeline[{index}].type")
            definition = SLOT_TYPES.get(type_id)
            if definition is None:
                raise Spine38FormatError(f"slot[{target}] timeline 类型未知：{type_id}")
            kind, channels = definition
            count = _count(reader, f"slot[{target}].timeline[{index}].frame_count")
            if kind == "attachment":
                raw: list[PoseFrame] = []
                first = last = 0.0
                for frame in range(count):
                    time = _time(reader, f"slot[{target}].attachment[{frame}].time", last if frame else None)
                    if frame == 0:
                        first = time
                    last = time
                    raw.append(PoseFrame(time, (reader.ref_string(static.shared_strings, f"slot[{target}].attachment[{frame}].name"),)))
                tracks.append(PoseTrack("slot", kind, slot, target, tuple(raw)))
            else:
                reader.varint(f"slot[{target}].{kind}.bezier_count")
                raw, first, last = _capture_slot_continuous(reader, f"slot[{target}].{kind}", count, channels or 0)
                tracks.append(PoseTrack("slot", kind, slot, target, raw))
            summaries.append(Spine41Timeline("slot", kind, target, count, first, last))
            duration = max(duration, last)
    return duration


def _capture_pose_bone_tracks(reader: _Reader, static: Spine41StaticDocument, tracks: list[PoseTrack], summaries: list[Spine41Timeline]) -> float:
    duration = 0.0
    for group in range(_count(reader, "animation.bone_groups")):
        bone = reader.varint(f"bone_group[{group}].bone")
        if not 0 <= bone < len(static.bones):
            raise Spine38FormatError(f"bone timeline 索引越界：{bone}/{len(static.bones)}")
        target = static.bones[bone].name
        for index in range(_count(reader, f"bone[{target}].timeline_count")):
            type_id = reader.byte(f"bone[{target}].timeline[{index}].type")
            definition = BONE_TYPES.get(type_id)
            if definition is None:
                raise Spine38FormatError(f"bone[{target}] timeline 类型未知：{type_id}")
            kind, components = definition
            count = _count(reader, f"bone[{target}].{kind}.frame_count")
            reader.varint(f"bone[{target}].{kind}.bezier_count")
            frames, first, last = _capture_continuous(reader, f"bone[{target}].{kind}", count, components)
            tracks.append(PoseTrack("bone", kind, bone, target, frames))
            summaries.append(Spine41Timeline("bone", kind, target, count, first, last))
            duration = max(duration, last)
    return duration


def parse_spine41_pose_animation(path: Path, animation_name: str) -> tuple[Spine41StaticDocument, PoseAnimation]:
    static = parse_file(path)
    data = path.read_bytes()
    reader = _Reader(data)
    reader.offset = static.static_end
    events: list[_EventDefinition] = []
    for index in range(_count(reader, "events.count")):
        name = reader.ref_string(static.shared_strings, f"events[{index}].name")
        reader.varint(f"events[{index}].int", positive=False); reader.f32(f"events[{index}].float"); reader.string(f"events[{index}].string")
        audio = reader.string(f"events[{index}].audio")
        if audio is not None:
            reader.f32(f"events[{index}].volume"); reader.f32(f"events[{index}].balance")
        events.append(_EventDefinition(name, audio))
    tracks: list[PoseTrack] = []
    deform_evidence: list[DeformTimelineEvidence] = []
    selected_summary: list[Spine41Timeline] | None = None
    duration = 0.0
    for index in range(_count(reader, "animations.count")):
        name = reader.string(f"animations[{index}].name")
        if not name:
            raise Spine38FormatError(f"animations[{index}].name 为空")
        if name != animation_name:
            _animation(reader, static, tuple(events), name)
            continue
        reader.varint(f"animation[{name}].timeline_capacity")
        summaries: list[Spine41Timeline] = []
        duration = max(_capture_pose_slot_tracks(reader, static, tracks, summaries), _capture_pose_bone_tracks(reader, static, tracks, summaries), _capture_pose_ik_tracks(reader, static, tracks, summaries), _capture_pose_transform_tracks(reader, static, tracks, summaries), _path(reader, static, summaries), _attachment(reader, static, summaries, deform_evidence), _capture_pose_draw_order(reader, static, tracks, summaries), _event(reader, tuple(events), summaries))
        selected_summary = summaries
    if reader.offset != len(data):
        raise Spine38FormatError(f"4.1 animations 段未完整消费：offset={reader.offset} total={len(data)}")
    if selected_summary is None:
        raise Spine38FormatError(f"未找到动画根：{animation_name}")
    supported = {
        "bone:rotate", "bone:translate", "bone:scale", "bone:shear",
        "slot:attachment", "slot:rgba", "slot:rgb", "slot:rgba2", "slot:rgb2", "slot:alpha", "draw_order:order", "ik:mix", "transform:mix",
    }
    unsupported = tuple(sorted({f"{item.group}:{item.kind}" for item in selected_summary if f"{item.group}:{item.kind}" not in supported}))
    return static, PoseAnimation(animation_name, duration, tuple(tracks), unsupported, tuple(deform_evidence))


def parse_spine41_animations(path: Path) -> Spine41AnimationArchive:
    static = parse_file(path)
    data = path.read_bytes()
    reader = _Reader(data)
    reader.offset = static.static_end
    events: list[_EventDefinition] = []
    for index in range(_count(reader, "events.count")):
        name = reader.ref_string(static.shared_strings, f"events[{index}].name")
        reader.varint(f"events[{index}].int", positive=False); reader.f32(f"events[{index}].float"); reader.string(f"events[{index}].string")
        audio = reader.string(f"events[{index}].audio")
        if audio is not None:
            reader.f32(f"events[{index}].volume"); reader.f32(f"events[{index}].balance")
        events.append(_EventDefinition(name, audio))
    count = _count(reader, "animations.count")
    animation_start = reader.offset
    animations = []
    for index in range(count):
        name = reader.string(f"animations[{index}].name")
        if not name:
            raise Spine38FormatError(f"animations[{index}].name 为空")
        animations.append(_animation(reader, static, tuple(events), name))
    if reader.offset != len(data):
        raise Spine38FormatError(f"4.1 animations 段未完整消费：offset={reader.offset} total={len(data)} remaining={len(data) - reader.offset}")
    return Spine41AnimationArchive(static, tuple(item.name for item in events), tuple(animations), animation_start, reader.offset)
