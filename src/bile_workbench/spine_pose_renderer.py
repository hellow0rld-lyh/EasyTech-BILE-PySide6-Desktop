"""将严格只读的 Spine pose 投影绘制为 ATLAS region 分层预览。"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from PIL import Image

from .spine_atlas import SpineAtlas, render_region
from .spine_mesh_renderer import rasterize_mesh
from .spine_pose import MeshPoseLayer, PoseLayer, PoseProjection
from .spine_two_color_composite import TwoColorCompositeError, compose_two_color_straight_alpha


@dataclass(frozen=True)
class PoseRender:
    image: Image.Image
    rendered_layer_count: int
    diagnostics: tuple[str, ...]


def _atlas_region_name(atlas: SpineAtlas, path: str) -> str | None:
    names = {item.name for item in atlas.regions}
    candidates = tuple(dict.fromkeys((path, path.removeprefix("images/"), path.rsplit("/", 1)[-1])))
    matches = [item for item in candidates if item in names]
    return matches[0] if len(matches) == 1 else None


def _apply_light_rgba(source: Image.Image, rgba: tuple[float, float, float, float]) -> Image.Image:
    """应用 Spine light tint；Pillow 合成层尚不实现 dark/two-color 或非 normal blend。"""
    if rgba == (1.0, 1.0, 1.0, 1.0):
        return source
    red, green, blue, alpha = source.convert("RGBA").split()
    factors = tuple(max(0.0, min(1.0, value)) for value in rgba)
    return Image.merge(
        "RGBA",
        (
            red.point(lambda value: round(value * factors[0])),
            green.point(lambda value: round(value * factors[1])),
            blue.point(lambda value: round(value * factors[2])),
            alpha.point(lambda value: round(value * factors[3])),
        ),
    )


def _straight_alpha_evidence_is_sufficient(source: Image.Image) -> bool:
    """仅接受全不透明 source，或半透明像素中 RGB 明确高于 alpha 的 straight-alpha 证据。"""
    rgba = np.asarray(source.convert("RGBA"), dtype=np.uint8)
    alpha = rgba[..., 3]
    partial = (alpha > 0) & (alpha < 255)
    if not bool(partial.any()):
        return True
    return bool((partial & np.any(rgba[..., :3] > alpha[..., None], axis=2)).any())


def _apply_slot_tint(
    source: Image.Image,
    light_rgba: tuple[float, float, float, float],
    dark_rgb: tuple[float, float, float] | None,
    blend_mode: int,
) -> tuple[Image.Image, str | None]:
    """以严格前置条件使用 two-color；不满足时只执行既有 light tint。"""
    if dark_rgb is None or dark_rgb == (0.0, 0.0, 0.0):
        return _apply_light_rgba(source, light_rgba), None
    if blend_mode != 0:
        return _apply_light_rgba(source, light_rgba), "dark/two-color 仅支持 verified straight-alpha 的 normal blend；当前 blend_mode 非 normal，已降级为 light RGBA。"
    if not _straight_alpha_evidence_is_sufficient(source):
        return _apply_light_rgba(source, light_rgba), "dark/two-color source alpha 编码缺少 straight-alpha 证据，已降级为 light RGBA。"
    try:
        return compose_two_color_straight_alpha(source, light_rgba, dark_rgb), "已应用受限 straight-alpha normal two-color preview；未实现 PMA、gamma/linear 变换、外部 Black Point 或 dark-alpha additive。"
    except TwoColorCompositeError as exc:
        return _apply_light_rgba(source, light_rgba), f"dark/two-color 通道未满足受限合成契约（{exc}），已降级为 light RGBA。"


def _source_to_world(layer: PoseLayer, source_size: tuple[int, int]) -> tuple[float, float, float, float, float, float]:
    """返回 source u/v 到 Spine world x/y 的仿射系数。"""
    width, height = source_size
    attachment = layer.attachment
    radians = math.radians(attachment.rotation)
    cos = math.cos(radians)
    sin = math.sin(radians)
    # source: (0,0) 是图像左上；Spine region 坐标以附件中心为原点且 y 向上。
    sx_u = attachment.width / width
    sy_v = -attachment.height / height
    ax = attachment.scale_x * cos * sx_u
    bx = -attachment.scale_y * sin * sy_v
    ay = attachment.scale_x * sin * sx_u
    by = attachment.scale_y * cos * sy_v
    center_x = attachment.x - attachment.scale_x * cos * attachment.width * 0.5 + attachment.scale_y * sin * attachment.height * 0.5
    center_y = attachment.y - attachment.scale_x * sin * attachment.width * 0.5 - attachment.scale_y * cos * attachment.height * 0.5
    bone = layer.world
    return (
        bone.a * ax + bone.b * ay,
        bone.a * bx + bone.b * by,
        bone.a * center_x + bone.b * center_y + bone.world_x,
        bone.c * ax + bone.d * ay,
        bone.c * bx + bone.d * by,
        bone.c * center_x + bone.d * center_y + bone.world_y,
    )


def _corners(transform: tuple[float, float, float, float, float, float], size: tuple[int, int]) -> tuple[tuple[float, float], ...]:
    ax, bx, tx, ay, by, ty = transform
    width, height = size
    return tuple((ax * u + bx * v + tx, ay * u + by * v + ty) for u, v in ((0, 0), (width, 0), (width, height), (0, height)))


def _paste_affine(canvas: Image.Image, source: Image.Image, transform: tuple[float, float, float, float, float, float], scale: float, offset_x: float, offset_y: float) -> None:
    ax, bx, tx, ay, by, ty = transform
    # world x/y -> canvas x/y；y 轴翻转。
    a = scale * ax
    b = scale * bx
    c = scale * tx + offset_x
    d = -scale * ay
    e = -scale * by
    f = -scale * ty + offset_y
    determinant = a * e - b * d
    if abs(determinant) < 1e-9:
        return
    inverse = (e / determinant, -b / determinant, (b * f - e * c) / determinant, -d / determinant, a / determinant, (d * c - a * f) / determinant)
    warped = source.transform(canvas.size, Image.Transform.AFFINE, inverse, resample=Image.Resampling.BICUBIC)
    canvas.alpha_composite(warped)


def render_pose_layers(projection: PoseProjection, atlas: SpineAtlas, *, max_canvas: int = 1024, margin: int = 28) -> PoseRender:
    """渲染当前 pose 的 region layers；没有唯一 ATLAS 映射的 layer 会被明确诊断。"""
    diagnostics = list(projection.diagnostics)
    prepared: list[tuple[PoseLayer, Image.Image, tuple[float, float, float, float, float, float]]] = []
    prepared_meshes: list[tuple[MeshPoseLayer, Image.Image]] = []
    all_corners: list[tuple[float, float]] = []
    for layer in projection.layers:
        region_name = _atlas_region_name(atlas, layer.attachment_path)
        if region_name is None:
            diagnostics.append(f"slot {layer.slot_name} 的 attachment path {layer.attachment_path!r} 没有唯一 ATLAS region 映射。")
            continue
        source, tint_diagnostic = _apply_slot_tint(render_region(atlas, region_name), layer.rgba, layer.dark_rgb, layer.blend_mode)
        if tint_diagnostic is not None:
            diagnostics.append(f"slot {layer.slot_name}：{tint_diagnostic}")
        transform = _source_to_world(layer, source.size)
        all_corners.extend(_corners(transform, source.size))
        prepared.append((layer, source, transform))
    for layer in projection.mesh_layers:
        region_name = _atlas_region_name(atlas, layer.attachment_path)
        if region_name is None:
            diagnostics.append(f"slot {layer.slot_name} 的 mesh path {layer.attachment_path!r} 没有唯一 ATLAS region 映射。")
            continue
        source, tint_diagnostic = _apply_slot_tint(render_region(atlas, region_name), layer.rgba, layer.dark_rgb, layer.blend_mode)
        if tint_diagnostic is not None:
            diagnostics.append(f"slot {layer.slot_name} mesh：{tint_diagnostic}")
        vertices = layer.mesh.world_vertices
        all_corners.extend((vertices[index], vertices[index + 1]) for index in range(0, len(vertices), 2))
        prepared_meshes.append((layer, source))
    if not all_corners:
        return PoseRender(Image.new("RGBA", (256, 192), (20, 23, 28, 255)), 0, tuple(diagnostics))
    min_x = min(point[0] for point in all_corners)
    max_x = max(point[0] for point in all_corners)
    min_y = min(point[1] for point in all_corners)
    max_y = max(point[1] for point in all_corners)
    span_x = max(1.0, max_x - min_x)
    span_y = max(1.0, max_y - min_y)
    scale = min((max_canvas - 2 * margin) / span_x, (max_canvas - 2 * margin) / span_y)
    width = max(64, min(max_canvas, int(math.ceil(span_x * scale + 2 * margin))))
    height = max(64, min(max_canvas, int(math.ceil(span_y * scale + 2 * margin))))
    offset_x = margin - min_x * scale
    offset_y = margin + max_y * scale
    canvas = Image.new("RGBA", (width, height), (20, 23, 28, 255))
    for _, source, transform in prepared:
        _paste_affine(canvas, source, transform, scale, offset_x, offset_y)
    rendered_meshes = 0
    for layer, source in prepared_meshes:
        rendered_meshes += 1 if rasterize_mesh(canvas, source, layer.mesh, scale=scale, offset_x=offset_x, offset_y=offset_y) else 0
    return PoseRender(canvas, len(prepared) + rendered_meshes, tuple(diagnostics))
