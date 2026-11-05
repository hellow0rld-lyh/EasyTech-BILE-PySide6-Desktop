"""BILE 的 AI 中转 JSON 与保守写回补丁。

新生成的补丁包含 expected-old 字段值；旧版 v1 补丁仍可通过源 SHA-256 绑定
继续使用。所有 BIN 候选均经过固定长度字段门禁、完整重解析和事务式发布。
"""
from __future__ import annotations

import json
import math
import struct
from pathlib import Path
from typing import Any

from .bile_format import BileDocument, BileFormatError
from .raw_image import RawBileImage
from .safe_mutation import (
    BileMutationBuffer,
    BileMutationReport,
    publish_verified_candidate,
)

SCHEMA = "bile-workbench.interchange/v1"
_MISSING = object()


def _keyframe_dict(index: int, keyframe) -> dict[str, Any]:
    return {
        "index": index,
        "transform": {
            "xx": keyframe.xx, "xy": keyframe.xy, "yx": keyframe.yx,
            "yy": keyframe.yy, "x": keyframe.x, "y": keyframe.y,
        },
        "argb": f"0x{keyframe.argb:08X}",
        "initial_phase": keyframe.initial_phase,
        "playback_mode": keyframe.playback_mode,
    }


def export_interchange(bin_path: str | Path, output_path: str | Path) -> None:
    """导出完整可读时间线和带 expected-old 的补丁模板。"""
    source = Path(bin_path)
    image = RawBileImage.read(source)
    document = image.document
    keyframe_template: list[dict[str, Any]] = []
    if document.keyframes:
        first = document.keyframes[0]
        keyframe_template.append({
            "index": 0,
            "transform": {"x": 0.0},
            "expected": {"transform": {"x": first.x}},
        })
    element_template: list[dict[str, Any]] = []
    if document.elements:
        first_element = document.elements[0]
        element_template.append({
            "index": 0,
            "anchor": [0.0, 0.0],
            "expected": {"anchor": [first_element.x, first_element.y]},
        })
    payload = {
        "schema": SCHEMA,
        "kind": "full-document",
        "source": {
            "file": source.name,
            "sha256": image.sha256,
            "version": document.header.version,
            "fps": document.header.fps,
        },
        "sprites": [{"index": e.index, "name": e.name, "anchor": [e.x, e.y]} for e in document.sprites],
        "animations": [
            {
                "index": e.index,
                "name": e.name,
                "frame_count": e.frame_count,
                "channels": [
                    [
                        {
                            "slot": frame.slot,
                            "tracks": [
                                {"keyframe": track.keyframe_index, "element": track.element_index}
                                for track in frame.tracks
                            ],
                        }
                        for frame in channel.frames
                    ]
                    for channel in e.channels
                ],
            }
            for e in document.animations
        ],
        "keyframes": [
            _keyframe_dict(index, keyframe)
            for index, keyframe in enumerate(document.keyframes)
        ],
        "patch_template": (
            {
                "schema": SCHEMA,
                "kind": "patch",
                "source_sha256": image.sha256,
                "keyframes": keyframe_template,
                "elements": element_template,
            }
            if document.header.version in (3, 4)
            else None
        ),
    }
    Path(output_path).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _pack_f32(value: Any, label: str) -> bytes:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise BileFormatError(f"{label} 必须是有限数字")
    try:
        number = float(value)
    except (OverflowError, ValueError) as exc:
        raise BileFormatError(f"{label} 超出有限 float32 范围") from exc
    if not math.isfinite(number):
        raise BileFormatError(f"{label} 必须是有限数字")
    try:
        packed = struct.pack("<f", number)
    except (OverflowError, struct.error) as exc:
        raise BileFormatError(f"{label} 超出 float32 范围") from exc
    if not math.isfinite(struct.unpack("<f", packed)[0]):
        raise BileFormatError(f"{label} 超出有限 float32 范围")
    return packed


def _parse_u32(value: Any, label: str) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or not 0 <= value <= 0xFFFFFFFF
    ):
        raise BileFormatError(f"{label} 必须是 0 到 4294967295 的整数")
    return value


def _parse_argb(value: Any) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        if 0 <= value <= 0xFFFFFFFF:
            return value
        raise BileFormatError("argb 整数必须位于 u32 范围")
    if isinstance(value, str) and value.lower().startswith("0x"):
        digits = value[2:]
        if not 1 <= len(digits) <= 8 or any(char not in "0123456789abcdefABCDEF" for char in digits):
            raise BileFormatError("argb 必须是 0xAARRGGBB 格式的 u32 值")
        return int(digits, 16)
    raise BileFormatError("argb 必须是 u32 整数或 0xAARRGGBB 字符串")


def _expected_mapping(change: dict[str, Any], allowed: set[str], label: str) -> dict[str, Any] | None:
    if "expected" not in change:
        return None
    expected = change["expected"]
    if not isinstance(expected, dict):
        raise BileFormatError(f"{label}.expected 必须是对象")
    unknown = set(expected) - allowed
    if unknown:
        raise BileFormatError(f"{label}.expected 包含不允许的字段：{sorted(unknown)}")
    return expected


def _check_expected_bytes(
    buffer: BileMutationBuffer,
    offset: int,
    expected_bytes: bytes,
    label: str,
) -> None:
    if buffer.read(offset, len(expected_bytes)) != expected_bytes:
        raise BileFormatError(f"{label} expected-old 与源 BIN 当前值不一致")


def _set_f32(
    buffer: BileMutationBuffer,
    offset: int,
    value: Any,
    label: str,
    expected_value: Any = _MISSING,
) -> None:
    if expected_value is not _MISSING:
        _check_expected_bytes(buffer, offset, _pack_f32(expected_value, f"{label}.expected"), label)
    buffer.replace(offset, _pack_f32(value, label), label)


def _require_index(change: dict[str, Any], upper_bound: int, label: str) -> int:
    index = change.get("index")
    if (
        not isinstance(index, int)
        or isinstance(index, bool)
        or not 0 <= index < upper_bound
    ):
        raise BileFormatError(f"{label} 索引无效：{index}")
    return index


def apply_patch_report(
    source_path: str | Path,
    patch_path: str | Path,
    output_path: str | Path,
    *,
    overwrite: bool = False,
) -> BileMutationReport:
    """应用受限补丁并返回输入/输出哈希与精确 changed-byte 证据。"""
    source = Path(source_path)
    image = RawBileImage.read(source)
    document = image.document
    if document.header.version not in (3, 4):
        raise BileFormatError(
            f"BILE v{document.header.version} 当前只读；保守补丁写入仅开放给 v3/v4"
        )

    patch = json.loads(Path(patch_path).read_text(encoding="utf-8"))
    if not isinstance(patch, dict):
        raise BileFormatError("补丁根节点必须是 JSON 对象")
    allowed_top_level = {"schema", "kind", "source_sha256", "keyframes", "elements"}
    unknown_top_level = set(patch) - allowed_top_level
    if unknown_top_level:
        raise BileFormatError(f"补丁包含不允许的顶层字段：{sorted(unknown_top_level)}")
    if patch.get("schema") != SCHEMA or patch.get("kind") != "patch":
        raise BileFormatError(f"仅接受 {SCHEMA} 的 patch 文档")
    expected_hash = patch.get("source_sha256")
    if not isinstance(expected_hash, str) or image.sha256 != expected_hash.lower():
        raise BileFormatError("补丁 source_sha256 与当前 BIN 不一致；为避免错位写入，已拒绝保存")

    keyframe_changes = patch.get("keyframes", [])
    element_changes = patch.get("elements", [])
    if not isinstance(keyframe_changes, list) or not isinstance(element_changes, list):
        raise BileFormatError("keyframes 和 elements 必须是数组")

    buffer = BileMutationBuffer(image)
    bele = document.sections["BELE"]
    bmti = document.sections["BMTI"]
    allowed_transform = {"xx": 0, "xy": 4, "yx": 8, "yy": 12, "x": 16, "y": 20}
    seen_keyframes: set[int] = set()
    for change in keyframe_changes:
        if not isinstance(change, dict):
            raise BileFormatError("keyframes[] 必须是对象")
        unknown = set(change) - {
            "index", "transform", "argb", "initial_phase", "playback_mode", "expected"
        }
        if unknown:
            raise BileFormatError(f"keyframes[] 包含不允许的字段：{sorted(unknown)}")
        if "playback_mode" in change:
            raise BileFormatError(
                "playback_mode 的游戏内扰动实证尚未完成，保守补丁禁止写入"
            )
        index = _require_index(change, len(document.keyframes), "keyframes[]")
        if index in seen_keyframes:
            raise BileFormatError(f"keyframes[] 不允许重复修改同一记录：{index}")
        seen_keyframes.add(index)
        offset = bele.payload_offset + index * 44
        expected = _expected_mapping(
            change, {"transform", "argb", "initial_phase"}, f"keyframes[{index}]"
        )
        transform = change.get("transform", {})
        if not isinstance(transform, dict):
            raise BileFormatError("keyframes[].transform 必须是对象")
        unknown_transform = set(transform) - set(allowed_transform)
        if unknown_transform:
            raise BileFormatError(f"transform 包含不允许的字段：{sorted(unknown_transform)}")
        expected_transform: dict[str, Any] = {}
        if expected is not None:
            raw_expected_transform = expected.get("transform", {})
            if not isinstance(raw_expected_transform, dict):
                raise BileFormatError("keyframes[].expected.transform 必须是对象")
            if set(raw_expected_transform) != set(transform):
                raise BileFormatError("expected.transform 必须与本次修改的 transform 字段完全对应")
            expected_transform = raw_expected_transform
        for field, local_offset in allowed_transform.items():
            if field in transform:
                _set_f32(
                    buffer,
                    offset + local_offset,
                    transform[field],
                    f"keyframes[{index}].{field}",
                    expected_transform[field] if expected is not None else _MISSING,
                )
        for field, field_offset, parser, packer in (
            ("argb", 24, _parse_argb, lambda value: struct.pack("<I", value)),
            ("initial_phase", 28, lambda value: _parse_u32(value, "initial_phase"), lambda value: struct.pack("<I", value)),
        ):
            if field in change:
                value = parser(change[field])
                expected_value = expected.get(field, _MISSING) if expected is not None else _MISSING
                if expected is not None and expected_value is _MISSING:
                    raise BileFormatError(f"keyframes[{index}].expected 缺少 {field}")
                if expected_value is not _MISSING:
                    _check_expected_bytes(
                        buffer,
                        offset + field_offset,
                        packer(parser(expected_value)),
                        f"keyframes[{index}].{field}",
                    )
                buffer.replace(
                    offset + field_offset,
                    packer(value),
                    f"keyframes[{index}].{field}",
                )
            elif expected is not None and field in expected:
                raise BileFormatError(f"keyframes[{index}].expected.{field} 没有对应修改")

    seen_elements: set[int] = set()
    for change in element_changes:
        if not isinstance(change, dict):
            raise BileFormatError("elements[] 必须是对象")
        unknown = set(change) - {"index", "anchor", "name", "expected"}
        if unknown:
            raise BileFormatError(f"elements[] 包含不允许的字段：{sorted(unknown)}")
        index = _require_index(change, len(document.elements), "elements[]")
        if index in seen_elements:
            raise BileFormatError(f"elements[] 不允许重复修改同一记录：{index}")
        seen_elements.add(index)
        offset = bmti.payload_offset + index * 56
        expected = _expected_mapping(
            change, {"anchor", "name"}, f"elements[{index}]"
        )
        if "anchor" in change:
            anchor = change["anchor"]
            if not isinstance(anchor, list) or len(anchor) != 2:
                raise BileFormatError("elements[].anchor 必须是 [x, y]")
            expected_anchor = expected.get("anchor", _MISSING) if expected is not None else _MISSING
            if expected is not None and (
                not isinstance(expected_anchor, list) or len(expected_anchor) != 2
            ):
                raise BileFormatError("elements[].expected.anchor 必须是 [x, y]")
            _set_f32(
                buffer,
                offset + 8,
                anchor[0],
                f"elements[{index}].anchor[0]",
                expected_anchor[0] if expected_anchor is not _MISSING else _MISSING,
            )
            _set_f32(
                buffer,
                offset + 12,
                anchor[1],
                f"elements[{index}].anchor[1]",
                expected_anchor[1] if expected_anchor is not _MISSING else _MISSING,
            )
        elif expected is not None and "anchor" in expected:
            raise BileFormatError(f"elements[{index}].expected.anchor 没有对应修改")

        if "name" in change:
            name = change["name"]
            if not isinstance(name, str) or "\0" in name:
                raise BileFormatError("elements[].name 必须是非空字节序列且不得包含 NUL")
            old_name = document.elements[index].name
            expected_name = expected.get("name", _MISSING) if expected is not None else _MISSING
            if expected is not None and expected_name is _MISSING:
                raise BileFormatError(f"elements[{index}].expected 缺少 name")
            if expected_name is not _MISSING and expected_name != old_name:
                raise BileFormatError(f"elements[{index}].name expected-old 与源 BIN 当前值不一致")
            name_users = [
                element.index
                for element in document.elements
                if element.name_offset == document.elements[index].name_offset
            ]
            if len(name_users) != 1:
                raise BileFormatError(
                    f"elements[{index}].name 与其它元素共享 BRTS 字符串偏移 {name_users}；拒绝产生多元素副作用"
                )
            old = old_name.encode("utf-8")
            new = name.encode("utf-8")
            if len(new) != len(old):
                raise BileFormatError(
                    "当前保守补丁只支持等 UTF-8 字节长度的改名；请使用完整重建流程"
                )
            start = document.sections["BRTS"].payload_offset + document.elements[index].name_offset
            buffer.replace(start, new, f"elements[{index}].name")
        elif expected is not None and "name" in expected:
            raise BileFormatError(f"elements[{index}].expected.name 没有对应修改")

    return publish_verified_candidate(
        source,
        output_path,
        buffer.to_bytes(),
        image.sha256,
        buffer.expected_changed_offsets,
        overwrite=overwrite,
    )


def apply_patch(
    source_path: str | Path,
    patch_path: str | Path,
    output_path: str | Path,
    *,
    overwrite: bool = False,
) -> BileDocument:
    """应用保守补丁并返回重新解析后的文档；源 BIN 永远不会被原位覆盖。"""
    return apply_patch_report(
        source_path, patch_path, output_path, overwrite=overwrite
    ).document
