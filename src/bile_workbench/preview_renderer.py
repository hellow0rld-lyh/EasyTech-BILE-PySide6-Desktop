"""BILE 动画的只读预览合成器。

渲染规则只包含可从原包、解析关系和参考实现交叉验证的内容：通道保持帧、
BELE 仿射矩阵、ARGB 调制色、BMTI 锚点，以及嵌套元素的变换相乘。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from .bile_format import BileDocument, Element, Keyframe
from .xml_safety import parse_untrusted_xml

MAX_NESTING_DEPTH = 24


@dataclass(frozen=True)
class SpriteRegion:
    name: str
    x: float
    y: float
    w: float
    h: float
    refx: float
    refy: float


@dataclass(frozen=True)
class Atlas:
    image: Image.Image
    regions: dict[str, SpriteRegion]
    xml_had_declaration: bool = False
    stripped_control_chars: int = 0
    fractional_geometry_regions: int = 0
    source_image_format: str = ""


def load_atlas(xml_path: str | Path, image_path: str | Path) -> Atlas:
    """读取原包的根级 XML 片段和对应 WebP/PNG 图集。"""
    xml_text = Path(xml_path).read_text(encoding="utf-8-sig")
    # 多数资源是无单一根节点的 XML 片段；少数旧资源仍保留 XML 声明。
    # XML 声明只能位于整个文档首部，因此包装片段前必须移除它。
    fragment = xml_text.lstrip()
    # 若资源尾部附带填充 NUL，XML 解析器会拒绝它；NUL 不属于 XML 合法文本，
    # 在图集片段层面安全剔除，其余可见文本和属性保持原样。
    stripped_control_chars = sum(1 for char in fragment if ord(char) < 0x20 and char not in "\t\n\r")
    fragment = "".join(char for char in fragment if ord(char) >= 0x20 or char in "\t\n\r")
    xml_had_declaration = fragment.startswith("<?xml")
    if xml_had_declaration:
        declaration_end = fragment.find("?>")
        if declaration_end < 0:
            raise ValueError(f"XML 声明未终止：{xml_path}")
        fragment = fragment[declaration_end + 2:]
    root = parse_untrusted_xml(f"<ResourceFragment>{fragment}</ResourceFragment>", str(xml_path))
    regions: dict[str, SpriteRegion] = {}
    fractional_geometry_regions = 0
    for node in root.findall("./Images/Image"):
        values = [float(node.attrib[field]) for field in ("x", "y", "w", "h")]
        if any(not value.is_integer() for value in values):
            fractional_geometry_regions += 1
        region = SpriteRegion(
            name=node.attrib["name"],
            x=float(node.attrib["x"]),
            y=float(node.attrib["y"]),
            w=float(node.attrib["w"]),
            h=float(node.attrib["h"]),
            refx=float(node.attrib.get("refx", "0")),
            refy=float(node.attrib.get("refy", "0")),
        )
        regions[region.name] = region
        if region.name.lower().endswith(".png"):
            regions.setdefault(region.name[:-4], region)
    with Image.open(image_path) as source:
        source_image_format = source.format or ""
        image = source.convert("RGBA")
    return Atlas(image, regions, xml_had_declaration, stripped_control_chars, fractional_geometry_regions, source_image_format)


def _identity() -> tuple[float, float, float, float, float, float]:
    return 1.0, 0.0, 0.0, 1.0, 0.0, 0.0


def _keyframe_transform(keyframe: Keyframe) -> tuple[float, float, float, float, float, float]:
    # (xx, xy, yx, yy, tx, ty); point=(x,y) → (xx*x + yx*y + tx, xy*x + yy*y + ty)
    return keyframe.xx, keyframe.xy, keyframe.yx, keyframe.yy, keyframe.x, keyframe.y


def _multiply(
    parent: tuple[float, float, float, float, float, float],
    child: tuple[float, float, float, float, float, float],
) -> tuple[float, float, float, float, float, float]:
    pxx, pxy, pyx, pyy, ptx, pty = parent
    cxx, cxy, cyx, cyy, ctx, cty = child
    return (
        pxx * cxx + pyx * cxy,
        pxy * cxx + pyy * cxy,
        pxx * cyx + pyx * cyy,
        pxy * cyx + pyy * cyy,
        pxx * ctx + pyx * cty + ptx,
        pxy * ctx + pyy * cty + pty,
    )


def _apply(transform: tuple[float, float, float, float, float, float], x: float, y: float) -> tuple[float, float]:
    xx, xy, yx, yy, tx, ty = transform
    return xx * x + yx * y + tx, xy * x + yy * y + ty


def _active_frame(element: Element, channel_index: int, slot: int):
    frames = element.channels[channel_index].frames
    active = None
    for frame in frames:
        if frame.slot <= slot:
            active = frame
        else:
            break
    return active


def _multiply_rgba(parent: tuple[int, int, int, int], child: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """按通道乘以颜色，匹配嵌套 BELE 的 ARGB 调制传播。"""
    return tuple((left * right + 127) // 255 for left, right in zip(parent, child))  # type: ignore[return-value]


def child_slot_for_reference_v4(parent_slot: int, frame_slot: int, keyframe: Keyframe, child_frame_count: int) -> int:
    """参考契约：段切换时以 initial_phase 重置子动画，再按 playback_mode 推进。"""
    if child_frame_count <= 0:
        return 0
    phase = min(keyframe.initial_phase, child_frame_count - 1)
    age = max(0, parent_slot - frame_slot)
    if keyframe.playback_mode == 2:  # ManualFrameHold
        return phase
    if keyframe.playback_mode == 1:  # OneShotStop：最后一帧保持可见
        return min(phase + age, child_frame_count - 1)
    return (phase + age) % child_frame_count  # Loop；未知模式保守回退到 loop


def _modulate(image: Image.Image, rgba: tuple[int, int, int, int]) -> Image.Image:
    if rgba == (255, 255, 255, 255):
        return image
    pixels = image.load()
    output = Image.new("RGBA", image.size)
    out_pixels = output.load()
    r_mul, g_mul, b_mul, a_mul = (value / 255.0 for value in rgba)
    for y in range(image.height):
        for x in range(image.width):
            r, g, b, a = pixels[x, y]
            out_pixels[x, y] = (round(r * r_mul), round(g * g_mul), round(b * b_mul), round(a * a_mul))
    return output


def _draw_sprite(
    canvas: Image.Image,
    atlas: Atlas,
    element: Element,
    transform: tuple[float, float, float, float, float, float],
    rgba: tuple[int, int, int, int],
    origin: tuple[float, float],
) -> None:
    region = atlas.regions.get(element.name) or atlas.regions.get(f"{element.name}.png")
    if region is None or region.w <= 0 or region.h <= 0:
        return
    # 图集裁切始终使用覆盖指定浮点区域的整数像素边界；几何变换仍保留原始浮点尺寸。
    left = math.floor(region.x)
    top = math.floor(region.y)
    right = math.ceil(region.x + region.w)
    bottom = math.ceil(region.y + region.h)
    source = atlas.image.crop((left, top, right, bottom))
    source = _modulate(source, rgba)
    # 原始图集的 refx/refy 是裁切图相对局部锚点的参考点；BMTI 偏移需扣除它。
    # 当 refx/refy 为 0 时与旧逻辑完全一致；anim_status 的部分精灵依赖该修正。
    local_x = element.x - region.refx
    local_y = element.y - region.refy
    # PIL inverse affine: output -> source. Use transformed source quadrilateral and projectively paste by mesh.
    corners = [
        _apply(transform, local_x, local_y),
        _apply(transform, local_x + region.w, local_y),
        _apply(transform, local_x + region.w, local_y + region.h),
        _apply(transform, local_x, local_y + region.h),
    ]
    corners = [(x + origin[0], y + origin[1]) for x, y in corners]
    # Image.Transform.QUAD maps a rectangle to source quad, not suitable for arbitrary affine output;
    # transform the sprite itself with a forward affine matrix and alpha-composite at a padded bounding box.
    xx, xy, yx, yy, _tx, _ty = transform
    det = xx * yy - xy * yx
    if abs(det) < 1e-8:
        return
    min_x = math.floor(min(x for x, _ in corners))
    max_x = math.ceil(max(x for x, _ in corners))
    min_y = math.floor(min(y for _, y in corners))
    max_y = math.ceil(max(y for _, y in corners))
    if max_x <= 0 or max_y <= 0 or min_x >= canvas.width or min_y >= canvas.height:
        return
    # The local input starts at element.x/y. Work in output bounding-box coordinates.
    inv_xx = yy / det
    inv_xy = -yx / det
    inv_yx = -xy / det
    inv_yy = xx / det
    tx = transform[4] + origin[0]
    ty = transform[5] + origin[1]
    # source coordinate u,v from output coordinate X,Y: local = inv*(output - translation), sprite = local - pivot.
    c = inv_xx * (min_x - tx) + inv_xy * (min_y - ty) - local_x
    f = inv_yx * (min_x - tx) + inv_yy * (min_y - ty) - local_y
    transformed = source.transform(
        (max(1, max_x - min_x), max(1, max_y - min_y)),
        Image.Transform.AFFINE,
        (inv_xx, inv_xy, c, inv_yx, inv_yy, f),
        resample=Image.Resampling.BICUBIC,
    )
    canvas.alpha_composite(transformed, (min_x, min_y))


def render_sprite(atlas: Atlas, element: Element) -> tuple[Image.Image, float, float]:
    """渲染单个图片元素，并返回 crop 图像及其 refx/refy。

    BMTI.x/y 是元素相对于动画原点的偏移；独立预览中的热点原点因此位于
    `(refx - element.x, refy - element.y)`，拖动它即可直观地改变 BMTI 锚点。
    """
    region = atlas.regions.get(element.name) or atlas.regions.get(f"{element.name}.png")
    if region is None or region.w <= 0 or region.h <= 0:
        raise KeyError(f"未找到图片图集区域：{element.name}")
    left = math.floor(region.x)
    top = math.floor(region.y)
    right = math.ceil(region.x + region.w)
    bottom = math.ceil(region.y + region.h)
    return atlas.image.crop((left, top, right, bottom)).convert("RGBA"), region.refx, region.refy


def render_frame(
    document: BileDocument,
    atlas: Atlas,
    animation_name: str,
    slot: int,
    canvas_size: tuple[int, int] = (1024, 768),
    background: tuple[int, int, int, int] = (35, 38, 44, 255),
    nested_timing: str = "reference_v4",
) -> Image.Image:
    """渲染指定动画元素在整数槽位的合成帧。

    `reference_v4` 启用经参考源码与原包字段分布支持的子动画相位/模式规则；
    `legacy_global` 保留旧版所有嵌套项共用根槽位的渲染方式，供差异审计。
    """
    if nested_timing not in {"reference_v4", "legacy_global"}:
        raise ValueError(f"未知 nested_timing：{nested_timing}")
    target = next((item for item in document.animations if item.name == animation_name), None)
    if target is None:
        raise KeyError(f"未找到动画元素：{animation_name}")
    canvas = Image.new("RGBA", canvas_size, background)
    origin = (canvas_size[0] / 2.0, canvas_size[1] / 2.0)

    def visit(
        element: Element,
        parent: tuple[float, float, float, float, float, float],
        color: tuple[int, int, int, int],
        local_slot: int,
        depth: int,
        ancestry: frozenset[int],
    ) -> None:
        if depth > MAX_NESTING_DEPTH or element.index in ancestry:
            return
        if element.has_texture:
            _draw_sprite(canvas, atlas, element, parent, color, origin)
            return
        channels = reversed(element.channels) if nested_timing == "reference_v4" else element.channels
        for channel in channels:
            active = None
            for candidate in channel.frames:
                if candidate.slot <= local_slot:
                    active = candidate
                else:
                    break
            if active is None:
                continue
            for track in active.tracks:
                if track.element_index < 0 or track.element_index >= len(document.elements):
                    continue
                if track.keyframe_index < 0 or track.keyframe_index >= len(document.keyframes):
                    continue
                keyframe = document.keyframes[track.keyframe_index]
                child = document.elements[track.element_index]
                child_slot = local_slot
                if nested_timing == "reference_v4" and not child.has_texture:
                    child_slot = child_slot_for_reference_v4(local_slot, active.slot, keyframe, child.frame_count)
                visit(
                    child,
                    _multiply(parent, _keyframe_transform(keyframe)),
                    _multiply_rgba(color, keyframe.rgba),
                    child_slot,
                    depth + 1,
                    ancestry | {element.index},
                )

    visit(target, _identity(), (255, 255, 255, 255), slot, 0, frozenset())
    return canvas
