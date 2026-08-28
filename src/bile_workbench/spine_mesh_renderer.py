"""无权重 Spine mesh 的只读三角形纹理栅格化。"""
from __future__ import annotations

from PIL import Image, ImageChops, ImageDraw

from .spine_mesh_pose import MeshPose


def _inverse_affine(destination: tuple[tuple[float, float], ...], source: tuple[tuple[float, float], ...]) -> tuple[float, float, float, float, float, float] | None:
    (x1, y1), (x2, y2), (x3, y3) = destination
    (u1, v1), (u2, v2), (u3, v3) = source
    determinant = x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2)
    if abs(determinant) < 1e-9:
        return None
    a = (u1 * (y2 - y3) + u2 * (y3 - y1) + u3 * (y1 - y2)) / determinant
    b = (u1 * (x3 - x2) + u2 * (x1 - x3) + u3 * (x2 - x1)) / determinant
    c = (u1 * (x2 * y3 - x3 * y2) + u2 * (x3 * y1 - x1 * y3) + u3 * (x1 * y2 - x2 * y1)) / determinant
    d = (v1 * (y2 - y3) + v2 * (y3 - y1) + v3 * (y1 - y2)) / determinant
    e = (v1 * (x3 - x2) + v2 * (x1 - x3) + v3 * (x2 - x1)) / determinant
    f = (v1 * (x2 * y3 - x3 * y2) + v2 * (x3 * y1 - x1 * y3) + v3 * (x1 * y2 - x2 * y1)) / determinant
    return a, b, c, d, e, f


def rasterize_mesh(canvas: Image.Image, source: Image.Image, pose: MeshPose, *, scale: float, offset_x: float, offset_y: float) -> int:
    """把一个 MeshPose 栅格化到 RGBA canvas，返回实际绘制的 triangle 数。"""
    source = source.convert("RGBA")
    width, height = source.size
    drawn = 0
    for index in range(0, len(pose.triangles), 3):
        vertex_indices = pose.triangles[index:index + 3]
        world = tuple((pose.world_vertices[item * 2], pose.world_vertices[item * 2 + 1]) for item in vertex_indices)
        destination = tuple((scale * x + offset_x, -scale * y + offset_y) for x, y in world)
        source_points = tuple((pose.uvs[item * 2] * width, pose.uvs[item * 2 + 1] * height) for item in vertex_indices)
        inverse = _inverse_affine(destination, source_points)
        if inverse is None:
            continue
        warped = source.transform(canvas.size, Image.Transform.AFFINE, inverse, resample=Image.Resampling.BICUBIC)
        mask = Image.new("L", canvas.size, 0)
        ImageDraw.Draw(mask).polygon(destination, fill=255)
        alpha = ImageChops.multiply(warped.getchannel("A"), mask)
        warped.putalpha(alpha)
        canvas.alpha_composite(warped)
        drawn += 1
    return drawn
