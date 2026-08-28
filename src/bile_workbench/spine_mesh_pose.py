"""Spine 无权重 mesh 的只读 pose 几何子集。

本模块不读取或写入 BIN，也不处理加权 vertices、deform、linked mesh、clipping 或 sequence。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .spine38_format import SpineMeshAttachment


@dataclass(frozen=True)
class MeshPose:
    attachment: SpineMeshAttachment
    bone_index: int
    world_vertices: tuple[float, ...]
    triangles: tuple[int, ...]
    uvs: tuple[float, ...]


def _validate_mesh(mesh: SpineMeshAttachment, vertex_count: int) -> str | None:
    if len(mesh.uvs) != vertex_count * 2:
        return f"mesh {mesh.name} 的 vertices/UV 长度不一致；当前不渲染。"
    if len(mesh.triangles) % 3 or any(index < 0 or index >= vertex_count for index in mesh.triangles):
        return f"mesh {mesh.name} 的 triangle 索引无效；当前不渲染。"
    return None


def project_unweighted_mesh(mesh: SpineMeshAttachment, world: Any) -> tuple[MeshPose | None, str | None]:
    """将 attachment-local 无权重顶点经 slot bone 的 world matrix 投影。"""
    if mesh.vertices is None:
        return None, f"mesh {mesh.name} 为加权 vertices；当前只读子集不投影。"
    vertex_count = len(mesh.vertices) // 2
    if len(mesh.vertices) % 2:
        return None, f"mesh {mesh.name} 的 vertices 不是二维坐标对；当前不渲染。"
    diagnostic = _validate_mesh(mesh, vertex_count)
    if diagnostic:
        return None, diagnostic
    values: list[float] = []
    for index in range(0, len(mesh.vertices), 2):
        x, y = mesh.vertices[index], mesh.vertices[index + 1]
        values.extend((world.a * x + world.b * y + world.world_x, world.c * x + world.d * y + world.world_y))
    return MeshPose(mesh, mesh.slot_index, tuple(values), mesh.triangles, mesh.uvs), None


def project_weighted_mesh_setup(mesh: SpineMeshAttachment, worlds: tuple[Any, ...] | list[Any]) -> tuple[MeshPose | None, str | None]:
    """投影加权 mesh 的 setup/static pose；不执行 deform 或额外顶点偏移。"""
    if mesh.weighted_vertices is None:
        return None, f"mesh {mesh.name} 不含加权 vertices；应使用无权重投影。"
    diagnostic = _validate_mesh(mesh, len(mesh.weighted_vertices))
    if diagnostic:
        return None, diagnostic
    values: list[float] = []
    for vertex_index, influences in enumerate(mesh.weighted_vertices):
        if not influences:
            return None, f"mesh {mesh.name} 的 vertex {vertex_index} 没有 bone influence；当前不渲染。"
        x = y = 0.0
        for bone_index, local_x, local_y, weight in influences:
            if not 0 <= bone_index < len(worlds) or weight < 0.0:
                return None, f"mesh {mesh.name} 的 vertex {vertex_index} 含无效 influence；当前不渲染。"
            world = worlds[bone_index]
            x += (world.a * local_x + world.b * local_y + world.world_x) * weight
            y += (world.c * local_x + world.d * local_y + world.world_y) * weight
        values.extend((x, y))
    return MeshPose(mesh, mesh.slot_index, tuple(values), mesh.triangles, mesh.uvs), None
