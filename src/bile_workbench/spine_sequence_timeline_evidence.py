from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SequenceTimelineFrameEvidence:
    """Spine 4.1 ATTACHMENT_SEQUENCE 单个关键帧的原始只读证据。

    ``mode_and_index`` 保留 BIN 的完整 int32；其低 4 位和算术右移 4 位的
    拆分与官方 4.1 SkeletonBinary 读取路径一致。该类型只记录已消费字段，
    不解释播放模式，也不据此选择任何图像帧。
    """

    time: float
    mode_and_index: int
    mode_ordinal: int
    sequence_index: int
    delay: float


@dataclass(frozen=True)
class SequenceTimelineEvidence:
    """Spine 4.1 attachment:sequence 时间线的只读证据。

    此证据与 static sequence attachment 的 ``skin/slot/name`` 仅以解析器中
    已出现的 timeline target 字段绑定；它不是 runtime 状态，且没有任何可用
    于渲染、图像采样、帧选择或 BIN 写回的操作。
    """

    spine_version: str
    animation: str
    skin: str
    slot_index: int
    attachment_name: str | None
    frames: tuple[SequenceTimelineFrameEvidence, ...]
    attachment_key: str | None = None
    selection_state: str = "forbidden"
    rendering_state: str = "forbidden"

    @property
    def frame_count(self) -> int:
        return len(self.frames)


def unpack_sequence_mode_and_index(mode_and_index: int) -> tuple[int, int]:
    """按官方 4.1 读取路径拆分 packed int，不对值执行 runtime 解释。"""
    return mode_and_index & 0xF, mode_and_index >> 4
