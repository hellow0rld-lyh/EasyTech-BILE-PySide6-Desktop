"""欧7 Spine 3.8 二进制的严格只读骨架前缀解析与结构档案导出。

范围严格限制在官方 3.8 SkeletonBinary 已知顺序的 header、shared strings、bones 和 slots。
不会把其后的 constraints/skins/animations 误称为已解析，也不产生任何写回物。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
from dataclasses import asdict, dataclass
from pathlib import Path


class Spine38Error(ValueError):
    pass


@dataclass(frozen=True)
class SpineBone:
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
class SpineSlot:
    index: int
    name: str
    bone_index: int
    rgba: str
    dark_rgb: str | None
    setup_attachment: str | None
    blend_mode: int


@dataclass(frozen=True)
class SpinePrefixManifest:
    schema: str
    file: str
    sha256: str
    byte_length: int
    source_hash: str
    version: str
    bounds: tuple[float, float, float, float]
    nonessential: bool
    fps: float | None
    images_path: str | None
    audio_path: str | None
    shared_string_count: int
    bones: tuple[SpineBone, ...]
    slots: tuple[SpineSlot, ...]
    prefix_end: int
    remaining_bytes: int


class Reader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.offset = 0

    def require(self, size: int, label: str) -> None:
        if size < 0 or self.offset + size > len(self.data):
            raise Spine38Error(f"{label} 越过文件末尾：offset={self.offset} size={size} total={len(self.data)}")

    def byte(self, label: str) -> int:
        self.require(1, label)
        value = self.data[self.offset]
        self.offset += 1
        return value

    def boolean(self, label: str) -> bool:
        value = self.byte(label)
        if value not in (0, 1):
            raise Spine38Error(f"{label} 不是 0/1：{value}")
        return bool(value)

    def int32(self, label: str) -> int:
        self.require(4, label)
        value = struct.unpack_from(">i", self.data, self.offset)[0]
        self.offset += 4
        return value

    def f32(self, label: str) -> float:
        self.require(4, label)
        value = struct.unpack_from(">f", self.data, self.offset)[0]
        self.offset += 4
        if not math.isfinite(value) or abs(value) > 1_000_000:
            raise Spine38Error(f"{label} 非法浮点：{value}")
        return value

    def varint(self, label: str, *, optimize_positive: bool = True) -> int:
        value = 0
        shift = 0
        for count in range(5):
            byte = self.byte(label)
            value |= (byte & 0x7F) << shift
            if not byte & 0x80:
                return value if optimize_positive else ((value >> 1) ^ -(value & 1))
            shift += 7
        raise Spine38Error(f"{label} varint 超过 5 字节")

    def string(self, label: str) -> str | None:
        count = self.varint(label)
        if count == 0:
            return None
        if count == 1:
            return ""
        size = count - 1
        self.require(size, label)
        raw = self.data[self.offset:self.offset + size]
        self.offset += size
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise Spine38Error(f"{label} 不是有效 UTF-8") from exc

    def string_ref(self, strings: tuple[str | None, ...], label: str) -> str | None:
        index = self.varint(label)
        if index == 0:
            return None
        index -= 1
        if not 0 <= index < len(strings):
            raise Spine38Error(f"{label} 共享字符串索引越界：{index}/{len(strings)}")
        return strings[index]


def color_hex(value: int) -> str:
    return f"0x{value & 0xFFFFFFFF:08X}"


def parse(path: Path, root: Path) -> SpinePrefixManifest:
    data = path.read_bytes()
    reader = Reader(data)
    source_hash = reader.string("header.hash")
    if not source_hash:
        raise Spine38Error("header.hash 为空")
    version = reader.string("header.version")
    if version != "3.8.99":
        raise Spine38Error(f"仅接受经验证的欧7 Spine 3.8.99，实际为 {version!r}")
    bounds = tuple(reader.f32(f"header.bounds[{index}]") for index in range(4))
    nonessential = reader.boolean("header.nonessential")
    fps = reader.f32("header.fps") if nonessential else None
    images_path = reader.string("header.images") if nonessential else None
    audio_path = reader.string("header.audio") if nonessential else None

    shared_count = reader.varint("shared_strings.count")
    if shared_count > 100_000:
        raise Spine38Error(f"shared_strings.count 过大：{shared_count}")
    shared_strings = tuple(reader.string(f"shared_strings[{index}]") for index in range(shared_count))

    bone_count = reader.varint("bones.count")
    if not 1 <= bone_count <= 100_000:
        raise Spine38Error(f"bones.count 不在合理范围：{bone_count}")
    bones = []
    for index in range(bone_count):
        name = reader.string(f"bones[{index}].name")
        if not name:
            raise Spine38Error(f"bones[{index}] 名称为空")
        parent_index = None if index == 0 else reader.varint(f"bones[{index}].parent")
        if parent_index is not None and not 0 <= parent_index < index:
            raise Spine38Error(f"bones[{index}] 父骨骼不指向前序骨骼：{parent_index}")
        values = [reader.f32(f"bones[{index}].transform[{field}]") for field in range(8)]
        transform_mode = reader.varint(f"bones[{index}].transform_mode")
        if transform_mode > 4:
            raise Spine38Error(f"bones[{index}].transform_mode 越界：{transform_mode}")
        skin_required = reader.boolean(f"bones[{index}].skin_required")
        if nonessential:
            reader.int32(f"bones[{index}].color")
        bones.append(SpineBone(index, name, parent_index, *values, transform_mode, skin_required))

    slot_count = reader.varint("slots.count")
    if slot_count > 100_000:
        raise Spine38Error(f"slots.count 过大：{slot_count}")
    slots = []
    for index in range(slot_count):
        name = reader.string(f"slots[{index}].name")
        if not name:
            raise Spine38Error(f"slots[{index}] 名称为空")
        bone_index = reader.varint(f"slots[{index}].bone")
        if not 0 <= bone_index < len(bones):
            raise Spine38Error(f"slots[{index}] 骨骼索引越界：{bone_index}/{len(bones)}")
        rgba = color_hex(reader.int32(f"slots[{index}].color"))
        dark = reader.int32(f"slots[{index}].dark_color")
        setup_attachment = reader.string_ref(shared_strings, f"slots[{index}].setup_attachment")
        blend_mode = reader.varint(f"slots[{index}].blend_mode")
        if blend_mode > 3:
            raise Spine38Error(f"slots[{index}].blend_mode 越界：{blend_mode}")
        slots.append(SpineSlot(index, name, bone_index, rgba, None if dark == -1 else color_hex(dark), setup_attachment, blend_mode))

    return SpinePrefixManifest(
        schema="easytech-spine38-prefix/v1",
        file=str(path.relative_to(root)),
        sha256=hashlib.sha256(data).hexdigest(),
        byte_length=len(data),
        source_hash=source_hash,
        version=version,
        bounds=bounds,
        nonessential=nonessential,
        fps=fps,
        images_path=images_path,
        audio_path=audio_path,
        shared_string_count=len(shared_strings),
        bones=tuple(bones),
        slots=tuple(slots),
        prefix_end=reader.offset,
        remaining_bytes=len(data) - reader.offset,
    )


def markdown(manifest: SpinePrefixManifest) -> str:
    lines = [
        "# 欧7 Spine 3.8 骨架前缀档案",
        "",
        "> 本档案严格解析到 slots 结束位置。剩余字节包含 constraints、skins、attachments、events 与 animations，尚未在此读取器中声称完成解析或允许写回。",
        "",
        "## 元数据",
        "",
        "| 字段 | 值 |",
        "|---|---|",
        f"| 文件 | `{manifest.file}` |",
        f"| SHA-256 | `{manifest.sha256}` |",
        f"| Spine 版本 | `{manifest.version}` |",
        f"| source hash | `{manifest.source_hash}` |",
        f"| bounds | `{', '.join(f'{value:.2f}' for value in manifest.bounds)}` |",
        f"| 非必要数据 / fps | `{manifest.nonessential}` / `{manifest.fps}` |",
        f"| images path | `{manifest.images_path or '—'}` |",
        f"| 共享字符串 | {manifest.shared_string_count} |",
        f"| 骨骼 / 插槽 | {len(manifest.bones)} / {len(manifest.slots)} |",
        f"| 已验证前缀 / 未解码余量 | {manifest.prefix_end} / {manifest.remaining_bytes} 字节 |",
        "",
        "## 骨骼",
        "",
        "| # | 名称 | 父骨骼 | 平移 | 旋转 | 长度 | 模式 | skin required |",
        "|---:|---|---:|---|---:|---:|---:|---|",
    ]
    for bone in manifest.bones:
        parent = "—" if bone.parent_index is None else str(bone.parent_index)
        lines.append(f"| {bone.index} | `{bone.name}` | {parent} | `{bone.x:.2f}, {bone.y:.2f}` | {bone.rotation:.2f} | {bone.length:.2f} | {bone.transform_mode} | {bone.skin_required} |")
    lines.extend(["", "## 插槽", "", "| # | 名称 | 骨骼 | RGBA | setup attachment | blend |", "|---:|---|---:|---|---|---:|"])
    for slot in manifest.slots:
        lines.append(f"| {slot.index} | `{slot.name}` | {slot.bone_index} | `{slot.rgba}` | `{slot.setup_attachment or '—'}` | {slot.blend_mode} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("file", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = parse(args.file, args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(asdict(manifest), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.output.with_suffix(".md").write_text(markdown(manifest), encoding="utf-8")
    print(f"已写入：{args.output}")
    print(f"已写入：{args.output.with_suffix('.md')}")


if __name__ == "__main__":
    main()
