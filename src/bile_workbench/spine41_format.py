"""征2封装内 Spine 4.1.x 静态骨架的严格只读解析。

已实测征2的前 8 字节按 Spine 4.1 `long hash` 读取，后续载荷遵循 4.1 静态骨架顺序。
该模块到 skins 结束为止；events/animations 均显式保留为未解码尾部，且无写回功能。
"""
from __future__ import annotations

import hashlib
import math
import re
import struct
from dataclasses import dataclass
from pathlib import Path

from .spine38_format import Spine38Bone, Spine38FormatError, Spine38RegionAttachment, Spine38Slot, SpineIkConstraint, SpineMeshAttachment, SpineTransformConstraint, _Reader, _count, _read_mesh_shorts, _read_mesh_vertices, _read_short_array, _read_vertices
from .spine_attachment_evidence import ClippingEvidence, LinkedMeshEvidence, SequenceEvidence

_VERSION = re.compile(r"^4\.1\.\d+$")


@dataclass(frozen=True)
class Spine41Header:
    hash_long: int
    version: str
    bounds: tuple[float, float, float, float]
    nonessential: bool
    fps: float | None
    images_path: str | None
    audio_path: str | None


@dataclass(frozen=True)
class Spine41StaticDocument:
    source_path: Path
    sha256: str
    byte_length: int
    header: Spine41Header
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
    sequence_evidence: tuple[SequenceEvidence, ...] = ()
    clipping_evidence: tuple[ClippingEvidence, ...] = ()

    @property
    def ik_constraint_count(self) -> int:
        return len(self.ik_constraints)

    @property
    def transform_constraint_count(self) -> int:
        return len(self.transform_constraints)


def _long(reader: _Reader, label: str) -> int:
    reader._need(8, label)
    value = struct.unpack_from(">q", reader.data, reader.offset)[0]
    reader.offset += 8
    return value


def _sequence(
    reader: _Reader,
    label: str,
    *,
    skin: str | None = None,
    slot_index: int | None = None,
    name: str | None = None,
    attachment_key: str | None = None,
    attachment_kind: str | None = None,
    evidence: list[SequenceEvidence] | None = None,
) -> bool:
    if not reader.bool(f"{label}.present"):
        return False
    count, start, digits, setup_index = (reader.varint(f"{label}.{field}") for field in ("count", "start", "digits", "setup_index"))
    if evidence is not None and skin is not None and slot_index is not None and name is not None:
        evidence.append(SequenceEvidence("4.1", skin, slot_index, name, count, start, digits, setup_index, attachment_key or name, attachment_kind))
    return True


def _attachment(reader: _Reader, strings: tuple[str | None, ...], skin: str, slot_index: int, attachment_name: str | None, nonessential: bool, regions: list[Spine38RegionAttachment], meshes: list[SpineMeshAttachment], linked_meshes: list[LinkedMeshEvidence], sequences: list[SequenceEvidence], clippings: list[ClippingEvidence]) -> None:
    name = reader.ref_string(strings, "attachment.name") or attachment_name
    if not name:
        raise Spine38FormatError("4.1 attachment 名称为空")
    kind = reader.byte(f"attachment[{name}].type")
    if kind == 0:
        path = reader.ref_string(strings, f"attachment[{name}].path") or name
        values = [reader.f32(f"attachment[{name}].region[{index}]") for index in range(7)]
        rgba = reader.int32(f"attachment[{name}].rgba")
        _sequence(reader, f"attachment[{name}].sequence", skin=skin, slot_index=slot_index, name=name, attachment_key=attachment_name or name, attachment_kind="region", evidence=sequences)
        regions.append(Spine38RegionAttachment(skin, slot_index, name, path, *values, rgba, attachment_name or name))
    elif kind == 1:
        _read_vertices(reader, _count(reader, f"attachment[{name}].vertex_count"), f"attachment[{name}]")
        if nonessential:
            reader.int32(f"attachment[{name}].rgba")
    elif kind == 2:
        path = reader.ref_string(strings, f"attachment[{name}].path") or name
        rgba = reader.int32(f"attachment[{name}].rgba")
        vertex_count = _count(reader, f"attachment[{name}].vertex_count")
        uvs = tuple(reader.f32(f"attachment[{name}].uv[{index}]") for index in range(vertex_count * 2))
        triangles = _read_mesh_shorts(reader, f"attachment[{name}].triangles")
        vertices, weighted_vertices = _read_mesh_vertices(reader, vertex_count, f"attachment[{name}]")
        hull_length = reader.varint(f"attachment[{name}].hull_length")
        has_sequence = _sequence(reader, f"attachment[{name}].sequence", skin=skin, slot_index=slot_index, name=name, attachment_key=attachment_name or name, attachment_kind="mesh", evidence=sequences)
        if not has_sequence:
            meshes.append(SpineMeshAttachment(skin, slot_index, name, path, rgba, uvs, triangles, vertices, hull_length, weighted_vertices, attachment_name or name))
        if nonessential:
            _read_short_array(reader, f"attachment[{name}].edges")
            reader.f32(f"attachment[{name}].width")
            reader.f32(f"attachment[{name}].height")
    elif kind == 3:
        path = reader.ref_string(strings, f"attachment[{name}].path")
        reader.int32(f"attachment[{name}].rgba")
        parent_skin = reader.ref_string(strings, f"attachment[{name}].skin")
        parent_name = reader.ref_string(strings, f"attachment[{name}].parent")
        inherit_timelines = reader.bool(f"attachment[{name}].inherit_timelines")
        sequence_present = _sequence(reader, f"attachment[{name}].sequence", skin=skin, slot_index=slot_index, name=name, attachment_key=attachment_name or name, attachment_kind="linked_mesh", evidence=sequences)
        linked_meshes.append(LinkedMeshEvidence("4.1", skin, slot_index, name, path, parent_skin, parent_name, inherit_timelines, sequence_present, attachment_name or name))
        if nonessential:
            reader.f32(f"attachment[{name}].width")
            reader.f32(f"attachment[{name}].height")
    elif kind == 4:
        reader.bool(f"attachment[{name}].closed")
        reader.bool(f"attachment[{name}].constant_speed")
        vertex_count = _count(reader, f"attachment[{name}].vertex_count")
        _read_vertices(reader, vertex_count, f"attachment[{name}]")
        for index in range(vertex_count // 3):
            reader.f32(f"attachment[{name}].length[{index}]")
        if nonessential:
            reader.int32(f"attachment[{name}].rgba")
    elif kind == 5:
        reader.f32(f"attachment[{name}].rotation")
        reader.f32(f"attachment[{name}].x")
        reader.f32(f"attachment[{name}].y")
        if nonessential:
            reader.int32(f"attachment[{name}].rgba")
    elif kind == 6:
        end_slot = reader.varint(f"attachment[{name}].end_slot")
        vertex_count = _count(reader, f"attachment[{name}].vertex_count")
        _read_vertices(reader, vertex_count, f"attachment[{name}]")
        clippings.append(ClippingEvidence("4.1", skin, slot_index, name, attachment_name or name, end_slot, vertex_count))
        if nonessential:
            reader.int32(f"attachment[{name}].rgba")
    else:
        raise Spine38FormatError(f"4.1 attachment[{name}] 类型未知：{kind}")


def _skin(reader: _Reader, strings: tuple[str | None, ...], skin: str, default: bool, nonessential: bool, slots: tuple[Spine38Slot, ...], regions: list[Spine38RegionAttachment], meshes: list[SpineMeshAttachment], linked_meshes: list[LinkedMeshEvidence], sequences: list[SequenceEvidence], clippings: list[ClippingEvidence]) -> bool:
    slot_count = _count(reader, "default_skin.slot_count") if default else None
    if default and slot_count == 0:
        return False
    if not default:
        for group in ("bones", "ik", "transform", "path"):
            for index in range(_count(reader, f"skin[{skin}].{group}_count")):
                reader.varint(f"skin[{skin}].{group}[{index}]")
        slot_count = _count(reader, f"skin[{skin}].slot_count")
    assert slot_count is not None
    for index in range(slot_count):
        slot_index = reader.varint(f"skin[{skin}].slot[{index}].index")
        if not 0 <= slot_index < len(slots):
            raise Spine38FormatError(f"skin[{skin}].slot 越界：{slot_index}/{len(slots)}")
        for attachment in range(_count(reader, f"skin[{skin}].slot[{index}].attachment_count")):
            attachment_name = reader.ref_string(strings, f"skin[{skin}].slot[{index}].attachment[{attachment}].name")
            _attachment(reader, strings, skin, slot_index, attachment_name, nonessential, regions, meshes, linked_meshes, sequences, clippings)
    return True


def parse_spine41_static(path: Path) -> Spine41StaticDocument:
    data = path.read_bytes()
    reader = _Reader(data)
    hash_long = _long(reader, "header.hash_long")
    version = reader.string("header.version")
    if version is None or not _VERSION.fullmatch(version):
        raise Spine38FormatError(f"仅接受征2实测 Spine 4.1.x 载荷，实际版本为 {version!r}")
    bounds = tuple(reader.f32(f"header.bounds[{index}]") for index in range(4))
    nonessential = reader.bool("header.nonessential")
    fps = reader.f32("header.fps") if nonessential else None
    images_path = reader.string("header.images") if nonessential else None
    audio_path = reader.string("header.audio") if nonessential else None
    header = Spine41Header(hash_long, version, bounds, nonessential, fps, images_path, audio_path)

    strings = tuple(reader.string(f"shared_strings[{index}]") for index in range(_count(reader, "shared_strings.count")))
    bones = []
    for index in range(_count(reader, "bones.count")):
        name = reader.string(f"bones[{index}].name")
        parent = None if index == 0 else reader.varint(f"bones[{index}].parent")
        if not name or (parent is not None and not 0 <= parent < index):
            raise Spine38FormatError(f"bones[{index}] 名称或父引用无效")
        values = [reader.f32(f"bones[{index}].value[{field}]") for field in range(8)]
        transform_mode = reader.varint(f"bones[{index}].transform_mode")
        if transform_mode > 4:
            raise Spine38FormatError(f"bones[{index}].transform_mode 越界：{transform_mode}")
        skin_required = reader.bool(f"bones[{index}].skin_required")
        if nonessential:
            reader.int32(f"bones[{index}].rgba")
        bones.append(Spine38Bone(index, name, parent, *values, transform_mode, skin_required))
    bones_tuple = tuple(bones)

    slots = []
    for index in range(_count(reader, "slots.count")):
        name = reader.string(f"slots[{index}].name")
        bone = reader.varint(f"slots[{index}].bone")
        if not name or not 0 <= bone < len(bones_tuple):
            raise Spine38FormatError(f"slots[{index}] 名称或骨骼引用无效")
        rgba = reader.int32(f"slots[{index}].rgba")
        dark = reader.int32(f"slots[{index}].dark")
        setup = reader.ref_string(strings, f"slots[{index}].setup_attachment")
        blend = reader.varint(f"slots[{index}].blend")
        if blend > 3:
            raise Spine38FormatError(f"slots[{index}].blend 越界：{blend}")
        slots.append(Spine38Slot(index, name, bone, rgba, None if dark == -1 else dark, setup, blend))
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
        values = tuple(reader.f32(f"transform[{index}].value[{value}]") for value in range(12))
        if not name or not constrained or any(not 0 <= bone < len(bones_tuple) for bone in constrained) or not 0 <= target < len(bones_tuple):
            raise Spine38FormatError(f"transform[{index}] 名称、骨骼或 target 无效")
        transform_constraints.append(SpineTransformConstraint(index, name, order, skin_required, constrained, target, local, relative, *values))
    path_count = _count(reader, "path.count")
    for index in range(path_count):
        reader.string(f"path[{index}].name"); reader.varint(f"path[{index}].order"); reader.bool(f"path[{index}].skin_required")
        for bone in range(_count(reader, f"path[{index}].bone_count")):
            reader.varint(f"path[{index}].bone[{bone}]")
        reader.varint(f"path[{index}].target"); reader.varint(f"path[{index}].position_mode"); reader.varint(f"path[{index}].spacing_mode"); reader.varint(f"path[{index}].rotate_mode")
        for value in range(6):
            reader.f32(f"path[{index}].value[{value}]")

    regions: list[Spine38RegionAttachment] = []
    meshes: list[SpineMeshAttachment] = []
    linked_meshes: list[LinkedMeshEvidence] = []
    sequences: list[SequenceEvidence] = []
    clippings: list[ClippingEvidence] = []
    skin_names: list[str] = []
    if _skin(reader, strings, "default", True, nonessential, slots_tuple, regions, meshes, linked_meshes, sequences, clippings):
        skin_names.append("default")
    for index in range(_count(reader, "skins.count")):
        skin = reader.ref_string(strings, f"skins[{index}].name")
        if not skin:
            raise Spine38FormatError(f"skins[{index}].name 为空")
        _skin(reader, strings, skin, False, nonessential, slots_tuple, regions, meshes, linked_meshes, sequences, clippings)
        skin_names.append(skin)
    static_end = reader.offset
    return Spine41StaticDocument(path, hashlib.sha256(data).hexdigest(), len(data), header, strings, bones_tuple, slots_tuple, tuple(ik_constraints), tuple(transform_constraints), path_count, tuple(skin_names), tuple(regions), tuple(meshes), static_end, len(data) - static_end, tuple(linked_meshes), tuple(sequences), tuple(clippings))


def parse_file(path: Path) -> Spine41StaticDocument:
    return parse_spine41_static(path)
