#!/usr/bin/env python3
"""只读验证 BILE BIN、根级 XML 片段与 WebP 图集的跨文件约束。"""
from __future__ import annotations

import json
import struct
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "sample_assets"
OUT_JSON = ROOT / "research" / "triplet_validation.json"
OUT_MD = ROOT / "research" / "triplet_validation.md"


@dataclass(frozen=True)
class Chunk:
    tag: str
    offset: int
    total_size: int
    count: int | None
    payload_offset: int
    payload: bytes


def u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def parse_chunks(data: bytes) -> list[Chunk]:
    if len(data) < 20 or data[:4] != b"BILE":
        raise ValueError("缺少 BILE 头")
    if u32(data, 8) + 20 != len(data):
        raise ValueError("文件长度字段不匹配")
    cursor = 20
    chunks: list[Chunk] = []
    for expected in ("BELE", "BXDI", "BMRF", "BYAL", "BMTI", "BRTS"):
        tag = data[cursor:cursor + 4].decode("ascii", "replace")
        if tag != expected:
            raise ValueError(f"偏移 0x{cursor:X} 预期 {expected}，实际 {tag}")
        total = u32(data, cursor + 4)
        if total < 12 or cursor + total > len(data):
            raise ValueError(f"{tag} 的块长度越界")
        if tag == "BRTS":
            count = None
            payload_offset = cursor + 12
        else:
            count = u32(data, cursor + 8)
            payload_offset = cursor + 16
        chunks.append(Chunk(tag, cursor, total, count, payload_offset, data[payload_offset:cursor + total]))
        cursor += total
    if cursor != len(data):
        raise ValueError(f"容器末尾存在 {len(data) - cursor} 个未解析字节")
    return chunks


def parse_xml_fragment(path: Path) -> tuple[str, list[dict[str, int | str]]]:
    text = path.read_text(encoding="utf-8-sig")
    root = ET.fromstring(f"<ResourceFragment>{text}</ResourceFragment>")
    texture = root.find("Texture")
    if texture is None or "name" not in texture.attrib:
        raise ValueError("XML 缺少 <Texture name=.../>")
    images = []
    for image in root.findall("./Images/Image"):
        images.append(
            {
                "name": image.attrib["name"],
                "x": int(image.attrib["x"]),
                "y": int(image.attrib["y"]),
                "w": int(image.attrib["w"]),
                "h": int(image.attrib["h"]),
                "refx": int(image.attrib.get("refx", "0")),
                "refy": int(image.attrib.get("refy", "0")),
            }
        )
    return texture.attrib["name"], images


def string_offsets(payload: bytes) -> dict[int, str]:
    strings: dict[int, str] = {}
    cursor = 0
    while cursor < len(payload):
        ending = payload.find(b"\0", cursor)
        if ending < 0:
            raise ValueError("BRTS 缺失 NUL 终止符")
        if ending > cursor:
            strings[cursor] = payload[cursor:ending].decode("utf-8")
        cursor = ending + 1
    return strings


def validate(stem: str) -> dict:
    bin_path = ASSETS / f"{stem}.bin"
    xml_path = ASSETS / f"{stem}.xml"
    webp_path = ASSETS / f"{stem}.webp"
    data = bin_path.read_bytes()
    chunks = parse_chunks(data)
    by_tag = {chunk.tag: chunk for chunk in chunks}
    texture_name, sprites = parse_xml_fragment(xml_path)
    with Image.open(webp_path) as image:
        atlas_size = image.size
    strings = string_offsets(by_tag["BRTS"].payload)
    bmti = by_tag["BMTI"]
    assert bmti.count is not None
    if len(bmti.payload) != bmti.count * 56:
        raise ValueError("BMTI 负载长度与 56 字节记录宽度不匹配")
    items = []
    errors: list[str] = []
    for index in range(bmti.count):
        offset = index * 56
        record = bmti.payload[offset:offset + 56]
        item_index = u32(record, 0)
        name_offset = u32(record, 4)
        kind = u32(record, 24)
        name = strings.get(name_offset)
        if item_index != index:
            errors.append(f"BMTI[{index}] 的索引字段为 {item_index}")
        if name is None:
            errors.append(f"BMTI[{index}] 的名称偏移 0x{name_offset:X} 不在 BRTS 项起点")
        items.append({"index": index, "name_offset": name_offset, "name": name, "kind": kind})
    sprite_names = {str(sprite["name"]).rsplit(".", 1)[0] for sprite in sprites}
    bmt_sprite_names = {str(item["name"]) for item in items if item["kind"] == 1 and item["name"] is not None}
    atlas_errors = []
    for sprite in sprites:
        if sprite["x"] < 0 or sprite["y"] < 0 or sprite["x"] + sprite["w"] > atlas_size[0] or sprite["y"] + sprite["h"] > atlas_size[1]:
            atlas_errors.append(str(sprite["name"]))
    if texture_name != f"{stem}.png":
        errors.append(f"Texture 名称 {texture_name} 与预期 {stem}.png 不符")
    warnings: list[str] = []
    if sprite_names != bmt_sprite_names:
        missing = sorted(sprite_names - bmt_sprite_names)
        extra = sorted(bmt_sprite_names - sprite_names)
        if missing:
            errors.append(f"XML 精灵在 BMTI 图片项中缺失：{missing}")
        if extra:
            warnings.append(f"BMTI 存在 XML 未列出的内部/遗留图片项：{extra}")
    chunk_view = []
    widths = {"BELE": 44, "BXDI": 8, "BMRF": 8, "BYAL": 8, "BMTI": 56}
    for chunk in chunks:
        item = {"tag": chunk.tag, "offset": chunk.offset, "total_size": chunk.total_size}
        if chunk.count is not None:
            item["count"] = chunk.count
            item["record_width"] = widths[chunk.tag]
            item["width_ok"] = len(chunk.payload) == chunk.count * widths[chunk.tag]
        else:
            item["utf8_string_count"] = len(strings)
        chunk_view.append(item)
    return {
        "stem": stem,
        "ok": not errors and not atlas_errors,
        "errors": errors,
        "atlas_bounds_errors": atlas_errors,
        "warnings": warnings,
        "header": {"version": u32(data, 4), "payload_size": u32(data, 8), "header_size": u16(data, 12), "section_count": u16(data, 14)},
        "atlas": {"path": webp_path.name, "width": atlas_size[0], "height": atlas_size[1], "texture_declared_name": texture_name},
        "xml_sprite_count": len(sprites),
        "bile": {"chunks": chunk_view, "strings": strings, "items": items},
        "animation_item_count": sum(item["kind"] == 0 for item in items),
        "image_item_count": sum(item["kind"] == 1 for item in items),
    }


def main() -> int:
    stems = [path.stem for path in sorted(ASSETS.glob("anim_*.bin"))]
    results = [validate(stem) for stem in stems]
    OUT_JSON.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# 动画三件套交叉验证", "", "> 本验证器仅读取原文件，不进行重编码或写回。BMTI 中可存在 XML 未列出的内部/遗留图片项；该情形作为警告保留，不阻断通过。", "", "| 资源 | 结果 | 图集 | XML 精灵 | BIN 图像项 | BIN 动画项 | BRTS 字符串 | 警告 |", "|---|---|---:|---:|---:|---:|---:|---|"]
    for result in results:
        status = "通过" if result["ok"] else "失败"
        lines.append(f"| `{result['stem']}` | **{status}** | `{result['atlas']['width']} × {result['atlas']['height']}` | `{result['xml_sprite_count']}` | `{result['image_item_count']}` | `{result['animation_item_count']}` | `{len(result['bile']['strings'])}` | `{'；'.join(result['warnings']) or '—'}` |")
    lines.append("")
    all_ok = all(result["ok"] for result in results)
    lines.append(f"**总体结果：{'全部通过' if all_ok else '存在失败'}**。")
    if not all_ok:
        lines.append("")
        lines.append("| 资源 | 失败信息 |")
        lines.append("|---|---|")
        for result in results:
            if not result["ok"]:
                problems = result["errors"] + result["atlas_bounds_errors"]
                lines.append(f"| `{result['stem']}` | `{'；'.join(problems)}` |")
    lines.append("")
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(OUT_MD)
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
