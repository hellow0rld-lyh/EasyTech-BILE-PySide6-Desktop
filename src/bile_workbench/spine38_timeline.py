"""欧7标准 Spine 3.8.99 animations 段的严格只读解析。"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .spine38_format import Spine38FormatError, Spine38StaticDocument, _Reader, _count, parse_file
from .spine_deform_evidence import DeformCurve, DeformFrameEvidence, DeformTimelineEvidence
from .spine_pose import PoseAnimation, PoseFrame, PoseTrack, unpack_rgba

SLOT_TYPES = {0: "attachment", 1: "color", 2: "two_color"}
BONE_TYPES = {0: "rotate", 1: "translate", 2: "scale", 3: "shear"}
PATH_TYPES = {0: "position", 1: "spacing", 2: "mix"}
CURVE_TYPES = {0: "linear", 1: "stepped", 2: "bezier"}


@dataclass(frozen=True)
class Spine38Timeline:
    group: str
    kind: str
    target: str
    frame_count: int
    first_time: float
    last_time: float


@dataclass(frozen=True)
class Spine38Animation:
    name: str
    duration: float
    timelines: tuple[Spine38Timeline, ...]


@dataclass(frozen=True)
class Spine38AnimationArchive:
    static: Spine38StaticDocument
    event_names: tuple[str | None, ...]
    animations: tuple[Spine38Animation, ...]
    animation_start: int
    animation_end: int

    @property
    def timeline_type_counts(self) -> dict[str, int]:
        return dict(Counter(f"{item.group}:{item.kind}" for animation in self.animations for item in animation.timelines))


@dataclass(frozen=True)
class _EventDefinition:
    name: str | None
    audio_path: str | None


def _curve(reader: _Reader, label: str) -> DeformCurve:
    """读取曲线并保留原始语义；调用方可忽略返回值以保持原有消费行为。"""
    kind = reader.byte(f"{label}.curve")
    if kind == 0:
        return "linear"
    if kind == 1:
        return "stepped"
    if kind == 2:
        return ((tuple(reader.f32(f"{label}.curve_bezier[{index}]") for index in range(4))),)
    raise Spine38FormatError(f"{label} curve 类型未知：{kind}")


def _frame_time(reader: _Reader, label: str, previous: float | None) -> float:
    value = reader.f32(label)
    if value < 0:
        raise Spine38FormatError(f"{label} 为负时间：{value}")
    if previous is not None and value < previous:
        raise Spine38FormatError(f"{label} 未单调递增：{value} < {previous}")
    return value


def _consume_standard_frames(reader: _Reader, label: str, frame_count: int, extra_floats: int, extra_ints: int, attachment_ref: bool = False) -> tuple[float, float]:
    first = last = 0.0
    for index in range(frame_count):
        time = _frame_time(reader, f"{label}.frame[{index}].time", last if index else None)
        if index == 0:
            first = time
        last = time
        for value in range(extra_floats):
            reader.f32(f"{label}.frame[{index}].float[{value}]")
        for value in range(extra_ints):
            reader.int32(f"{label}.frame[{index}].int[{value}]")
        if attachment_ref:
            reader.ref_string(_CURRENT_STRINGS.get(), f"{label}.frame[{index}].attachment")
        if index < frame_count - 1:
            _curve(reader, f"{label}.frame[{index}]")
    return first, last


class _StringContext:
    """避免在各 helper 的签名中重复传共享字符串；仅限同步单线程解析。"""

    def __init__(self) -> None:
        self.value: tuple[str | None, ...] = ()

    def set(self, value: tuple[str | None, ...]) -> None:
        self.value = value

    def get(self) -> tuple[str | None, ...]:
        return self.value


_CURRENT_STRINGS = _StringContext()


def _slot_timelines(reader: _Reader, static: Spine38StaticDocument, output: list[Spine38Timeline]) -> float:
    duration = 0.0
    for group_index in range(_count(reader, "animation.slot_groups")):
        slot_index = reader.varint(f"animation.slot_groups[{group_index}].slot")
        if not 0 <= slot_index < len(static.slots):
            raise Spine38FormatError(f"slot timeline 引用越界：{slot_index}/{len(static.slots)}")
        target = static.slots[slot_index].name
        for timeline_index in range(_count(reader, f"animation.slot_groups[{group_index}].timelines")):
            kind_id = reader.byte(f"slot[{target}].timeline[{timeline_index}].type")
            kind = SLOT_TYPES.get(kind_id)
            if kind is None:
                raise Spine38FormatError(f"slot[{target}] timeline 类型未知：{kind_id}")
            frame_count = _count(reader, f"slot[{target}].timeline[{timeline_index}].frame_count")
            if frame_count == 0:
                raise Spine38FormatError(f"slot[{target}] timeline 帧数为零")
            if kind == "attachment":
                first = last = 0.0
                for frame in range(frame_count):
                    time = _frame_time(reader, f"slot[{target}].attachment[{frame}].time", last if frame else None)
                    if frame == 0:
                        first = time
                    last = time
                    reader.ref_string(static.shared_strings, f"slot[{target}].attachment[{frame}].name")
            elif kind == "color":
                first, last = _consume_standard_frames(reader, f"slot[{target}].color", frame_count, 0, 1)
            else:
                first, last = _consume_standard_frames(reader, f"slot[{target}].two_color", frame_count, 0, 2)
            output.append(Spine38Timeline("slot", kind, target, frame_count, first, last))
            duration = max(duration, last)
    return duration


def _bone_timelines(reader: _Reader, static: Spine38StaticDocument, output: list[Spine38Timeline]) -> float:
    duration = 0.0
    for group_index in range(_count(reader, "animation.bone_groups")):
        bone_index = reader.varint(f"animation.bone_groups[{group_index}].bone")
        if not 0 <= bone_index < len(static.bones):
            raise Spine38FormatError(f"bone timeline 引用越界：{bone_index}/{len(static.bones)}")
        target = static.bones[bone_index].name
        for timeline_index in range(_count(reader, f"animation.bone_groups[{group_index}].timelines")):
            kind_id = reader.byte(f"bone[{target}].timeline[{timeline_index}].type")
            kind = BONE_TYPES.get(kind_id)
            if kind is None:
                raise Spine38FormatError(f"bone[{target}] timeline 类型未知：{kind_id}")
            frame_count = _count(reader, f"bone[{target}].timeline[{timeline_index}].frame_count")
            if frame_count == 0:
                raise Spine38FormatError(f"bone[{target}] timeline 帧数为零")
            floats = 1 if kind == "rotate" else 2
            first, last = _consume_standard_frames(reader, f"bone[{target}].{kind}", frame_count, floats, 0)
            output.append(Spine38Timeline("bone", kind, target, frame_count, first, last))
            duration = max(duration, last)
    return duration


def _ik_timelines(reader: _Reader, static: Spine38StaticDocument, output: list[Spine38Timeline]) -> float:
    duration = 0.0
    for index in range(_count(reader, "animation.ik_groups")):
        target = reader.varint(f"animation.ik[{index}].constraint")
        if not 0 <= target < static.ik_constraint_count:
            raise Spine38FormatError(f"ik timeline 引用越界：{target}/{static.ik_constraint_count}")
        frame_count = _count(reader, f"animation.ik[{index}].frame_count")
        if frame_count == 0:
            raise Spine38FormatError("ik timeline 帧数为零")
        first = last = 0.0
        for frame in range(frame_count):
            time = _frame_time(reader, f"ik[{target}].frame[{frame}].time", last if frame else None)
            if frame == 0:
                first = time
            last = time
            reader.f32(f"ik[{target}].frame[{frame}].mix"); reader.f32(f"ik[{target}].frame[{frame}].softness")
            reader.byte(f"ik[{target}].frame[{frame}].bend"); reader.bool(f"ik[{target}].frame[{frame}].compress"); reader.bool(f"ik[{target}].frame[{frame}].stretch")
            if frame < frame_count - 1:
                _curve(reader, f"ik[{target}].frame[{frame}]")
        output.append(Spine38Timeline("ik", "mix", str(target), frame_count, first, last))
        duration = max(duration, last)
    return duration


def _transform_timelines(reader: _Reader, static: Spine38StaticDocument, output: list[Spine38Timeline]) -> float:
    duration = 0.0
    for index in range(_count(reader, "animation.transform_groups")):
        target = reader.varint(f"animation.transform[{index}].constraint")
        if not 0 <= target < static.transform_constraint_count:
            raise Spine38FormatError(f"transform timeline 引用越界：{target}/{static.transform_constraint_count}")
        frame_count = _count(reader, f"animation.transform[{index}].frame_count")
        if frame_count == 0:
            raise Spine38FormatError("transform timeline 帧数为零")
        first, last = _consume_standard_frames(reader, f"transform[{target}]", frame_count, 4, 0)
        output.append(Spine38Timeline("transform", "mix", str(target), frame_count, first, last))
        duration = max(duration, last)
    return duration


def _path_timelines(reader: _Reader, static: Spine38StaticDocument, output: list[Spine38Timeline]) -> float:
    duration = 0.0
    for group_index in range(_count(reader, "animation.path_groups")):
        target = reader.varint(f"animation.path_groups[{group_index}].constraint")
        if not 0 <= target < static.path_constraint_count:
            raise Spine38FormatError(f"path timeline 引用越界：{target}/{static.path_constraint_count}")
        for timeline_index in range(_count(reader, f"path[{target}].timelines")):
            kind_id = reader.byte(f"path[{target}].timeline[{timeline_index}].type")
            kind = PATH_TYPES.get(kind_id)
            if kind is None:
                raise Spine38FormatError(f"path[{target}] timeline 类型未知：{kind_id}")
            frame_count = _count(reader, f"path[{target}].timeline[{timeline_index}].frame_count")
            if frame_count == 0:
                raise Spine38FormatError(f"path[{target}] timeline 帧数为零")
            first, last = _consume_standard_frames(reader, f"path[{target}].{kind}", frame_count, 2 if kind == "mix" else 1, 0)
            output.append(Spine38Timeline("path", kind, str(target), frame_count, first, last))
            duration = max(duration, last)
    return duration


def _deform_timelines(reader: _Reader, static: Spine38StaticDocument, output: list[Spine38Timeline], evidence: list[DeformTimelineEvidence] | None = None) -> float:
    duration = 0.0
    skin_names = static.skin_names
    for skin_group in range(_count(reader, "animation.deform_skins")):
        skin_index = reader.varint(f"animation.deform_skins[{skin_group}].skin")
        if not 0 <= skin_index < len(skin_names):
            raise Spine38FormatError(f"deform skin 引用越界：{skin_index}/{len(skin_names)}")
        skin = skin_names[skin_index]
        for slot_group in range(_count(reader, f"deform[{skin}].slot_groups")):
            slot_index = reader.varint(f"deform[{skin}].slot[{slot_group}].index")
            if not 0 <= slot_index < len(static.slots):
                raise Spine38FormatError(f"deform slot 引用越界：{slot_index}/{len(static.slots)}")
            for timeline_index in range(_count(reader, f"deform[{skin}].slot[{slot_index}].timelines")):
                attachment = reader.ref_string(static.shared_strings, f"deform[{skin}].slot[{slot_index}].timeline[{timeline_index}].attachment")
                frame_count = _count(reader, f"deform[{skin}].slot[{slot_index}].timeline[{timeline_index}].frame_count")
                if frame_count == 0:
                    raise Spine38FormatError("deform timeline 帧数为零")
                first = last = 0.0
                frames: list[DeformFrameEvidence] = []
                for frame in range(frame_count):
                    time = _frame_time(reader, f"deform[{skin}].slot[{slot_index}].frame[{frame}].time", last if frame else None)
                    if frame == 0:
                        first = time
                    last = time
                    length = _count(reader, f"deform[{skin}].slot[{slot_index}].frame[{frame}].length", 2_000_000)
                    start = None
                    values: tuple[float, ...] = ()
                    if length:
                        start = reader.varint(f"deform[{skin}].slot[{slot_index}].frame[{frame}].start")
                        values = tuple(reader.f32(f"deform[{skin}].slot[{slot_index}].frame[{frame}].value[{value}]") for value in range(length))
                    curve = None
                    if frame < frame_count - 1:
                        curve = _curve(reader, f"deform[{skin}].slot[{slot_index}].frame[{frame}]")
                    frames.append(DeformFrameEvidence(time, start, values, curve))
                output.append(Spine38Timeline("deform", "vertices", f"{skin}:{slot_index}:{attachment or '—'}", frame_count, first, last))
                if evidence is not None:
                    evidence.append(DeformTimelineEvidence(skin, slot_index, attachment, tuple(frames)))
                duration = max(duration, last)
    return duration


def _decode_draw_order(reader: _Reader, static: Spine38StaticDocument, label: str) -> tuple[int, ...]:
    """独立实现官方 3.8 offset → slot index 排列语义；offset 与 slot index 均为正 varint。"""
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


def _draw_order(reader: _Reader, static: Spine38StaticDocument, output: list[Spine38Timeline]) -> float:
    frame_count = _count(reader, "animation.draw_order.frame_count")
    if frame_count == 0:
        return 0.0
    first = last = 0.0
    for frame in range(frame_count):
        time = _frame_time(reader, f"draw_order.frame[{frame}].time", last if frame else None)
        if frame == 0:
            first = time
        last = time
        _decode_draw_order(reader, static, f"draw_order.frame[{frame}]")
    output.append(Spine38Timeline("draw_order", "order", "slots", frame_count, first, last))
    return last


def _capture_pose_draw_order(reader: _Reader, static: Spine38StaticDocument, tracks: list[PoseTrack], summaries: list[Spine38Timeline]) -> float:
    frame_count = _count(reader, "animation.draw_order.frame_count")
    if frame_count == 0:
        return 0.0
    frames: list[PoseFrame] = []
    first = last = 0.0
    for frame in range(frame_count):
        time = _frame_time(reader, f"draw_order.frame[{frame}].time", last if frame else None)
        if frame == 0:
            first = time
        last = time
        frames.append(PoseFrame(time, _decode_draw_order(reader, static, f"draw_order.frame[{frame}]")))
    tracks.append(PoseTrack("draw_order", "order", -1, "slots", tuple(frames)))
    summaries.append(Spine38Timeline("draw_order", "order", "slots", frame_count, first, last))
    return last


def _event_timeline(reader: _Reader, events: tuple[_EventDefinition, ...], output: list[Spine38Timeline]) -> float:
    frame_count = _count(reader, "animation.events.frame_count")
    if frame_count == 0:
        return 0.0
    first = last = 0.0
    for frame in range(frame_count):
        time = _frame_time(reader, f"events.frame[{frame}].time", last if frame else None)
        if frame == 0:
            first = time
        last = time
        index = reader.varint(f"events.frame[{frame}].event")
        if not 0 <= index < len(events):
            raise Spine38FormatError(f"event timeline 引用越界：{index}/{len(events)}")
        reader.varint(f"events.frame[{frame}].int", positive=False)
        reader.f32(f"events.frame[{frame}].float")
        if reader.bool(f"events.frame[{frame}].has_string"):
            reader.string(f"events.frame[{frame}].string")
        if events[index].audio_path is not None:
            reader.f32(f"events.frame[{frame}].volume"); reader.f32(f"events.frame[{frame}].balance")
    output.append(Spine38Timeline("event", "event", "events", frame_count, first, last))
    return last


def _read_animation(reader: _Reader, static: Spine38StaticDocument, events: tuple[_EventDefinition, ...], name: str) -> Spine38Animation:
    timelines: list[Spine38Timeline] = []
    duration = max(
        _slot_timelines(reader, static, timelines),
        _bone_timelines(reader, static, timelines),
        _ik_timelines(reader, static, timelines),
        _transform_timelines(reader, static, timelines),
        _path_timelines(reader, static, timelines),
        _deform_timelines(reader, static, timelines),
        _draw_order(reader, static, timelines),
        _event_timeline(reader, events, timelines),
    )
    return Spine38Animation(name, duration, tuple(timelines))


def _capture_curve(reader: _Reader, label: str) -> str | tuple[tuple[float, float, float, float], ...]:
    kind = reader.byte(f"{label}.curve")
    name = CURVE_TYPES.get(kind)
    if name is None:
        raise Spine38FormatError(f"{label} curve 类型未知：{kind}")
    if name == "bezier":
        controls = tuple(reader.f32(f"{label}.curve_bezier[{index}]") for index in range(4))
        return (controls,)  # 3.8 二进制曲线段由一条曲线共同作用于该帧的各连续值。
    return name


def _capture_pose_slot_tracks(reader: _Reader, static: Spine38StaticDocument, tracks: list[PoseTrack], summaries: list[Spine38Timeline]) -> float:
    duration = 0.0
    for group_index in range(_count(reader, "animation.slot_groups")):
        slot_index = reader.varint(f"animation.slot_groups[{group_index}].slot")
        if not 0 <= slot_index < len(static.slots):
            raise Spine38FormatError(f"slot timeline 引用越界：{slot_index}/{len(static.slots)}")
        target = static.slots[slot_index].name
        for timeline_index in range(_count(reader, f"slot[{target}].timelines")):
            kind_id = reader.byte(f"slot[{target}].timeline[{timeline_index}].type")
            kind = SLOT_TYPES.get(kind_id)
            if kind is None:
                raise Spine38FormatError(f"slot[{target}] timeline 类型未知：{kind_id}")
            count = _count(reader, f"slot[{target}].timeline[{timeline_index}].frame_count")
            if count == 0:
                raise Spine38FormatError(f"slot[{target}] timeline 帧数为零")
            frames: list[PoseFrame] = []
            first = last = 0.0
            for frame in range(count):
                time = _frame_time(reader, f"slot[{target}].{kind}[{frame}].time", last if frame else None)
                if frame == 0:
                    first = time
                last = time
                if kind == "attachment":
                    values: tuple[float | str | None, ...] = (reader.ref_string(static.shared_strings, f"slot[{target}].attachment[{frame}].name"),)
                elif kind == "color":
                    values = unpack_rgba(reader.int32(f"slot[{target}].color[{frame}].rgba"))
                else:
                    light = unpack_rgba(reader.int32(f"slot[{target}].two_color[{frame}].rgba"))
                    dark = unpack_rgba(reader.int32(f"slot[{target}].two_color[{frame}].dark"))[:3]
                    values = light + dark
                curve = _capture_curve(reader, f"slot[{target}].{kind}[{frame}]") if kind != "attachment" and frame < count - 1 else None
                frames.append(PoseFrame(time, values, curve))
            tracks.append(PoseTrack("slot", kind, slot_index, target, tuple(frames)))
            summaries.append(Spine38Timeline("slot", kind, target, count, first, last))
            duration = max(duration, last)
    return duration


def _capture_pose_bone_tracks(reader: _Reader, static: Spine38StaticDocument, tracks: list[PoseTrack], summaries: list[Spine38Timeline]) -> float:
    duration = 0.0
    for group_index in range(_count(reader, "animation.bone_groups")):
        bone_index = reader.varint(f"animation.bone_groups[{group_index}].bone")
        if not 0 <= bone_index < len(static.bones):
            raise Spine38FormatError(f"bone timeline 引用越界：{bone_index}/{len(static.bones)}")
        target = static.bones[bone_index].name
        for timeline_index in range(_count(reader, f"bone[{target}].timelines")):
            kind_id = reader.byte(f"bone[{target}].timeline[{timeline_index}].type")
            kind = BONE_TYPES.get(kind_id)
            if kind is None:
                raise Spine38FormatError(f"bone[{target}] timeline 类型未知：{kind_id}")
            count = _count(reader, f"bone[{target}].timeline[{timeline_index}].frame_count")
            if count == 0:
                raise Spine38FormatError(f"bone[{target}] timeline 帧数为零")
            frames: list[PoseFrame] = []
            first = last = 0.0
            for frame in range(count):
                time = _frame_time(reader, f"bone[{target}].{kind}[{frame}].time", last if frame else None)
                if frame == 0:
                    first = time
                last = time
                values = (reader.f32(f"bone[{target}].{kind}[{frame}].value[0]"),) if kind == "rotate" else (reader.f32(f"bone[{target}].{kind}[{frame}].value[0]"), reader.f32(f"bone[{target}].{kind}[{frame}].value[1]"))
                curve = _capture_curve(reader, f"bone[{target}].{kind}[{frame}]") if frame < count - 1 else None
                frames.append(PoseFrame(time, values, curve))
            tracks.append(PoseTrack("bone", kind, bone_index, target, tuple(frames)))
            summaries.append(Spine38Timeline("bone", kind, target, count, first, last))
            duration = max(duration, last)
    return duration


def _capture_pose_ik_tracks(reader: _Reader, static: Spine38StaticDocument, tracks: list[PoseTrack], summaries: list[Spine38Timeline]) -> float:
    duration = 0.0
    for group in range(_count(reader, "animation.ik_groups")):
        target = reader.varint(f"animation.ik[{group}].constraint")
        if not 0 <= target < static.ik_constraint_count:
            raise Spine38FormatError(f"ik timeline 引用越界：{target}/{static.ik_constraint_count}")
        count = _count(reader, f"animation.ik[{target}].frame_count")
        if count == 0:
            raise Spine38FormatError("ik timeline 帧数为零")
        mix_frames: list[PoseFrame] = []
        state_frames: list[PoseFrame] = []
        first = last = 0.0
        for frame in range(count):
            time = _frame_time(reader, f"ik[{target}].frame[{frame}].time", last if frame else None)
            if frame == 0:
                first = time
            last = time
            mix = reader.f32(f"ik[{target}].frame[{frame}].mix")
            softness = reader.f32(f"ik[{target}].frame[{frame}].softness")
            raw_bend = reader.byte(f"ik[{target}].frame[{frame}].bend")
            bend = raw_bend - 256 if raw_bend > 127 else raw_bend
            compress = int(reader.bool(f"ik[{target}].frame[{frame}].compress"))
            stretch = int(reader.bool(f"ik[{target}].frame[{frame}].stretch"))
            curve = _capture_curve(reader, f"ik[{target}].frame[{frame}]") if frame < count - 1 else None
            mix_frames.append(PoseFrame(time, (mix, softness), curve))
            state_frames.append(PoseFrame(time, (bend, compress, stretch)))
        name = static.ik_constraints[target].name
        tracks.append(PoseTrack("ik", "mix", target, name, tuple(mix_frames)))
        tracks.append(PoseTrack("ik", "state", target, name, tuple(state_frames)))
        summaries.append(Spine38Timeline("ik", "mix", name, count, first, last))
        duration = max(duration, last)
    return duration


def _capture_pose_transform_tracks(reader: _Reader, static: Spine38StaticDocument, tracks: list[PoseTrack], summaries: list[Spine38Timeline]) -> float:
    duration = 0.0
    for group in range(_count(reader, "animation.transform_groups")):
        target = reader.varint(f"animation.transform[{group}].constraint")
        if not 0 <= target < static.transform_constraint_count:
            raise Spine38FormatError(f"transform timeline 引用越界：{target}/{static.transform_constraint_count}")
        count = _count(reader, f"transform[{target}].frame_count")
        if count == 0:
            raise Spine38FormatError("transform timeline 帧数为零")
        frames: list[PoseFrame] = []
        first = last = 0.0
        for frame in range(count):
            time = _frame_time(reader, f"transform[{target}].frame[{frame}].time", last if frame else None)
            if frame == 0:
                first = time
            last = time
            values = tuple(reader.f32(f"transform[{target}].frame[{frame}].mix[{item}]") for item in range(4))
            curve = _capture_curve(reader, f"transform[{target}].frame[{frame}]") if frame < count - 1 else None
            frames.append(PoseFrame(time, values, curve))
        name = static.transform_constraints[target].name
        tracks.append(PoseTrack("transform", "mix", target, name, tuple(frames)))
        summaries.append(Spine38Timeline("transform", "mix", name, count, first, last))
        duration = max(duration, last)
    return duration


def parse_spine38_pose_animation(path: Path, animation_name: str) -> tuple[Spine38StaticDocument, PoseAnimation]:
    """严格重读单个 animation 的可视化子集；文件其他段仍必须完整消费。"""
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
    selected_summary: list[Spine38Timeline] | None = None
    duration = 0.0
    for index in range(_count(reader, "animations.count")):
        name = reader.string(f"animations[{index}].name")
        if not name:
            raise Spine38FormatError(f"animations[{index}].name 为空")
        if name != animation_name:
            _read_animation(reader, static, tuple(events), name)
            continue
        summaries: list[Spine38Timeline] = []
        duration = max(_capture_pose_slot_tracks(reader, static, tracks, summaries), _capture_pose_bone_tracks(reader, static, tracks, summaries), _capture_pose_ik_tracks(reader, static, tracks, summaries), _capture_pose_transform_tracks(reader, static, tracks, summaries), _path_timelines(reader, static, summaries), _deform_timelines(reader, static, summaries, deform_evidence), _capture_pose_draw_order(reader, static, tracks, summaries), _event_timeline(reader, tuple(events), summaries))
        selected_summary = summaries
    if reader.offset != len(data):
        raise Spine38FormatError(f"animations 段未完整消费：offset={reader.offset} total={len(data)}")
    if selected_summary is None:
        raise Spine38FormatError(f"未找到动画根：{animation_name}")
    supported = {"bone:rotate", "bone:translate", "bone:scale", "bone:shear", "slot:attachment", "slot:color", "slot:two_color", "draw_order:order", "ik:mix", "transform:mix"}
    unsupported = tuple(sorted({f"{item.group}:{item.kind}" for item in selected_summary if f"{item.group}:{item.kind}" not in supported}))
    return static, PoseAnimation(animation_name, duration, tuple(tracks), unsupported, tuple(deform_evidence))


def parse_spine38_animations(path: Path) -> Spine38AnimationArchive:
    static = parse_file(path)
    data = path.read_bytes()
    reader = _Reader(data)
    reader.offset = static.static_end
    events: list[_EventDefinition] = []
    for index in range(_count(reader, "events.count")):
        name = reader.ref_string(static.shared_strings, f"events[{index}].name")
        reader.varint(f"events[{index}].int", positive=False)
        reader.f32(f"events[{index}].float")
        reader.string(f"events[{index}].string")
        audio = reader.string(f"events[{index}].audio")
        if audio is not None:
            reader.f32(f"events[{index}].volume"); reader.f32(f"events[{index}].balance")
        events.append(_EventDefinition(name, audio))
    animation_count = _count(reader, "animations.count")
    animation_start = reader.offset
    animations = []
    for index in range(animation_count):
        name = reader.string(f"animations[{index}].name")
        if not name:
            raise Spine38FormatError(f"animations[{index}].name 为空")
        animations.append(_read_animation(reader, static, tuple(events), name))
    if reader.offset != len(data):
        raise Spine38FormatError(f"animations 段未完整消费：offset={reader.offset} total={len(data)} remaining={len(data) - reader.offset}")
    return Spine38AnimationArchive(static, tuple(item.name for item in events), tuple(animations), animation_start, reader.offset)
