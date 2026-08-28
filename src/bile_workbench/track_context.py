"""BILE 动画根内部的轨道上下文投影。

BILE 的时间线为离散槽位与保持帧；本模块不把它解释为可编辑曲线，也不改变任何记录。
"""
from __future__ import annotations

from dataclasses import dataclass

from .bile_format import BileDocument


class TrackContextError(ValueError):
    """请求的动画、通道、槽位或 Track 超出已解析 BILE 文档范围。"""


@dataclass(frozen=True)
class TrackContext:
    animation_index: int
    animation_name: str
    channel_index: int
    frame_slot: int
    hold_end_slot: int
    track_index: int
    keyframe_index: int
    target_element_index: int
    target_element_name: str
    target_is_sprite: bool

    @property
    def scope_label(self) -> str:
        target_kind = "精灵" if self.target_is_sprite else "子动画"
        return (
            f"{self.animation_name} / 通道 {self.channel_index + 1} / 段 {self.frame_slot}–{self.hold_end_slot} "
            f"/ Track {self.track_index + 1} / BELE[{self.keyframe_index}] / {target_kind} {self.target_element_name}"
        )


def _animation(document: BileDocument, animation_index: int):
    if not 0 <= animation_index < len(document.elements):
        raise TrackContextError(f"动画元素索引超出范围：{animation_index}")
    animation = document.elements[animation_index]
    if animation.has_texture:
        raise TrackContextError(f"元素不是动画根：{animation.name}")
    return animation


def tracks_for_animation(document: BileDocument, animation_index: int) -> tuple[TrackContext, ...]:
    """展开一个动画根的每条 Track 及其关键帧保持段。"""
    animation = _animation(document, animation_index)
    contexts: list[TrackContext] = []
    for channel_index, channel in enumerate(animation.channels):
        for frame_index, frame in enumerate(channel.frames):
            next_slot = channel.frames[frame_index + 1].slot if frame_index + 1 < len(channel.frames) else animation.frame_count
            hold_end_slot = max(frame.slot, next_slot - 1)
            for track_index, track in enumerate(frame.tracks):
                if not 0 <= track.keyframe_index < len(document.keyframes):
                    raise TrackContextError(f"Track 引用的 BELE 超出范围：{track.keyframe_index}")
                if not 0 <= track.element_index < len(document.elements):
                    raise TrackContextError(f"Track 引用的 BMTI 超出范围：{track.element_index}")
                target = document.elements[track.element_index]
                contexts.append(
                    TrackContext(
                        animation_index=animation.index,
                        animation_name=animation.name,
                        channel_index=channel_index,
                        frame_slot=frame.slot,
                        hold_end_slot=hold_end_slot,
                        track_index=track_index,
                        keyframe_index=track.keyframe_index,
                        target_element_index=target.index,
                        target_element_name=target.name,
                        target_is_sprite=target.has_texture,
                    )
                )
    return tuple(contexts)


def active_tracks_at_slot(document: BileDocument, animation_index: int, slot: int) -> tuple[TrackContext, ...]:
    """返回每个通道在当前离散槽位的活动帧中的 Track。"""
    animation = _animation(document, animation_index)
    if not 0 <= slot < animation.frame_count:
        raise TrackContextError(f"槽位超出动画范围：{slot} / 0–{max(0, animation.frame_count - 1)}")
    return tuple(context for context in tracks_for_animation(document, animation_index) if context.frame_slot <= slot <= context.hold_end_slot)


def keyframe_contexts(document: BileDocument, keyframe_index: int) -> tuple[TrackContext, ...]:
    """列出一个 BELE 在当前文档中被哪些动画轨道引用，供影响范围取证使用。"""
    if not 0 <= keyframe_index < len(document.keyframes):
        raise TrackContextError(f"BELE 索引超出范围：{keyframe_index}")
    contexts: list[TrackContext] = []
    for animation in document.animations:
        contexts.extend(context for context in tracks_for_animation(document, animation.index) if context.keyframe_index == keyframe_index)
    return tuple(contexts)
