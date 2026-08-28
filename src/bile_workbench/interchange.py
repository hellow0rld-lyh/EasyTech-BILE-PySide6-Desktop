"""BILE 的 AI 中转 JSON 与保守写回补丁。

设计目标：允许任何 AI/外部工具生成可审计的编辑说明，而不是直接让其改写
不透明二进制字段。当前补丁层严格限制为不改变记录数和块结构的字段。
"""
from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path
from typing import Any

from .bile_format import BileDocument, BileFormatError, parse_bytes, parse_file

SCHEMA = "bile-workbench.interchange/v1"


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
    """导出完整可读时间线，供 AI 生成提案或人工版本控制；不输出不透明地址字段。"""
    source = Path(bin_path)
    document = parse_file(source)
    payload = {
        "schema": SCHEMA,
        "kind": "full-document",
        "source": {"file": source.name, "sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "version": document.header.version, "fps": document.header.fps},
        "sprites": [{"index": e.index, "name": e.name, "anchor": [e.x, e.y]} for e in document.sprites],
        "animations": [
            {
                "index": e.index,
                "name": e.name,
                "frame_count": e.frame_count,
                "channels": [
                    [{"slot": frame.slot, "tracks": [{"keyframe": track.keyframe_index, "element": track.element_index} for track in frame.tracks]} for frame in channel.frames]
                    for channel in e.channels
                ],
            }
            for e in document.animations
        ],
        "keyframes": [_keyframe_dict(index, keyframe) for index, keyframe in enumerate(document.keyframes)],
        "patch_template": {
            "schema": SCHEMA,
            "kind": "patch",
            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "keyframes": [{"index": 0, "transform": {"x": 0.0, "y": 0.0}, "argb": "0xFFFFFFFF", "initial_phase": 0}],
            "elements": [{"index": 0, "anchor": [0.0, 0.0]}],
        },
    }
    Path(output_path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _set_f32(data: bytearray, offset: int, value: Any, label: str) -> None:
    if not isinstance(value, (int, float)):
        raise BileFormatError(f"{label} 必须是数字")
    struct.pack_into("<f", data, offset, float(value))


def _parse_u32(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 0xFFFFFFFF:
        raise BileFormatError(f"{label} 必须是 0 到 4294967295 的整数")
    return value


def _parse_argb(value: Any) -> int:
    if isinstance(value, int):
        return value & 0xFFFFFFFF
    if isinstance(value, str) and value.lower().startswith("0x"):
        return int(value, 16) & 0xFFFFFFFF
    raise BileFormatError("argb 必须是 u32 整数或 0xAARRGGBB 字符串")


def apply_patch(source_path: str | Path, patch_path: str | Path, output_path: str | Path) -> BileDocument:
    """应用仅限已验证字段的非结构化补丁，并在写出前重新解析验证。"""
    source = Path(source_path)
    original = source.read_bytes()
    document = parse_bytes(original)
    if document.header.version != 4 and document.header.version != 3:
        raise BileFormatError(f"BILE v{document.header.version} 当前仅支持只读解析、预览和导出；保守补丁写入仅开放给经写回验证的 v3/v4 六节容器")
    patch = json.loads(Path(patch_path).read_text(encoding="utf-8"))
    if patch.get("schema") != SCHEMA or patch.get("kind") != "patch":
        raise BileFormatError(f"仅接受 {SCHEMA} 的 patch 文档")
    expected_hash = patch.get("source_sha256")
    actual_hash = hashlib.sha256(original).hexdigest()
    if expected_hash != actual_hash:
        raise BileFormatError("补丁 source_sha256 与当前 BIN 不一致；为避免错位写入，已拒绝保存")
    data = bytearray(original)
    bele = document.sections["BELE"]
    bmti = document.sections["BMTI"]
    allowed_transform = {"xx": 0, "xy": 4, "yx": 8, "yy": 12, "x": 16, "y": 20}
    for change in patch.get("keyframes", []):
        index = change.get("index")
        if not isinstance(index, int) or not 0 <= index < len(document.keyframes):
            raise BileFormatError(f"无效关键帧索引：{index}")
        offset = bele.payload_offset + index * 44
        transform = change.get("transform", {})
        if not isinstance(transform, dict):
            raise BileFormatError("keyframes[].transform 必须是对象")
        for field, local_offset in allowed_transform.items():
            if field in transform:
                _set_f32(data, offset + local_offset, transform[field], f"keyframes[{index}].{field}")
        if "argb" in change:
            struct.pack_into("<I", data, offset + 24, _parse_argb(change["argb"]))
        if "initial_phase" in change:
            # +0x1C 已由实际子动画轨道和独立播放器思路共同支持；不改变结构。
            struct.pack_into("<I", data, offset + 28, _parse_u32(change["initial_phase"], f"keyframes[{index}].initial_phase"))
        if "playback_mode" in change:
            raise BileFormatError("playback_mode=1/2 的子动画语义尚未完成原包实证，保守补丁禁止写入")
    for change in patch.get("elements", []):
        index = change.get("index")
        if not isinstance(index, int) or not 0 <= index < len(document.elements):
            raise BileFormatError(f"无效元素索引：{index}")
        offset = bmti.payload_offset + index * 56
        anchor = change.get("anchor")
        if anchor is not None:
            if not isinstance(anchor, list) or len(anchor) != 2:
                raise BileFormatError("elements[].anchor 必须是 [x, y]")
            _set_f32(data, offset + 8, anchor[0], f"elements[{index}].anchor[0]")
            _set_f32(data, offset + 12, anchor[1], f"elements[{index}].anchor[1]")
        # 名称仅允许相同 UTF-8 字节长度的原位替换，避免重排 BRTS 偏移。
        if "name" in change:
            name = change["name"]
            if not isinstance(name, str):
                raise BileFormatError("elements[].name 必须是字符串")
            old = document.elements[index].name.encode("utf-8")
            new = name.encode("utf-8")
            if len(new) != len(old):
                raise BileFormatError("当前保守补丁只支持等 UTF-8 字节长度的改名；请使用完整重建流程")
            start = document.sections["BRTS"].payload_offset + document.elements[index].name_offset
            data[start:start + len(old)] = new
    checked = parse_bytes(bytes(data))
    Path(output_path).write_bytes(bytes(data))
    return checked
