"""Spine transform constraint 的独立只读求值子集。

当前仅实现最易核验的 absolute-world 模式。调用者应把 local 或 relative 约束保留为
显式降级，直到与 update cache 的完整 applied transform 链共同验证。
"""
from __future__ import annotations

import math
from dataclasses import replace
from typing import Any


def _normalise_radians(value: float) -> float:
    return (value + math.pi) % (2 * math.pi) - math.pi


def _clamp_mix(value: float) -> float:
    return max(0.0, min(1.0, value))


def apply_absolute_world_transform(
    bone: Any,
    target: Any,
    *,
    offset_rotation: float,
    offset_x: float,
    offset_y: float,
    offset_scale_x: float,
    offset_scale_y: float,
    offset_shear_y: float,
    mix_rotate: float,
    mix_x: float,
    mix_y: float,
    mix_scale_x: float,
    mix_scale_y: float,
    mix_shear_y: float,
) -> Any:
    """应用 absolute-world transform constraint，不修改任一输入对象。"""
    a, b, c, d = bone.a, bone.b, bone.c, bone.d
    target_angle = math.atan2(target.c, target.a)
    bone_angle = math.atan2(c, a)
    rotate = _normalise_radians(target_angle - bone_angle + math.radians(offset_rotation)) * _clamp_mix(mix_rotate)
    if rotate:
        cosine = math.cos(rotate)
        sine = math.sin(rotate)
        a, b, c, d = cosine * a - sine * c, cosine * b - sine * d, sine * a + cosine * c, sine * b + cosine * d

    target_x = target.a * offset_x + target.b * offset_y + target.world_x
    target_y = target.c * offset_x + target.d * offset_y + target.world_y
    world_x = bone.world_x + (target_x - bone.world_x) * _clamp_mix(mix_x)
    world_y = bone.world_y + (target_y - bone.world_y) * _clamp_mix(mix_y)

    scale_x = math.hypot(a, c)
    target_scale_x = math.hypot(target.a, target.c) + offset_scale_x
    if scale_x > 1e-6 and mix_scale_x:
        factor = (scale_x + (target_scale_x - scale_x) * _clamp_mix(mix_scale_x)) / scale_x
        a *= factor
        c *= factor
    scale_y = math.hypot(b, d)
    target_scale_y = math.hypot(target.b, target.d) + offset_scale_y
    if scale_y > 1e-6 and mix_scale_y:
        factor = (scale_y + (target_scale_y - scale_y) * _clamp_mix(mix_scale_y)) / scale_y
        b *= factor
        d *= factor

    if mix_shear_y:
        axis_y = math.atan2(d, b)
        shear_target = math.atan2(target.d, target.b) - math.atan2(target.c, target.a) + math.radians(offset_shear_y)
        desired = target_angle + math.pi / 2 + shear_target
        axis_y += _normalise_radians(desired - axis_y) * _clamp_mix(mix_shear_y)
        magnitude = math.hypot(b, d)
        b, d = math.cos(axis_y) * magnitude, math.sin(axis_y) * magnitude

    return replace(
        bone,
        a=a,
        b=b,
        c=c,
        d=d,
        world_x=world_x,
        world_y=world_y,
        rotation=bone.rotation + math.degrees(rotate),
    )
