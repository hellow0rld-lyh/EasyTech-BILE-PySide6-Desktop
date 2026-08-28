"""Spine deform timeline 的只读取证契约。

此模块有意不含 deform 应用、BIN 重写或实时补帧接口。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias


BezierCurve: TypeAlias = tuple[tuple[float, float, float, float], ...]
DeformCurve: TypeAlias = Literal["linear", "stepped"] | BezierCurve


@dataclass(frozen=True)
class DeformFrameEvidence:
    time: float
    start: int | None
    values: tuple[float, ...]
    curve: DeformCurve | None = None


@dataclass(frozen=True)
class DeformTimelineEvidence:
    skin: str
    slot_index: int
    attachment_name: str | None
    frames: tuple[DeformFrameEvidence, ...]


@dataclass(frozen=True)
class SpineDeformEvidence:
    source_sha256: str
    spine_version: str
    animation_name: str
    timelines: tuple[DeformTimelineEvidence, ...]

    @property
    def frame_count(self) -> int:
        return sum(len(item.frames) for item in self.timelines)

    @property
    def value_count(self) -> int:
        return sum(len(frame.values) for item in self.timelines for frame in item.frames)
