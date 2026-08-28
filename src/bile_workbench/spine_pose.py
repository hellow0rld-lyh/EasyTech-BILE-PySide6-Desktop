"""Spine 只读 pose 投影核心。

本模块不模拟完整 Spine runtime，也不写回 BIN。它只对已捕获的 bone/slot
关键帧执行单动画、alpha=1、MixBlend.setup 的局部 pose 投影，并将任何未执行
constraint、bezier、mesh/deform、draw-order 或 sequence 特性显式标为降级。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Protocol

from .spine38_format import Spine38Bone, Spine38RegionAttachment, Spine38Slot, SpineIkConstraint, SpineMeshAttachment, SpineTransformConstraint
from .spine_mesh_pose import MeshPose, project_unweighted_mesh, project_weighted_mesh_setup
from .spine_ik_solver import solve_one_bone_ik, solve_two_bone_ik
from .spine_transform_solver import apply_absolute_world_transform
from .spine_deform_evidence import DeformTimelineEvidence


CurveControls = tuple[float, float, float, float]
CurveData = str | tuple[CurveControls, ...] | None
Color = tuple[float, float, float, float]


def unpack_rgba(value: int) -> Color:
    """按 Spine binary 的高位 R、低位 A 解包 32-bit color。"""
    packed = value & 0xFFFFFFFF
    return (
        ((packed >> 24) & 0xFF) / 255.0,
        ((packed >> 16) & 0xFF) / 255.0,
        ((packed >> 8) & 0xFF) / 255.0,
        (packed & 0xFF) / 255.0,
    )


def multiply_rgba(left: Color, right: Color) -> Color:
    return tuple(component_left * component_right for component_left, component_right in zip(left, right))  # type: ignore[return-value]


@dataclass(frozen=True)
class PoseFrame:
    time: float
    values: tuple[float | str | int | None, ...]
    curve: CurveData = None


@dataclass(frozen=True)
class PoseTrack:
    group: str
    kind: str
    target_index: int
    target_name: str
    frames: tuple[PoseFrame, ...]


@dataclass(frozen=True)
class PoseAnimation:
    name: str
    duration: float
    tracks: tuple[PoseTrack, ...]
    unsupported_timeline_kinds: tuple[str, ...]
    deform_evidence: tuple[DeformTimelineEvidence, ...] = ()


class _StaticDocument(Protocol):
    bones: tuple[Spine38Bone, ...]
    slots: tuple[Spine38Slot, ...]
    region_attachments: tuple[Spine38RegionAttachment, ...]
    mesh_attachments: tuple[SpineMeshAttachment, ...]


@dataclass(frozen=True)
class BoneWorld:
    index: int
    name: str
    x: float
    y: float
    rotation: float
    scale_x: float
    scale_y: float
    shear_x: float
    shear_y: float
    a: float
    b: float
    c: float
    d: float
    world_x: float
    world_y: float


@dataclass(frozen=True)
class PoseLayer:
    slot_index: int
    slot_name: str
    attachment_name: str
    attachment_path: str
    bone_index: int
    world: BoneWorld
    attachment: Spine38RegionAttachment
    rgba: Color
    dark_rgb: tuple[float, float, float] | None
    blend_mode: int


@dataclass(frozen=True)
class MeshPoseLayer:
    slot_index: int
    slot_name: str
    attachment_name: str
    attachment_path: str
    bone_index: int
    world: BoneWorld
    attachment: SpineMeshAttachment
    mesh: MeshPose
    rgba: Color
    dark_rgb: tuple[float, float, float] | None
    blend_mode: int


@dataclass(frozen=True)
class PoseProjection:
    animation_name: str
    requested_time: float
    effective_time: float
    duration: float
    bones: tuple[BoneWorld, ...]
    layers: tuple[PoseLayer, ...]
    mesh_layers: tuple[MeshPoseLayer, ...]
    coverage_complete: bool
    diagnostics: tuple[str, ...]


def _cubic_component(value: float, control1: float, control2: float, target: float) -> float:
    inverse = 1.0 - target
    return inverse * inverse * inverse * value + 3.0 * inverse * inverse * target * control1 + 3.0 * inverse * target * target * control2 + target * target * target


def _bezier_percent(time_percent: float, controls: CurveControls) -> float:
    """在归一化时间轴反解 cubic Bezier 的 y；与 Spine 曲线的 time/value 控制点语义一致。"""
    cx1, cy1, cx2, cy2 = controls
    lower = 0.0
    upper = 1.0
    for _ in range(18):
        parameter = (lower + upper) * 0.5
        x = _cubic_component(0.0, cx1, cx2, parameter)
        if x < time_percent:
            lower = parameter
        else:
            upper = parameter
    parameter = (lower + upper) * 0.5
    return _cubic_component(0.0, cy1, cy2, parameter)


def _interpolate(track: PoseTrack, time: float, diagnostics: list[str]) -> tuple[float | str | None, ...] | None:
    frames = track.frames
    if not frames or time < frames[0].time:
        return None
    before = frames[0]
    after: PoseFrame | None = None
    for candidate in frames[1:]:
        if candidate.time > time:
            after = candidate
            break
        before = candidate
    if after is None or after.time == before.time:
        return before.values
    if any(not isinstance(value, float) for value in before.values + after.values):
        return before.values
    if before.curve == "stepped":
        return before.values
    ratio = (time - before.time) / (after.time - before.time)
    if isinstance(before.curve, tuple):
        controls = before.curve
        if not controls:
            diagnostics.append(f"{track.group}:{track.kind}:{track.target_name} 的 bezier 控制点为空；预览回退线性插值。")
        else:
            return tuple(
                float(left) + (float(right) - float(left)) * _bezier_percent(ratio, controls[min(index, len(controls) - 1)])
                for index, (left, right) in enumerate(zip(before.values, after.values))
            )
    elif before.curve == "bezier":
        diagnostics.append(f"{track.group}:{track.kind}:{track.target_name} 在 {before.time:.3f}s 标记为 bezier，但控制点未捕获；预览回退线性插值。")
    return tuple(float(left) + (float(right) - float(left)) * ratio for left, right in zip(before.values, after.values))


def _matrix_for_bone(bone: Spine38Bone, local: dict[str, float], parent: BoneWorld | None, diagnostics: list[str]) -> BoneWorld:
    rotation = local["rotation"]
    scale_x = local["scale_x"]
    scale_y = local["scale_y"]
    shear_x = local["shear_x"]
    shear_y = local["shear_y"]
    x = local["x"]
    y = local["y"]
    rotation_y = math.radians(rotation + 90.0 + shear_y)
    rotation_x = math.radians(rotation + shear_x)
    la = math.cos(rotation_x) * scale_x
    lb = math.cos(rotation_y) * scale_y
    lc = math.sin(rotation_x) * scale_x
    ld = math.sin(rotation_y) * scale_y
    if parent is None:
        return BoneWorld(bone.index, bone.name, x, y, rotation, scale_x, scale_y, shear_x, shear_y, la, lb, lc, ld, x, y)
    world_x = parent.a * x + parent.b * y + parent.world_x
    world_y = parent.c * x + parent.d * y + parent.world_y
    if bone.transform_mode == 0:  # normal
        a = parent.a * la + parent.b * lc
        b = parent.a * lb + parent.b * ld
        c = parent.c * la + parent.d * lc
        d = parent.c * lb + parent.d * ld
    elif bone.transform_mode == 1:  # onlyTranslation
        a, b, c, d = la, lb, lc, ld
    else:
        # 非 normal 的世界矩阵需要完整父矩阵规约，与 constraint 顺序共同决定语义。
        # 不伪造完全运行时结果：保留 normal 投影但要求 diagnostics 明示它是部分覆盖。
        diagnostics.append(f"骨骼 {bone.name} 使用 transform_mode={bone.transform_mode}；当前采用 normal matrix 近似，预览非完整。")
        a = parent.a * la + parent.b * lc
        b = parent.a * lb + parent.b * ld
        c = parent.c * la + parent.d * lc
        d = parent.c * lb + parent.d * ld
    return BoneWorld(bone.index, bone.name, x, y, rotation, scale_x, scale_y, shear_x, shear_y, a, b, c, d, world_x, world_y)


def _is_descendant(static: _StaticDocument, candidate: int, ancestor: int) -> bool:
    parent = static.bones[candidate].parent_index
    while parent is not None:
        if parent == ancestor:
            return True
        parent = static.bones[parent].parent_index
    return False


def _refresh_descendants(static: _StaticDocument, locals_by_index: dict[int, dict[str, float]], worlds: list[BoneWorld], ancestor: int, protected: set[int], diagnostics: list[str]) -> None:
    for bone in static.bones[ancestor + 1:]:
        if bone.index not in protected and _is_descendant(static, bone.index, ancestor):
            parent = worlds[bone.parent_index] if bone.parent_index is not None else None
            worlds[bone.index] = _matrix_for_bone(bone, locals_by_index[bone.index], parent, diagnostics)


def _apply_setup_constraint_subset(
    static: _StaticDocument,
    locals_by_index: dict[int, dict[str, float]],
    worlds: list[BoneWorld],
    diagnostics: list[str],
    ik_values: Mapping[int, tuple[float, float, int, bool, bool]] | None = None,
    transform_values: Mapping[int, tuple[float, ...]] | None = None,
) -> None:
    ik_constraints = tuple(getattr(static, "ik_constraints", ()))
    transform_constraints = tuple(getattr(static, "transform_constraints", ()))
    ordered = sorted(
        [(item.order, "ik", item) for item in ik_constraints] + [(item.order, "transform", item) for item in transform_constraints],
        key=lambda item: (item[0], item[1], item[2].index),
    )
    for _order, kind, constraint in ordered:
        if constraint.skin_required:
            diagnostics.append(f"{kind} constraint {constraint.name} 需要 skin activation；当前只读 pose 保留 setup world matrix。")
            continue
        touched = (constraint.target,) + constraint.bones
        if any(static.bones[index].transform_mode != 0 for index in touched):
            diagnostics.append(f"{kind} constraint {constraint.name} 引用非 normal transform bone；当前只读子集不执行。")
            continue
        if kind == "ik":
            ik: SpineIkConstraint = constraint
            mix, softness, bend_direction, compress, stretch = (ik_values or {}).get(ik.index, (ik.mix, ik.softness, ik.bend_direction, ik.compress, ik.stretch))
            if softness != 0:
                diagnostics.append(f"IK constraint {ik.name} 使用 softness={softness:g}；当前只读子集不执行。")
                continue
            target = worlds[ik.target]
            if len(ik.bones) == 1:
                index = ik.bones[0]
                solved, warning = solve_one_bone_ik(worlds[index], target.world_x, target.world_y, mix=mix, bone_length=static.bones[index].length, compress=compress, stretch=stretch, uniform=ik.uniform)
                worlds[index] = solved
                _refresh_descendants(static, locals_by_index, worlds, index, {index}, diagnostics)
                if warning:
                    diagnostics.append(f"IK constraint {ik.name}: {warning}")
            elif len(ik.bones) == 2:
                parent_index, child_index = ik.bones
                if static.bones[child_index].parent_index != parent_index:
                    diagnostics.append(f"IK constraint {ik.name} 不是直接父子链；当前只读子集不执行。")
                    continue
                solved, warning = solve_two_bone_ik(worlds[parent_index], worlds[child_index], target.world_x, target.world_y, parent_length=static.bones[parent_index].length, child_length=static.bones[child_index].length, bend_direction=bend_direction, mix=mix, stretch=stretch)
                worlds[parent_index], worlds[child_index] = solved
                _refresh_descendants(static, locals_by_index, worlds, parent_index, {parent_index, child_index}, diagnostics)
                _refresh_descendants(static, locals_by_index, worlds, child_index, {child_index}, diagnostics)
            else:
                diagnostics.append(f"IK constraint {ik.name} 约束 {len(ik.bones)} 根骨骼；当前只读子集不执行。")
        else:
            transform: SpineTransformConstraint = constraint
            if transform.local or transform.relative:
                diagnostics.append(f"transform constraint {transform.name} 使用 local/relative；当前仅执行 absolute-world 子集。")
                continue
            values = (transform_values or {}).get(transform.index, (transform.mix_rotate, transform.mix_x, transform.mix_y, transform.mix_scale_x, transform.mix_scale_y, transform.mix_shear_y))
            if len(values) == 4:  # Spine 3.8: rotate, translate, scale, shear.
                values = (values[0], values[1], values[1], values[2], values[2], values[3])
            if len(values) != 6:
                diagnostics.append(f"transform constraint {transform.name} 的动画 mix 分量数无效；保留 setup mix。")
                values = (transform.mix_rotate, transform.mix_x, transform.mix_y, transform.mix_scale_x, transform.mix_scale_y, transform.mix_shear_y)
            target = worlds[transform.target]
            for index in transform.bones:
                worlds[index] = apply_absolute_world_transform(worlds[index], target, offset_rotation=transform.offset_rotation, offset_x=transform.offset_x, offset_y=transform.offset_y, offset_scale_x=transform.offset_scale_x, offset_scale_y=transform.offset_scale_y, offset_shear_y=transform.offset_shear_y, mix_rotate=values[0], mix_x=values[1], mix_y=values[2], mix_scale_x=values[3], mix_scale_y=values[4], mix_shear_y=values[5])
                _refresh_descendants(static, locals_by_index, worlds, index, {index}, diagnostics)


def project_pose(
    static: _StaticDocument,
    animation: PoseAnimation,
    time: float,
    *,
    bone_deltas: Mapping[int, Mapping[str, float]] | None = None,
    attachment_overrides: Mapping[int, str | None] | None = None,
) -> PoseProjection:
    """投影单动画单层、setup blend、无 constraint 的只读 pose。

    ``bone_deltas`` 与 ``attachment_overrides`` 仅用于可逆的内存审阅提案。
    它们从不序列化回 Spine BIN，且会使结果显式标记为非完整 runtime pose。
    """
    diagnostics: list[str] = []
    duration = max(0.0, animation.duration)
    effective = min(max(0.0, time), duration)
    locals_by_index: dict[int, dict[str, float]] = {
        bone.index: {
            "rotation": bone.rotation,
            "x": bone.x,
            "y": bone.y,
            "scale_x": bone.scale_x,
            "scale_y": bone.scale_y,
            "shear_x": bone.shear_x,
            "shear_y": bone.shear_y,
        }
        for bone in static.bones
    }
    slot_attachment: dict[int, str | None] = {slot.index: slot.setup_attachment for slot in static.slots}
    draw_order = list(range(len(static.slots)))
    slot_rgba: dict[int, Color] = {slot.index: unpack_rgba(slot.rgba) for slot in static.slots}
    ik_animation_values: dict[int, tuple[float, float, int, bool, bool]] = {}
    transform_animation_values: dict[int, tuple[float, ...]] = {}
    ik_state_values: dict[int, tuple[int, bool, bool]] = {}
    slot_dark: dict[int, tuple[float, float, float] | None] = {
        slot.index: (unpack_rgba(slot.dark_rgb)[:3] if slot.dark_rgb is not None else None)
        for slot in static.slots
    }
    for track in animation.tracks:
        values = _interpolate(track, effective, diagnostics)
        if values is None:
            continue
        if track.group == "bone":
            local = locals_by_index[track.target_index]
            if track.kind == "rotate" and isinstance(values[0], float):
                local["rotation"] = static.bones[track.target_index].rotation + values[0]
            elif track.kind == "translate" and len(values) == 2 and all(isinstance(item, float) for item in values):
                local["x"] = static.bones[track.target_index].x + float(values[0])
                local["y"] = static.bones[track.target_index].y + float(values[1])
            elif track.kind == "scale" and len(values) == 2 and all(isinstance(item, float) for item in values):
                local["scale_x"] = static.bones[track.target_index].scale_x * float(values[0])
                local["scale_y"] = static.bones[track.target_index].scale_y * float(values[1])
            elif track.kind == "shear" and len(values) == 2 and all(isinstance(item, float) for item in values):
                local["shear_x"] = static.bones[track.target_index].shear_x + float(values[0])
                local["shear_y"] = static.bones[track.target_index].shear_y + float(values[1])
        elif track.group == "slot":
            if track.kind == "attachment":
                slot_attachment[track.target_index] = values[0] if values else None
            elif track.kind == "color" and len(values) == 4 and all(isinstance(value, float) for value in values):
                slot_rgba[track.target_index] = tuple(float(value) for value in values)  # type: ignore[assignment]
            elif track.kind == "two_color" and len(values) == 7 and all(isinstance(value, float) for value in values):
                slot_rgba[track.target_index] = tuple(float(value) for value in values[:4])  # type: ignore[assignment]
                slot_dark[track.target_index] = tuple(float(value) for value in values[4:7])  # type: ignore[assignment]
            elif track.kind == "rgba" and len(values) == 4 and all(isinstance(value, float) for value in values):
                slot_rgba[track.target_index] = tuple(float(value) for value in values)  # type: ignore[assignment]
            elif track.kind == "rgb" and len(values) == 3 and all(isinstance(value, float) for value in values):
                prior = slot_rgba[track.target_index]
                slot_rgba[track.target_index] = (float(values[0]), float(values[1]), float(values[2]), prior[3])
            elif track.kind == "alpha" and len(values) == 1 and isinstance(values[0], float):
                prior = slot_rgba[track.target_index]
                slot_rgba[track.target_index] = (prior[0], prior[1], prior[2], float(values[0]))
            elif track.kind == "rgba2" and len(values) == 7 and all(isinstance(value, float) for value in values):
                slot_rgba[track.target_index] = tuple(float(value) for value in values[:4])  # type: ignore[assignment]
                slot_dark[track.target_index] = tuple(float(value) for value in values[4:7])  # type: ignore[assignment]
            elif track.kind == "rgb2" and len(values) == 6 and all(isinstance(value, float) for value in values):
                prior = slot_rgba[track.target_index]
                slot_rgba[track.target_index] = (float(values[0]), float(values[1]), float(values[2]), prior[3])
                slot_dark[track.target_index] = tuple(float(value) for value in values[3:6])  # type: ignore[assignment]
        elif track.group == "ik":
            if track.kind == "mix" and len(values) == 2 and all(isinstance(value, float) for value in values):
                prior = ik_animation_values.get(track.target_index)
                state = ik_state_values.get(track.target_index, (0, False, False))
                ik_animation_values[track.target_index] = (float(values[0]), float(values[1]), state[0], state[1], state[2])
            elif track.kind == "state" and len(values) == 3 and all(isinstance(value, int) for value in values):
                ik_state_values[track.target_index] = (int(values[0]), bool(values[1]), bool(values[2]))
                prior = ik_animation_values.get(track.target_index)
                if prior is not None:
                    ik_animation_values[track.target_index] = (prior[0], prior[1], int(values[0]), bool(values[1]), bool(values[2]))
        elif track.group == "transform" and track.kind == "mix" and all(isinstance(value, float) for value in values):
            transform_animation_values[track.target_index] = tuple(float(value) for value in values)
        elif track.group == "draw_order" and track.kind == "order":
            if len(values) != len(static.slots) or not all(isinstance(value, int) for value in values):
                diagnostics.append("draw_order timeline 的 slot 重排数据无效；保留 setup order。")
            elif sorted(int(value) for value in values) != list(range(len(static.slots))):
                diagnostics.append("draw_order timeline 不是 slot 索引排列；保留 setup order。")
            else:
                draw_order = [int(value) for value in values]
    if bone_deltas:
        for bone_index, delta in bone_deltas.items():
            local = locals_by_index.get(bone_index)
            if local is None:
                diagnostics.append(f"AI Motion DSL 请求不存在的 bone index {bone_index}；已忽略。")
                continue
            for field in ("x", "y", "rotation", "scale_x", "scale_y", "shear_x", "shear_y"):
                amount = delta.get(field)
                if amount is not None:
                    local[field] += amount
            diagnostics.append(f"AI Motion DSL 内存覆盖：bone {static.bones[bone_index].name}；不代表 Spine runtime 或 BIN 写回。")
    if attachment_overrides:
        for slot_index, attachment_name in attachment_overrides.items():
            if slot_index not in slot_attachment:
                diagnostics.append(f"AI Motion DSL 请求不存在的 slot index {slot_index}；已忽略。")
                continue
            slot_attachment[slot_index] = attachment_name
            diagnostics.append(f"AI Motion DSL 内存覆盖：slot {static.slots[slot_index].name} attachment；不代表 Spine runtime 或 BIN 写回。")
    worlds: list[BoneWorld] = []
    for bone in static.bones:
        parent = worlds[bone.parent_index] if bone.parent_index is not None else None
        worlds.append(_matrix_for_bone(bone, locals_by_index[bone.index], parent, diagnostics))
    _apply_setup_constraint_subset(static, locals_by_index, worlds, diagnostics, ik_animation_values, transform_animation_values)
    attachment_index: dict[tuple[int, str], Spine38RegionAttachment] = {}
    fallback_index: dict[tuple[int, str], list[Spine38RegionAttachment]] = {}
    mesh_index: dict[tuple[int, str], SpineMeshAttachment] = {}
    mesh_fallback: dict[tuple[int, str], list[SpineMeshAttachment]] = {}
    for attachment in static.region_attachments:
        key = (attachment.slot_index, attachment.name)
        fallback_index.setdefault(key, []).append(attachment)
        if attachment.skin == "default":
            attachment_index.setdefault(key, attachment)
    for attachment in getattr(static, "mesh_attachments", ()):
        key = (attachment.slot_index, attachment.name)
        mesh_fallback.setdefault(key, []).append(attachment)
        if attachment.skin == "default":
            mesh_index.setdefault(key, attachment)
    layers: list[PoseLayer] = []
    mesh_layers: list[MeshPoseLayer] = []
    for slot_index in draw_order:
        slot = static.slots[slot_index]
        attachment_name = slot_attachment.get(slot.index)
        if not attachment_name:
            continue
        key = (slot.index, attachment_name)
        mesh_attachment = mesh_index.get(key)
        if mesh_attachment is None:
            candidates = mesh_fallback.get(key, [])
            if len(candidates) == 1:
                mesh_attachment = candidates[0]
        if mesh_attachment is not None:
            mesh, warning = (project_unweighted_mesh(mesh_attachment, worlds[slot.bone_index]) if mesh_attachment.vertices is not None else project_weighted_mesh_setup(mesh_attachment, worlds))
            if warning:
                diagnostics.append(warning)
                continue
            assert mesh is not None
            rgba = multiply_rgba(slot_rgba[slot.index], unpack_rgba(mesh_attachment.rgba))
            dark = slot_dark[slot.index]
            if dark is not None:
                diagnostics.append(f"slot {slot.name} 使用 dark/two-color tint；renderer 仅在已验证 straight-alpha normal blend 输入时执行受限合成，其余情况显式降级。")
            if slot.blend_mode != 0:
                diagnostics.append(f"slot {slot.name} 使用 blend_mode={slot.blend_mode}；当前 mesh renderer 采用 normal alpha composite，预览非完整。")
            mesh_layers.append(MeshPoseLayer(slot.index, slot.name, mesh_attachment.name, mesh_attachment.path, slot.bone_index, worlds[slot.bone_index], mesh_attachment, mesh, rgba, dark, slot.blend_mode))
            continue
        attachment = attachment_index.get(key)
        if attachment is None:
            candidates = fallback_index.get(key, [])
            if len(candidates) == 1:
                attachment = candidates[0]
                diagnostics.append(f"slot {slot.name} 的 attachment {attachment_name!r} 仅在 skin {attachment.skin!r} 中找到；采用唯一静态回退。")
            else:
                diagnostics.append(f"slot {slot.name} 的 attachment {attachment_name!r} 没有唯一 region 映射；当前不渲染。")
                continue
        rgba = multiply_rgba(slot_rgba[slot.index], unpack_rgba(attachment.rgba))
        dark = slot_dark[slot.index]
        if dark is not None:
            diagnostics.append(f"slot {slot.name} 使用 dark/two-color tint；renderer 仅在已验证 straight-alpha normal blend 输入时执行受限合成，其余情况显式降级。")
        if slot.blend_mode != 0:
            diagnostics.append(f"slot {slot.name} 使用 blend_mode={slot.blend_mode}；当前 renderer 采用 normal alpha composite，预览非完整。")
        layers.append(PoseLayer(slot.index, slot.name, attachment.name, attachment.path, slot.bone_index, worlds[slot.bone_index], attachment, rgba, dark, slot.blend_mode))
    for kind in animation.unsupported_timeline_kinds:
        diagnostics.append(f"animation 包含未执行的 timeline：{kind}")
    complete = not diagnostics
    return PoseProjection(animation.name, time, effective, duration, tuple(worlds), tuple(layers), tuple(mesh_layers), complete, tuple(diagnostics))
