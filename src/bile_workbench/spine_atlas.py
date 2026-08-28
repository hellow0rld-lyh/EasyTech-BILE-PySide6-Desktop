"""Spine ATLAS 的只读解析与单区域预览，覆盖欧7传统与征2新式字段方言。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image


class SpineAtlasError(ValueError):
    pass


@dataclass(frozen=True)
class SpineAtlasRegion:
    name: str
    x: int
    y: int
    width: int
    height: int
    original_width: int
    original_height: int
    offset_x: int
    offset_y: int
    rotation: int
    index: int


@dataclass(frozen=True)
class SpineAtlas:
    source_path: Path
    image_path: Path
    image_size: tuple[int, int]
    regions: tuple[SpineAtlasRegion, ...]
    page_name: str | None
    dialect: str


def _pair(value: str, label: str) -> tuple[int, int]:
    try:
        values = tuple(int(part.strip()) for part in value.split(","))
    except ValueError as exc:
        raise SpineAtlasError(f"{label} 不是整数对：{value!r}") from exc
    if len(values) != 2:
        raise SpineAtlasError(f"{label} 不是二元值：{value!r}")
    return values


def _quad(value: str, label: str) -> tuple[int, int, int, int]:
    try:
        values = tuple(int(part.strip()) for part in value.split(","))
    except ValueError as exc:
        raise SpineAtlasError(f"{label} 不是整数四元组：{value!r}") from exc
    if len(values) != 4:
        raise SpineAtlasError(f"{label} 不是四元值：{value!r}")
    return values


def _rotation(value: str) -> int:
    normalized = value.strip().lower()
    if normalized in {"false", "0"}:
        return 0
    if normalized == "true":
        return 90
    try:
        result = int(normalized)
    except ValueError as exc:
        raise SpineAtlasError(f"rotate 不可识别：{value!r}") from exc
    if result not in {0, 90, 180, 270}:
        raise SpineAtlasError(f"rotate 不在支持角度：{result}")
    return result


def _image_for(atlas_path: Path, page_name: str | None) -> Path:
    candidates = []
    if page_name:
        candidates.append(atlas_path.parent / page_name)
    candidates.extend(atlas_path.with_suffix(extension) for extension in (".png", ".webp"))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise SpineAtlasError(f"未找到 ATLAS 图像：{atlas_path.name}")


def load_spine_atlas(path: Path) -> SpineAtlas:
    raw = path.read_text(encoding="utf-8-sig", errors="strict").replace("\r\n", "\n")
    lines = [line.strip() for line in raw.split("\n") if line.strip()]
    if not lines:
        raise SpineAtlasError("ATLAS 为空")
    properties: dict[str, str] = {}
    page_name: str | None = None
    regions: list[SpineAtlasRegion] = []
    position = 0
    if ":" not in lines[0]:
        page_name = lines[0]
        position = 1
    page_properties = {"size", "format", "filter", "repeat", "pma", "scale"}
    region_properties = {"rotate", "xy", "size", "orig", "offset", "index", "bounds", "offsets", "split", "pad"}
    while position < len(lines) and ":" in lines[position]:
        key, value = (part.strip() for part in lines[position].split(":", 1))
        if key not in page_properties:
            break
        properties[key] = value
        position += 1
    if "size" not in properties:
        raise SpineAtlasError("ATLAS 缺少页面 size")
    atlas_width, atlas_height = _pair(properties["size"], "page.size")
    uses_bounds_offsets = False
    while position < len(lines):
        name = lines[position]
        if ":" in name:
            raise SpineAtlasError(f"区域名称意外为属性：{name!r}")
        position += 1
        fields: dict[str, str] = {}
        while position < len(lines) and ":" in lines[position]:
            key, value = (part.strip() for part in lines[position].split(":", 1))
            if key not in region_properties:
                raise SpineAtlasError(f"区域 {name!r} 的未知字段：{key}")
            fields[key] = value
            position += 1
        rotation = _rotation(fields.get("rotate", "false"))
        if "bounds" in fields:
            uses_bounds_offsets = True
            x, y, logical_width, logical_height = _quad(fields["bounds"], f"region[{name}].bounds")
            # 新式 atlas 的 rotate 后 bounds 以未旋转逻辑宽高表示，页面中存储矩形需交换宽高。
            width, height = (logical_height, logical_width) if rotation in {90, 270} else (logical_width, logical_height)
        else:
            x, y = _pair(fields.get("xy", ""), f"region[{name}].xy")
            width, height = _pair(fields.get("size", ""), f"region[{name}].size")
            logical_width, logical_height = width, height
        if not width > 0 or not height > 0 or x < 0 or y < 0 or x + width > atlas_width or y + height > atlas_height:
            raise SpineAtlasError(f"区域 {name!r} 超出图集边界：{x},{y},{width},{height} / {atlas_width},{atlas_height}")
        if "offsets" in fields:
            uses_bounds_offsets = True
            offset_x, offset_y, original_width, original_height = _quad(fields["offsets"], f"region[{name}].offsets")
        else:
            original_width, original_height = _pair(fields.get("orig", fields.get("size", f"{logical_width},{logical_height}")), f"region[{name}].orig")
            offset_x, offset_y = _pair(fields.get("offset", "0,0"), f"region[{name}].offset")
        index = int(fields.get("index", "-1"))
        regions.append(SpineAtlasRegion(name, x, y, width, height, original_width, original_height, offset_x, offset_y, rotation, index))
    dialect = "bounds-offsets" if uses_bounds_offsets else "xy-size-orig-offset"
    image_path = _image_for(path, page_name)
    with Image.open(image_path) as image:
        image_size = image.size
    if image_size != (atlas_width, atlas_height):
        raise SpineAtlasError(f"ATLAS 页面大小 {atlas_width}×{atlas_height} 与图像 {image_size[0]}×{image_size[1]} 不一致")
    if not regions:
        raise SpineAtlasError("ATLAS 没有区域")
    return SpineAtlas(path, image_path, image_size, tuple(regions), page_name, dialect)


def render_region(atlas: SpineAtlas, name: str) -> Image.Image:
    region = next((item for item in atlas.regions if item.name == name), None)
    if region is None:
        raise SpineAtlasError(f"区域不存在：{name}")
    with Image.open(atlas.image_path) as source:
        crop = source.convert("RGBA").crop((region.x, region.y, region.x + region.width, region.y + region.height))
    if region.rotation:
        # Spine atlas 中 rotate 表示在页面内逆时针存储；预览时顺时针还原。
        crop = crop.rotate(-region.rotation, expand=True)
    canvas = Image.new("RGBA", (max(region.original_width, crop.width), max(region.original_height, crop.height)), (0, 0, 0, 0))
    y = canvas.height - crop.height - region.offset_y
    canvas.alpha_composite(crop, (region.offset_x, max(0, y)))
    return canvas
