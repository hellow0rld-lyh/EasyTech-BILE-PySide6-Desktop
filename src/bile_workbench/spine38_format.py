"""Spine 3.8.99 静态骨架的严格只读解析。

该模块只实现欧7已实测的标准 Spine 3.8.99 前缀到 skins 结束：header、共享字符串、bones、slots、三类约束、皮肤与附件。
事件和动画时间线尚未被解码，任何 Spine 文件均不提供写回。
"""
from __future__ import annotations

import hashlib
import math
import struct
from dataclasses import dataclass
from pathlib import Path

from .spine_attachment_evidence import ClippingEvidence, LinkedMeshEvidence


class Spine38FormatError(ValueError):
    """标准 Spine 3.8.99 静态骨架读取失败。"""


@dataclass(frozen=True)
class Spine38Header:
    source_hash: str
    version: str
    bounds: tuple[float, float, float, float]
    nonessential: bool
    fps: float | None
    images_path: str | None
    audio_path: str | None


@dataclass(frozen=True)
class Spine38Bone:
    index: int
    name: str
    parent_index: int | None
    rotation: float
    x: float
    y: float
    scale_x: float
    scale_y: float
    shear_x: float
    shear_y: float
    length: float
    transform_mode: int
    skin_required: bool


@dataclass(frozen=True)
class Spine38Slot:
    index: int
    name: str
    bone_index: int
    rgba: int
    dark_rgb: int | None
    setup_attachment: str | None
    blend_mode: int


@dataclass(frozen=True)
class Spine38RegionAttachment:
    skin: str
    slot_index: int
    name: str
    path: str
    rotation: float
    x: float
    y: float
    scale_x: float
    scale_y: float
    width: float
    height: float
    rgba: int
    attachment_key: str | None = None


@dataclass(frozen=True)
class SpineMeshAttachment:
    skin: str
    slot_index: int
    name: str
    path: str
    rgba: int
    uvs: tuple[float, ...]
    triangles: tuple[int, ...]
    vertices: tuple[float, ...] | None
    hull_length: int
    weighted_vertices: tuple[tuple[tuple[int, float, float, float], ...], ...] | None = None
    attachment_key: str | None = None


@dataclass(frozen=True)
class SpineIkConstraint:
    index: int
    name: str
    order: int
    skin_required: bool
    bones: tuple[int, ...]
    target: int
    mix: float
    softness: float
    bend_direction: int
    compress: bool
    stretch: bool
    uniform: bool


@dataclass(frozen=True)
class SpineTransformConstraint:
    index: int
    name: str
    order: int
    skin_required: bool
    bones: tuple[int, ...]
    target: int
    local: bool
    relative: bool
    offset_rotation: float
    offset_x: float
    offset_y: float
    offset_scale_x: float
    offset_scale_y: float
    offset_shear_y: float
    mix_rotate: float
    mix_x: float
    mix_y: float
    mix_scale_x: float
    mix_scale_y: float
    mix_shear_y: float


@dataclass(frozen=True)
class Spine38StaticDocument:
    source_path: Path
    sha256: str
    byte_length: int
    header: Spine38Header
    shared_strings: tuple[str | None, ...]
    bones: tuple[Spine38Bone, ...]
    slots: tuple[Spine38Slot, ...]
    ik_constraints: tuple[SpineIkConstraint, ...]
    transform_constraints: tuple[SpineTransformConstraint, ...]
    path_constraint_count: int
    skin_names: tuple[str, ...]
    region_attachments: tuple[Spine38RegionAttachment, ...]
    mesh_attachments: tuple[SpineMeshAttachment, ...]
    static_end: int
    undecoded_tail_bytes: int
    linked_mesh_evidence: tuple[LinkedMeshEvidence, ...] = ()
    clipping_evidence: tuple[ClippingEvidence, ...] = ()

    @property
    def ik_constraint_count(self) -> int:
        return len(self.ik_constraints)

    @property
    def transform_constraint_count(self) -> int:
        return len(self.transform_constraints)


class _Reader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.offset = 0

    def _need(self, size: int, label: str) -> None:
        if size < 0 or self.offset + size > len(self.data):
            raise Spine38FormatError(f"{label} 越过文件末尾：offset={self.offset} size={size} total={len(self.data)}")

    def byte(self, label: str) -> int:
        self._need(1, label)
        value = self.data[self.offset]
        self.offset += 1
        return value

    def bool(self, label: str) -> bool:
        value = self.byte(label)
        if value not in (0, 1):
            raise Spine38FormatError(f"{label} 不是 0/1：{value}")
        return bool(value)

    def int32(self, label: str) -> int:
        self._need(4, label)
        value = struct.unpack_from(">i", self.data, self.offset)[0]
        self.offset += 4
        return value

    def f32(self, label: str) -> float:
        self._need(4, label)
        value = struct.unpack_from(">f", self.data, self.offset)[0]
        self.offset += 4
        if not math.isfinite(value) or abs(value) > 1_000_000:
            raise Spine38FormatError(f"{label} 不是可信有限浮点：{value}")
        return value

    def varint(self, label: str, *, positive: bool = True) -> int:
        value = 0
        for index in range(5):
            part = self.byte(label)
            value |= (part & 0x7F) << (index * 7)
            if not part & 0x80:
                return value if positive else ((value >> 1) ^ -(value & 1))
        raise Spine38FormatError(f"{label} varint 超过 5 字节")

    def string(self, label: str) -> str | None:
        count = self.varint(label)
        if count == 0:
            return None
        if count == 1:
            return ""
        count -= 1
        self._need(count, label)
        raw = self.data[self.offset:self.offset + count]
        self.offset += count
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise Spine38FormatError(f"{label} 不是 UTF-8") from exc

    def ref_string(self, strings: tuple[str | None, ...], label: str) -> str | None:
        index = self.varint(label)
        if index == 0:
            return None
        index -= 1
        if not 0 <= index < len(strings):
            raise Spine38FormatError(f"{label} 引用共享字符串越界：{index}/{len(strings)}")
        return strings[index]


def _count(reader: _Reader, label: str, maximum: int = 100_000) -> int:
    value = reader.varint(label)
    if value > maximum:
        raise Spine38FormatError(f"{label} 过大：{value}")
    return value


def _read_vertices(reader: _Reader, vertex_count: int, label: str) -> None:
    if vertex_count > 100_000:
        raise Spine38FormatError(f"{label}.vertex_count 过大：{vertex_count}")
    weighted = reader.bool(f"{label}.weighted")
    if not weighted:
        for index in range(vertex_count * 2):
            reader.f32(f"{label}.vertices[{index}]")
        return
    for vertex in range(vertex_count):
        bone_count = _count(reader, f"{label}.vertex[{vertex}].bone_count", 1024)
        for bone in range(bone_count):
            reader.varint(f"{label}.vertex[{vertex}].bone[{bone}].index")
            reader.f32(f"{label}.vertex[{vertex}].bone[{bone}].x")
            reader.f32(f"{label}.vertex[{vertex}].bone[{bone}].y")
            reader.f32(f"{label}.vertex[{vertex}].bone[{bone}].weight")


def _read_short_array(reader: _Reader, label: str) -> None:
    count = _count(reader, f"{label}.count", 2_000_000)
    for index in range(count):
        reader._need(2, f"{label}[{index}]")
        reader.offset += 2


def _read_mesh_vertices(reader: _Reader, vertex_count: int, label: str) -> tuple[tuple[float, ...] | None, tuple[tuple[tuple[int, float, float, float], ...], ...] | None]:
    if vertex_count > 100_000:
        raise Spine38FormatError(f"{label}.vertex_count 过大：{vertex_count}")
    weighted = reader.bool(f"{label}.weighted")
    if not weighted:
        return tuple(reader.f32(f"{label}.vertices[{index}]") for index in range(vertex_count * 2)), None
    vertices = []
    for vertex in range(vertex_count):
        influences = []
        for bone in range(_count(reader, f"{label}.vertex[{vertex}].bone_count", 1024)):
            index = reader.varint(f"{label}.vertex[{vertex}].bone[{bone}].index")
            x = reader.f32(f"{label}.vertex[{vertex}].bone[{bone}].x")
            y = reader.f32(f"{label}.vertex[{vertex}].bone[{bone}].y")
            weight = reader.f32(f"{label}.vertex[{vertex}].bone[{bone}].weight")
            influences.append((index, x, y, weight))
        vertices.append(tuple(influences))
    return None, tuple(vertices)


def _read_mesh_shorts(reader: _Reader, label: str) -> tuple[int, ...]:
    count = _count(reader, f"{label}.count", 2_000_000)
    values = []
    for index in range(count):
        reader._need(2, f"{label}[{index}]")
        values.append((reader.data[reader.offset] << 8) | reader.data[reader.offset + 1])
        reader.offset += 2
    return tuple(values)


def _read_attachment(reader: _Reader, strings: tuple[str | None, ...], skin: str, slot_index: int, attachment_name: str | None, nonessential: bool, regions: list[Spine38RegionAttachment], meshes: list[SpineMeshAttachment], linked_meshes: list[LinkedMeshEvidence], clippings: list[ClippingEvidence]) -> None:
    name = reader.ref_string(strings, "attachment.name") or attachment_name
    if not name:
        raise Spine38FormatError("attachment 名称为空")
    kind = reader.byte(f"attachment[{name}].type")
    if kind == 0:  # region
        path = reader.ref_string(strings, f"attachment[{name}].path") or name
        values = [reader.f32(f"attachment[{name}].region[{index}]") for index in range(7)]
        rgba = reader.int32(f"attachment[{name}].rgba")
        regions.append(Spine38RegionAttachment(skin, slot_index, name, path, *values, rgba, attachment_name or name))
    elif kind == 1:  # boundingbox
        _read_vertices(reader, _count(reader, f"attachment[{name}].vertex_count"), f"attachment[{name}]")
        if nonessential:
            reader.int32(f"attachment[{name}].rgba")
    elif kind == 2:  # mesh
        path = reader.ref_string(strings, f"attachment[{name}].path") or name
        rgba = reader.int32(f"attachment[{name}].rgba")
        vertex_count = _count(reader, f"attachment[{name}].vertex_count")
        uvs = tuple(reader.f32(f"attachment[{name}].uv[{index}]") for index in range(vertex_count * 2))
        triangles = _read_mesh_shorts(reader, f"attachment[{name}].triangles")
        vertices, weighted_vertices = _read_mesh_vertices(reader, vertex_count, f"attachment[{name}]")
        hull_length = reader.varint(f"attachment[{name}].hull_length")
        meshes.append(SpineMeshAttachment(skin, slot_index, name, path, rgba, uvs, triangles, vertices, hull_length, weighted_vertices, attachment_name or name))
        if nonessential:
            _read_short_array(reader, f"attachment[{name}].edges")
            reader.f32(f"attachment[{name}].width")
            reader.f32(f"attachment[{name}].height")
    elif kind == 3:  # linkedmesh
        path = reader.ref_string(strings, f"attachment[{name}].path")
        reader.int32(f"attachment[{name}].rgba")
        parent_skin = reader.ref_string(strings, f"attachment[{name}].skin")
        parent_name = reader.ref_string(strings, f"attachment[{name}].parent")
        inherit_deform = reader.bool(f"attachment[{name}].inherit_deform")
        linked_meshes.append(LinkedMeshEvidence("3.8", skin, slot_index, name, path, parent_skin, parent_name, inherit_deform, False, attachment_name or name))
        if nonessential:
            reader.f32(f"attachment[{name}].width")
            reader.f32(f"attachment[{name}].height")
    elif kind == 4:  # path
        reader.bool(f"attachment[{name}].closed")
        reader.bool(f"attachment[{name}].constant_speed")
        vertex_count = _count(reader, f"attachment[{name}].vertex_count")
        _read_vertices(reader, vertex_count, f"attachment[{name}]")
        for index in range(vertex_count // 3):
            reader.f32(f"attachment[{name}].length[{index}]")
        if nonessential:
            reader.int32(f"attachment[{name}].rgba")
    elif kind == 5:  # point
        reader.f32(f"attachment[{name}].rotation")
        reader.f32(f"attachment[{name}].x")
        reader.f32(f"attachment[{name}].y")
        if nonessential:
            reader.int32(f"attachment[{name}].rgba")
    elif kind == 6:  # clipping
        end_slot = reader.varint(f"attachment[{name}].end_slot")
        vertex_count = _count(reader, f"attachment[{name}].vertex_count")
        _read_vertices(reader, vertex_count, f"attachment[{name}]")
        clippings.append(ClippingEvidence("3.8", skin, slot_index, name, attachment_name or name, end_slot, vertex_count))
        if nonessential:
            reader.int32(f"attachment[{name}].rgba")
    else:
        raise Spine38FormatError(f"attachment[{name}] 类型未知：{kind}")


def _read_skin(reader: _Reader, strings: tuple[str | None, ...], skin: str, is_default: bool, nonessential: bool, slots: tuple[Spine38Slot, ...], regions: list[Spine38RegionAttachment], meshes: list[SpineMeshAttachment], linked_meshes: list[LinkedMeshEvidence], clippings: list[ClippingEvidence]) -> bool:
    if is_default:
        slot_count = _count(reader, "default_skin.slot_count")
        if slot_count == 0:
            return False
    else:
        bone_count = _count(reader, f"skin[{skin}].bone_count")
        for index in range(bone_count):
            reader.varint(f"skin[{skin}].bone[{index}]")
        for category in ("ik", "transform", "path"):
            for index in range(_count(reader, f"skin[{skin}].{category}_count")):
                reader.varint(f"skin[{skin}].{category}[{index}]")
        slot_count = _count(reader, f"skin[{skin}].slot_count")
    for index in range(slot_count):
        slot_index = reader.varint(f"skin[{skin}].slot[{index}].index")
        if not 0 <= slot_index < len(slots):
            raise Spine38FormatError(f"skin[{skin}] 插槽越界：{slot_index}/{len(slots)}")
        attachment_count = _count(reader, f"skin[{skin}].slot[{index}].attachment_count")
        for attachment in range(attachment_count):
            attachment_name = reader.ref_string(strings, f"skin[{skin}].slot[{index}].attachment[{attachment}].name")
            _read_attachment(reader, strings, skin, slot_index, attachment_name, nonessential, regions, meshes, linked_meshes, clippings)
    return True


def parse_spine38_static(path: Path) -> Spine38StaticDocument:
    data = path.read_bytes()
    reader = _Reader(data)
    source_hash = reader.string("header.hash")
    version = reader.string("header.version")
    if not source_hash or version != "3.8.99":
        raise Spine38FormatError(f"仅接受标准 Spine 3.8.99：hash={source_hash!r} version={version!r}")
    bounds = tuple(reader.f32(f"header.bounds[{index}]") for index in range(4))
    nonessential = reader.bool("header.nonessential")
    fps = reader.f32("header.fps") if nonessential else None
    images_path = reader.string("header.images") if nonessential else None
    audio_path = reader.string("header.audio") if nonessential else None
    header = Spine38Header(source_hash, version, bounds, nonessential, fps, images_path, audio_path)

    shared_strings = tuple(reader.string(f"shared_strings[{index}]") for index in range(_count(reader, "shared_strings.count")))
    bones = []
    for index in range(_count(reader, "bones.count")):
        name = reader.string(f"bones[{index}].name")
        if not name:
            raise Spine38FormatError(f"bones[{index}].name 为空")
        parent = None if index == 0 else reader.varint(f"bones[{index}].parent")
        if parent is not None and not 0 <= parent < index:
            raise Spine38FormatError(f"bones[{index}].parent 越界或未指向前序骨骼：{parent}")
        values = [reader.f32(f"bones[{index}].value[{field}]") for field in range(8)]
        transform = reader.varint(f"bones[{index}].transform_mode")
        if transform > 4:
            raise Spine38FormatError(f"bones[{index}].transform_mode 越界：{transform}")
        skin_required = reader.bool(f"bones[{index}].skin_required")
        if nonessential:
            reader.int32(f"bones[{index}].rgba")
        bones.append(Spine38Bone(index, name, parent, *values, transform, skin_required))
    bones_tuple = tuple(bones)

    slots = []
    for index in range(_count(reader, "slots.count")):
        name = reader.string(f"slots[{index}].name")
        bone_index = reader.varint(f"slots[{index}].bone")
        if not name or not 0 <= bone_index < len(bones_tuple):
            raise Spine38FormatError(f"slots[{index}] 名称或骨骼引用无效")
        rgba = reader.int32(f"slots[{index}].rgba")
        dark = reader.int32(f"slots[{index}].dark")
        setup = reader.ref_string(shared_strings, f"slots[{index}].setup_attachment")
        blend = reader.varint(f"slots[{index}].blend")
        if blend > 3:
            raise Spine38FormatError(f"slots[{index}].blend 越界：{blend}")
        slots.append(Spine38Slot(index, name, bone_index, rgba, None if dark == -1 else dark, setup, blend))
    slots_tuple = tuple(slots)

    ik_constraints: list[SpineIkConstraint] = []
    for index in range(_count(reader, "ik.count")):
        name = reader.string(f"ik[{index}].name")
        order = reader.varint(f"ik[{index}].order")
        skin_required = reader.bool(f"ik[{index}].skin_required")
        constrained = tuple(reader.varint(f"ik[{index}].bone[{bone}]") for bone in range(_count(reader, f"ik[{index}].bone_count")))
        target = reader.varint(f"ik[{index}].target")
        mix = reader.f32(f"ik[{index}].mix")
        softness = reader.f32(f"ik[{index}].softness")
        raw_bend = reader.byte(f"ik[{index}].bend")
        bend = raw_bend - 256 if raw_bend > 127 else raw_bend
        compress = reader.bool(f"ik[{index}].compress")
        stretch = reader.bool(f"ik[{index}].stretch")
        uniform = reader.bool(f"ik[{index}].uniform")
        if not name or not constrained or any(not 0 <= bone < len(bones_tuple) for bone in constrained) or not 0 <= target < len(bones_tuple) or bend not in (-1, 1):
            raise Spine38FormatError(f"ik[{index}] 名称、骨骼、target 或 bend 无效")
        ik_constraints.append(SpineIkConstraint(index, name, order, skin_required, constrained, target, mix, softness, bend, compress, stretch, uniform))
    transform_constraints: list[SpineTransformConstraint] = []
    for index in range(_count(reader, "transform.count")):
        name = reader.string(f"transform[{index}].name")
        order = reader.varint(f"transform[{index}].order")
        skin_required = reader.bool(f"transform[{index}].skin_required")
        constrained = tuple(reader.varint(f"transform[{index}].bone[{bone}]") for bone in range(_count(reader, f"transform[{index}].bone_count")))
        target = reader.varint(f"transform[{index}].target")
        local = reader.bool(f"transform[{index}].local")
        relative = reader.bool(f"transform[{index}].relative")
        values = tuple(reader.f32(f"transform[{index}].value[{value}]") for value in range(10))
        if not name or not constrained or any(not 0 <= bone < len(bones_tuple) for bone in constrained) or not 0 <= target < len(bones_tuple):
            raise Spine38FormatError(f"transform[{index}] 名称、骨骼或 target 无效")
        transform_constraints.append(SpineTransformConstraint(index, name, order, skin_required, constrained, target, local, relative, *values[:6], values[6], values[7], values[7], values[8], values[8], values[9]))
    path_count = _count(reader, "path.count")
    for index in range(path_count):
        reader.string(f"path[{index}].name"); reader.varint(f"path[{index}].order"); reader.bool(f"path[{index}].skin_required")
        for bone in range(_count(reader, f"path[{index}].bone_count")):
            reader.varint(f"path[{index}].bone[{bone}]")
        reader.varint(f"path[{index}].target"); reader.varint(f"path[{index}].position_mode"); reader.varint(f"path[{index}].spacing_mode"); reader.varint(f"path[{index}].rotate_mode")
        for value in range(5):
            reader.f32(f"path[{index}].value[{value}]")

    regions: list[Spine38RegionAttachment] = []
    skin_names: list[str] = []
    meshes: list[SpineMeshAttachment] = []
    linked_meshes: list[LinkedMeshEvidence] = []
    clippings: list[ClippingEvidence] = []
    if _read_skin(reader, shared_strings, "default", True, nonessential, slots_tuple, regions, meshes, linked_meshes, clippings):
        skin_names.append("default")
    for index in range(_count(reader, "skins.count")):
        skin = reader.ref_string(shared_strings, f"skins[{index}].name")
        if not skin:
            raise Spine38FormatError(f"skins[{index}].name 为空")
        _read_skin(reader, shared_strings, skin, False, nonessential, slots_tuple, regions, meshes, linked_meshes, clippings)
        skin_names.append(skin)
    static_end = reader.offset
    return Spine38StaticDocument(path, hashlib.sha256(data).hexdigest(), len(data), header, shared_strings, bones_tuple, slots_tuple, tuple(ik_constraints), tuple(transform_constraints), path_count, tuple(skin_names), tuple(regions), tuple(meshes), static_end, len(data) - static_end, tuple(linked_meshes), tuple(clippings))


def parse_file(path: Path) -> Spine38StaticDocument:
    return parse_spine38_static(path)
