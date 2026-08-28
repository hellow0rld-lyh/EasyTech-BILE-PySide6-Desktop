"""EasyTech BILE 动画容器的保守读取模型。

本模块只使用已由原包样本与公开参考实现共同验证的字段。它不依赖
Godot、游戏运行时或私有地址值，并在遇到未通过边界/引用校验的数据时失败。
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

MAGIC: Final[bytes] = b"BILE"
STANDARD_TAGS: Final[tuple[str, ...]] = ("BELE", "BXDI", "BMRF", "BYAL", "BMTI", "BRTS")
V2_TAGS: Final[tuple[str, ...]] = ("BELE", "BMRF", "BYAL", "BMTI", "BRTS")
RECORD_WIDTHS: Final[dict[str, int]] = {"BELE": 44, "BXDI": 8, "BMRF": 8, "BYAL": 8, "BMTI": 56}
V2_RECORD_WIDTHS: Final[dict[str, int]] = {"BELE": 48, "BMRF": 12, "BYAL": 8, "BMTI": 56}


class BileFormatError(ValueError):
    """BILE 文件不满足已验证的结构约束。"""


@dataclass(frozen=True)
class Header:
    version: int
    payload_size: int
    header_size: int
    section_count: int
    fps: float


@dataclass(frozen=True)
class Section:
    tag: str
    offset: int
    total_size: int
    count: int
    opaque_value: int | None
    payload_offset: int
    payload: bytes


@dataclass(frozen=True)
class Keyframe:
    """BELE 记录中已确认的 2D 仿射变换、ARGB 调制色及未解释保留字段。"""

    xx: float
    xy: float
    yx: float
    yy: float
    x: float
    y: float
    argb: int
    initial_phase: int
    playback_mode: int
    opaque_ref: int
    opaque_flags: int

    @property
    def has_known_playback_mode(self) -> bool:
        """0=循环、1=单次停止、2=手动保持；其它值保留但标记为未知。"""
        return self.playback_mode in (0, 1, 2)

    @property
    def rgba(self) -> tuple[int, int, int, int]:
        return (
            (self.argb >> 16) & 0xFF,
            (self.argb >> 8) & 0xFF,
            self.argb & 0xFF,
            (self.argb >> 24) & 0xFF,
        )


@dataclass(frozen=True)
class Track:
    keyframe_index: int
    element_index: int


@dataclass(frozen=True)
class Frame:
    slot: int
    tracks: tuple[Track, ...]


@dataclass(frozen=True)
class Channel:
    frames: tuple[Frame, ...]


@dataclass(frozen=True)
class Element:
    index: int
    name_offset: int
    name: str
    x: float
    y: float
    has_texture: bool
    frame_count: int
    channel_count: int
    opaque_14: int
    opaque_18: int
    opaque_2c: int
    opaque_30: int
    opaque_34: int
    channels: tuple[Channel, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class BileDocument:
    header: Header
    sections: dict[str, Section]
    keyframes: tuple[Keyframe, ...]
    elements: tuple[Element, ...]
    strings: dict[int, str]
    graph_cycles: tuple[tuple[int, ...], ...] = field(default_factory=tuple)

    @property
    def animations(self) -> tuple[Element, ...]:
        return tuple(element for element in self.elements if not element.has_texture)

    @property
    def sprites(self) -> tuple[Element, ...]:
        return tuple(element for element in self.elements if element.has_texture)


def _need(data: bytes, offset: int, count: int, context: str) -> None:
    if offset < 0 or count < 0 or offset + count > len(data):
        raise BileFormatError(f"{context} 越界：offset=0x{offset:X}, size={count}, file={len(data)}")


def _u16(data: bytes, offset: int, context: str) -> int:
    _need(data, offset, 2, context)
    return struct.unpack_from("<H", data, offset)[0]


def _s32(data: bytes, offset: int, context: str) -> int:
    _need(data, offset, 4, context)
    return struct.unpack_from("<i", data, offset)[0]


def _u32(data: bytes, offset: int, context: str) -> int:
    _need(data, offset, 4, context)
    return struct.unpack_from("<I", data, offset)[0]


def _f32(data: bytes, offset: int, context: str) -> float:
    _need(data, offset, 4, context)
    return struct.unpack_from("<f", data, offset)[0]


def _parse_strings(payload: bytes) -> dict[int, str]:
    strings: dict[int, str] = {}
    cursor = 0
    while cursor < len(payload):
        end = payload.find(b"\0", cursor)
        if end < 0:
            raise BileFormatError("BRTS 字符串区存在未终止 UTF-8 字符串")
        if end > cursor:
            try:
                strings[cursor] = payload[cursor:end].decode("utf-8")
            except UnicodeDecodeError as exc:
                raise BileFormatError(f"BRTS 在 0x{cursor:X} 处不是有效 UTF-8") from exc
        cursor = end + 1
    return strings


def _parse_header_and_sections(data: bytes) -> tuple[Header, dict[str, Section]]:
    _need(data, 0, 20, "BILE 文件头")
    if data[:4] != MAGIC:
        raise BileFormatError(f"魔数错误：预期 {MAGIC!r}，得到 {data[:4]!r}")
    header = Header(
        version=_u32(data, 4, "版本"),
        payload_size=_u32(data, 8, "载荷长度"),
        header_size=_u16(data, 12, "头长度"),
        section_count=_u16(data, 14, "节数量"),
        fps=_f32(data, 16, "FPS"),
    )
    if header.payload_size + header.header_size != len(data):
        raise BileFormatError("载荷长度加头长度不等于实际文件长度")
    if header.header_size != 20:
        raise BileFormatError(f"不支持的头长度：{header.header_size}")
    if header.version == 2:
        expected_tags = V2_TAGS
        record_widths = V2_RECORD_WIDTHS
    elif header.version in (3, 4):
        expected_tags = STANDARD_TAGS
        record_widths = RECORD_WIDTHS
    else:
        raise BileFormatError(f"不支持的 BILE 版本：{header.version}")
    if header.section_count != len(expected_tags):
        raise BileFormatError(f"BILE v{header.version} 的节数量应为 {len(expected_tags)}，实际为 {header.section_count}")
    cursor = header.header_size
    sections: dict[str, Section] = {}
    for expected_tag in expected_tags:
        _need(data, cursor, 12, f"{expected_tag} 块头")
        tag_bytes = data[cursor:cursor + 4]
        try:
            tag = tag_bytes.decode("ascii")
        except UnicodeDecodeError as exc:
            raise BileFormatError(f"0x{cursor:X} 的块标签非 ASCII") from exc
        if tag != expected_tag:
            raise BileFormatError(f"块顺序错误：预期 {expected_tag}，实际 {tag}")
        total_size = _u32(data, cursor + 4, f"{tag} 总长度")
        count = _u32(data, cursor + 8, f"{tag} 数量")
        header_width = 12 if tag == "BRTS" else 16
        if total_size < header_width:
            raise BileFormatError(f"{tag} 块长度小于头部长度")
        _need(data, cursor, total_size, f"{tag} 块")
        opaque_value = None if tag == "BRTS" else _u32(data, cursor + 12, f"{tag} 不透明值")
        payload_offset = cursor + header_width
        payload = data[payload_offset:cursor + total_size]
        if tag in record_widths and len(payload) != count * record_widths[tag]:
            raise BileFormatError(f"{tag} 负载长度与记录计数不一致")
        sections[tag] = Section(tag, cursor, total_size, count, opaque_value, payload_offset, payload)
        cursor += total_size
    if cursor != len(data):
        raise BileFormatError(f"顶层节之后还有 {len(data) - cursor} 个字节")
    return header, sections


def parse_bytes(data: bytes) -> BileDocument:
    """解析一个完整、受支持的 BILE v2/v3/v4 动画文件。v2 仅提供经样本验证的只读解码。"""
    header, sections = _parse_header_and_sections(data)
    strings = _parse_strings(sections["BRTS"].payload)

    bele = sections["BELE"]
    keyframes: list[Keyframe] = []
    for index in range(bele.count):
        if header.version == 2:
            offset = bele.payload_offset + index * 48
            alpha = _f32(data, offset + 24, "BILE v2 BELE.alpha")
            if not 0.0 <= alpha <= 1.0:
                raise BileFormatError(f"BILE v2 BELE[{index}] 的候选 alpha 不在 [0, 1] 范围")
            keyframes.append(
                Keyframe(
                    xx=_f32(data, offset, "BELE.xx"),
                    xy=_f32(data, offset + 4, "BELE.xy"),
                    yx=_f32(data, offset + 8, "BELE.yx"),
                    yy=_f32(data, offset + 12, "BELE.yy"),
                    x=_f32(data, offset + 16, "BELE.x"),
                    y=_f32(data, offset + 20, "BELE.y"),
                    argb=(round(alpha * 255) << 24) | 0x00FFFFFF,
                    initial_phase=0,
                    playback_mode=0,
                    opaque_ref=_u32(data, offset + 36, "BILE v2 BELE.opaque_ref"),
                    opaque_flags=_u32(data, offset + 44, "BILE v2 BELE.opaque_flags"),
                )
            )
        else:
            offset = bele.payload_offset + index * 44
            keyframes.append(
                Keyframe(
                    xx=_f32(data, offset, "BELE.xx"),
                    xy=_f32(data, offset + 4, "BELE.xy"),
                    yx=_f32(data, offset + 8, "BELE.yx"),
                    yy=_f32(data, offset + 12, "BELE.yy"),
                    x=_f32(data, offset + 16, "BELE.x"),
                    y=_f32(data, offset + 20, "BELE.y"),
                    argb=_u32(data, offset + 24, "BELE.argb"),
                    initial_phase=_u32(data, offset + 28, "BELE.initial_phase"),
                    playback_mode=_u32(data, offset + 32, "BELE.playback_mode"),
                    opaque_ref=_u32(data, offset + 36, "BELE.opaque_ref"),
                    opaque_flags=_u32(data, offset + 40, "BELE.opaque_flags"),
                )
            )

    bmti = sections["BMTI"]
    element_shells: list[Element] = []
    for index in range(bmti.count):
        offset = bmti.payload_offset + index * 56
        item_index = _u32(data, offset, "BMTI.index")
        if item_index != index:
            raise BileFormatError(f"BMTI[{index}] 的自索引为 {item_index}")
        name_offset = _u32(data, offset + 4, "BMTI.name_offset")
        if name_offset not in strings:
            raise BileFormatError(f"BMTI[{index}] 引用无效 BRTS 偏移 0x{name_offset:X}")
        element_shells.append(
            Element(
                index=item_index,
                name_offset=name_offset,
                name=strings[name_offset],
                x=_f32(data, offset + 8, "BMTI.x"),
                y=_f32(data, offset + 12, "BMTI.y"),
                has_texture=_u32(data, offset + 24, "BMTI.has_texture") != 0,
                frame_count=_u32(data, offset + 28, "BMTI.frame_count"),
                channel_count=_u32(data, offset + 32, "BMTI.channel_count"),
                opaque_14=_u32(data, offset + 20, "BMTI.opaque_14"),
                opaque_18=_u32(data, offset + 24, "BMTI.type"),
                opaque_2c=_u32(data, offset + 44, "BMTI.opaque_2c"),
                opaque_30=_u32(data, offset + 48, "BMTI.opaque_30"),
                opaque_34=_u32(data, offset + 52, "BMTI.opaque_34"),
            )
        )

    # 基于顺序累计关系重建元素 -> 通道 -> 帧 -> 轨道。所有游标均在最后检查全消费。
    byal = sections["BYAL"]
    bmrf = sections["BMRF"]
    bxdi = sections.get("BXDI")
    channel_cursor = 0
    frame_cursor = 0
    track_cursor = 0
    elements: list[Element] = []
    for element in element_shells:
        channels: list[Channel] = []
        for _channel_index in range(element.channel_count):
            if channel_cursor >= byal.count:
                raise BileFormatError(f"{element.name} 的通道数超出 BYAL")
            channel_offset = byal.payload_offset + channel_cursor * 8
            frame_count = _u32(data, channel_offset, "BYAL.frame_count")
            frames: list[Frame] = []
            for _frame_index in range(frame_count):
                if frame_cursor >= bmrf.count:
                    raise BileFormatError(f"{element.name} 的帧数超出 BMRF")
                tracks: list[Track] = []
                if header.version == 2:
                    # v2 不含 BXDI。新增世2/欧3反例与既有将军的荣耀1样本共同表明，BMRF
                    # 的 12 字节记录为 <u32 slot, u32 track_count, opaque_u32>：每个帧记录
                    # 消费 track_count 条连续 BELE。BELE 的最后一个 s32 则为每条轨道的目标元素。
                    # 旧样本恰好每帧 track_count 都为 1，不能据此把 BMRF 第二 dword误作元素索引。
                    frame_offset = bmrf.payload_offset + frame_cursor * 12
                    slot = _u32(data, frame_offset, "BILE v2 BMRF.slot")
                    track_count = _u32(data, frame_offset + 4, "BILE v2 BMRF.track_count")
                    for _track_index in range(track_count):
                        if track_cursor >= len(keyframes):
                            raise BileFormatError(f"BILE v2 BMRF 轨道数超出 BELE[{track_cursor}]")
                        keyframe_index = track_cursor
                        keyframe_offset = bele.payload_offset + keyframe_index * 48
                        element_index = _s32(data, keyframe_offset + 44, "BILE v2 BELE.element_index")
                        if element_index != -1 and not 0 <= element_index < len(element_shells):
                            raise BileFormatError(f"BILE v2 BELE 引用越界 BMTI[{element_index}]")
                        tracks.append(Track(keyframe_index, element_index))
                        track_cursor += 1
                else:
                    if bxdi is None:
                        raise BileFormatError("BILE v3/v4 缺少 BXDI")
                    frame_offset = bmrf.payload_offset + frame_cursor * 8
                    slot = _u16(data, frame_offset, "BMRF.slot")
                    track_count = _u16(data, frame_offset + 2, "BMRF.track_count")
                    for _track_index in range(track_count):
                        if track_cursor >= bxdi.count:
                            raise BileFormatError(f"{element.name} 的轨道数超出 BXDI")
                        track_offset = bxdi.payload_offset + track_cursor * 8
                        keyframe_index = _u32(data, track_offset, "BXDI.keyframe_index")
                        element_index = _s32(data, track_offset + 4, "BXDI.element_index")
                        if keyframe_index >= len(keyframes):
                            raise BileFormatError(f"BXDI 引用越界 BELE[{keyframe_index}]")
                        if element_index != -1 and not 0 <= element_index < len(element_shells):
                            raise BileFormatError(f"BXDI 引用越界 BMTI[{element_index}]")
                        tracks.append(Track(keyframe_index, element_index))
                        track_cursor += 1
                frames.append(Frame(slot, tuple(tracks)))
                frame_cursor += 1
            channels.append(Channel(tuple(frames)))
            channel_cursor += 1
        elements.append(
            Element(
                **{**element.__dict__, "channels": tuple(channels)}
            )
        )
    expected_track_count = len(keyframes) if header.version == 2 else (bxdi.count if bxdi is not None else -1)
    if channel_cursor != byal.count or frame_cursor != bmrf.count or track_cursor != expected_track_count:
        track_label = "BELE（v2 由 BMRF.track_count 累计消费）" if header.version == 2 else "BXDI"
        raise BileFormatError(
            "累计遍历未完整消费时间线块："
            f"BYAL {channel_cursor}/{byal.count}，BMRF {frame_cursor}/{bmrf.count}，{track_label} {track_cursor}/{expected_track_count}"
        )
    graph_cycles = _find_animation_cycles(tuple(elements))
    return BileDocument(header, sections, tuple(keyframes), tuple(elements), strings, graph_cycles)


def _find_animation_cycles(elements: tuple[Element, ...]) -> tuple[tuple[int, ...], ...]:
    """从动画元素引用图中找环；环不阻止读取，但预览器必须避免无限递归。"""
    adjacency: dict[int, set[int]] = {element.index: set() for element in elements if not element.has_texture}
    for element in elements:
        if element.has_texture:
            continue
        for channel in element.channels:
            for frame in channel.frames:
                for track in frame.tracks:
                    if track.element_index >= 0 and not elements[track.element_index].has_texture:
                        adjacency[element.index].add(track.element_index)
    state = {index: 0 for index in adjacency}
    stack: list[int] = []
    positions: dict[int, int] = {}
    cycles: list[tuple[int, ...]] = []
    seen: set[tuple[int, ...]] = set()

    def visit(node: int) -> None:
        state[node] = 1
        positions[node] = len(stack)
        stack.append(node)
        for target in sorted(adjacency[node]):
            if state[target] == 0:
                visit(target)
            elif state[target] == 1:
                cycle = tuple(stack[positions[target]:] + [target])
                if cycle not in seen:
                    seen.add(cycle)
                    cycles.append(cycle)
        stack.pop()
        positions.pop(node, None)
        state[node] = 2

    for node in sorted(adjacency):
        if state[node] == 0:
            visit(node)
    return tuple(cycles)


def parse_file(path: str | Path) -> BileDocument:
    """读取并解析指定的 BIN 文件。"""
    return parse_bytes(Path(path).read_bytes())
