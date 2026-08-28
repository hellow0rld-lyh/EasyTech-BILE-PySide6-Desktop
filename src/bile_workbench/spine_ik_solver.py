"""Spine IK 的独立只读 world-matrix 子集。

本模块不读取或写入 BIN。它仅对已求出的 normal-transform world matrix 应用可验证的
单骨与直接父子双骨几何解；softness、非均匀 parent scale 和复杂 transform mode 由调用者
保留为显式降级条件。
"""
from __future__ import annotations

import math
from dataclasses import replace
from typing import Any

_EPSILON = 1e-6


def _normalise_degrees(value: float) -> float:
    return (value + 180.0) % 360.0 - 180.0


def _rotate_world(bone: Any, degrees: float, *, scale_x: float = 1.0, scale_y: float = 1.0) -> Any:
    radians = math.radians(degrees)
    cosine = math.cos(radians)
    sine = math.sin(radians)
    return replace(
        bone,
        rotation=bone.rotation + degrees,
        scale_x=bone.scale_x * scale_x,
        scale_y=bone.scale_y * scale_y,
        a=(cosine * bone.a - sine * bone.c) * scale_x,
        b=(cosine * bone.b - sine * bone.d) * scale_y,
        c=(sine * bone.a + cosine * bone.c) * scale_x,
        d=(sine * bone.b + cosine * bone.d) * scale_y,
    )


def solve_one_bone_ik(
    bone: Any,
    target_x: float,
    target_y: float,
    *,
    mix: float,
    bone_length: float,
    compress: bool = False,
    stretch: bool = False,
    uniform: bool = False,
) -> tuple[Any, str | None]:
    """在 world space 旋转一根 normal bone 指向 target。

    返回的 matrix 可直接用于只读 region pose。若 target 与 bone base 重合，保持原矩阵并返回诊断。
    """
    dx = target_x - bone.world_x
    dy = target_y - bone.world_y
    distance = math.hypot(dx, dy)
    if distance <= _EPSILON:
        return bone, "IK target 与单骨基点重合；保持原 pose。"
    alpha = max(0.0, min(1.0, mix))
    desired = math.degrees(math.atan2(dy, dx))
    current = math.degrees(math.atan2(bone.c, bone.a))
    rotation = _normalise_degrees(desired - current) * alpha
    scale_x = scale_y = 1.0
    reach = abs(bone_length * bone.scale_x)
    if reach > _EPSILON and ((compress and distance < reach) or (stretch and distance > reach)):
        scale_x = 1.0 + (distance / reach - 1.0) * alpha
        if uniform:
            scale_y = scale_x
    return _rotate_world(bone, rotation, scale_x=scale_x, scale_y=scale_y), None


def solve_two_bone_ik(
    parent: Any,
    child: Any,
    target_x: float,
    target_y: float,
    *,
    parent_length: float,
    child_length: float,
    bend_direction: int,
    mix: float,
    stretch: bool = False,
) -> tuple[tuple[Any, Any], str | None]:
    """求直接父子、normal、近似均匀缩放双骨链的 world-space IK。

    这是刻意受限的审阅子集：调用方必须已排除 softness、非直接链和非 normal transform。
    """
    if bend_direction not in (-1, 1):
        return (parent, child), "IK bend_direction 无效；保持原 pose。"
    base_x, base_y = parent.world_x, parent.world_y
    dx, dy = target_x - base_x, target_y - base_y
    distance = math.hypot(dx, dy)
    length1 = math.hypot(child.world_x - base_x, child.world_y - base_y)
    length2 = abs(child_length * child.scale_x)
    if length1 <= _EPSILON or length2 <= _EPSILON or distance <= _EPSILON:
        return (parent, child), "双骨 IK 链长度或 target 距离退化；保持原 pose。"
    alpha = max(0.0, min(1.0, mix))
    max_reach = length1 + length2
    scale = 1.0
    if stretch and distance > max_reach:
        scale = 1.0 + (distance / max_reach - 1.0) * alpha
        length1 *= scale
        length2 *= scale
    clamped = min(max(distance, abs(length1 - length2) + _EPSILON), length1 + length2 - _EPSILON)
    cosine_child = max(-1.0, min(1.0, (clamped * clamped - length1 * length1 - length2 * length2) / (2.0 * length1 * length2)))
    child_angle = math.degrees(math.acos(cosine_child)) * bend_direction
    base_angle = math.degrees(math.atan2(dy, dx))
    offset = math.degrees(math.atan2(length2 * math.sin(math.radians(child_angle)), length1 + length2 * math.cos(math.radians(child_angle))))
    parent_target = base_angle - offset
    current_parent = math.degrees(math.atan2(parent.c, parent.a))
    rotated_parent = _rotate_world(parent, _normalise_degrees(parent_target - current_parent) * alpha, scale_x=scale, scale_y=scale)
    current_child = math.degrees(math.atan2(child.c, child.a))
    child_target = parent_target + child_angle
    rotated_child = _rotate_world(child, _normalise_degrees(child_target - current_child) * alpha, scale_x=scale, scale_y=scale)
    # child base follows the solved parent tip in this restricted direct-chain model.
    rotated_child = replace(rotated_child, world_x=base_x + math.cos(math.radians(parent_target)) * length1, world_y=base_y + math.sin(math.radians(parent_target)) * length1)
    return (rotated_parent, rotated_child), None
