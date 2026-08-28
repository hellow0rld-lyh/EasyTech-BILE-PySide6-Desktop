from __future__ import annotations

from dataclasses import dataclass

from .spine_pose import CurveData, PoseAnimation


_TWO_COLOR_COMPONENTS = {"two_color": 7, "rgba2": 7, "rgb2": 6}


@dataclass(frozen=True)
class TwoColorFrameEvidence:
    time: float
    light_components: tuple[float, ...]
    dark_rgb: tuple[float, float, float]
    curve: CurveData


@dataclass(frozen=True)
class TwoColorTimelineEvidence:
    spine_version: str
    animation: str
    slot_index: int
    slot_name: str
    kind: str
    frames: tuple[TwoColorFrameEvidence, ...]
    pixel_application_state: str = "forbidden"
    rendering_state: str = "forbidden"
    writeback: str = "forbidden"


def collect_two_color_timeline_evidence(spine_version: str, animation: PoseAnimation) -> tuple[TwoColorTimelineEvidence, ...]:
    """将已读取的 slot two-color tracks 提升为证据；不计算像素或生成预览。"""
    evidence: list[TwoColorTimelineEvidence] = []
    for track in animation.tracks:
        expected = _TWO_COLOR_COMPONENTS.get(track.kind) if track.group == "slot" else None
        if expected is None:
            continue
        frames: list[TwoColorFrameEvidence] = []
        for frame in track.frames:
            values = frame.values
            if len(values) != expected or not all(isinstance(value, float) for value in values):
                raise ValueError(f"two-color track {track.kind} 的 raw 通道数量或类型无效")
            components = tuple(float(value) for value in values)
            light_count = 4 if track.kind in {"two_color", "rgba2"} else 3
            dark = tuple(components[light_count:])
            if len(dark) != 3:
                raise ValueError(f"two-color track {track.kind} 的 dark RGB 通道无效")
            frames.append(TwoColorFrameEvidence(frame.time, components[:light_count], dark, frame.curve))
        evidence.append(TwoColorTimelineEvidence(spine_version, animation.name, track.target_index, track.target_name, track.kind, tuple(frames)))
    return tuple(evidence)
