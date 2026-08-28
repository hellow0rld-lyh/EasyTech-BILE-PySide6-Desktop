"""BILE Scene Interchange v1：面向审阅与 AI 提案的只读场景中转层。

这是 BILE 的可解释投影，并不是 BILE writer。它有意排除所有不透明字段、
原始偏移和任何把结果序列化回 BIN 的接口。后续若实现重建式实验导出，必须
使用另一 schema、另一模块及更严格的独立回归门槛。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .bile_format import BileDocument, Element, parse_file
from .preview_renderer import Atlas, load_atlas, render_frame

SCENE_SCHEMA = "easytech-bile-scene/v1"
SCENE_KIND = "read_only_scene"
WITNESS_RENDERER = "bile_workbench.preview_renderer/reference_v4"
MAX_WITNESS_ANIMATIONS_PER_DOCUMENT = 8
MAX_WITNESS_SLOTS_PER_ANIMATION = 8


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _matrix(keyframe: Any) -> dict[str, float]:
    return {
        "xx": keyframe.xx,
        "xy": keyframe.xy,
        "yx": keyframe.yx,
        "yy": keyframe.yy,
        "x": keyframe.x,
        "y": keyframe.y,
    }


def _element_node(element: Element, atlas: Atlas) -> dict[str, Any]:
    node: dict[str, Any] = {
        "id": f"element:{element.index}",
        "element_index": element.index,
        "name": element.name,
        "kind": "sprite" if element.has_texture else "animation",
        "anchor": {"x": element.x, "y": element.y},
    }
    if element.has_texture:
        region = atlas.regions.get(element.name) or atlas.regions.get(f"{element.name}.png")
        node["atlas_region"] = (
            None
            if region is None
            else {
                "name": region.name,
                "bounds": {"x": region.x, "y": region.y, "width": region.w, "height": region.h},
                "reference": {"x": region.refx, "y": region.refy},
            }
        )
    else:
        node["frame_count"] = element.frame_count
        node["channel_count"] = element.channel_count
    return node


def _timeline(element: Element) -> dict[str, Any]:
    """将 BILE 引用表投影为有序、离散的 scene timeline；不改变源引用语义。"""
    return {
        "animation_id": f"element:{element.index}",
        "frame_count": element.frame_count,
        "channels": [
            {
                "channel_index": channel_index,
                "frames": [
                    {
                        "slot": frame.slot,
                        # 此顺序是 renderer 消费的输入顺序；中转消费者不得假定它等于最终像素绘制顺序。
                        "draws": [
                            {
                                "draw_index": draw_index,
                                "target_element_id": None if track.element_index < 0 else f"element:{track.element_index}",
                                "target_element_index": track.element_index,
                                "keyframe_id": f"keyframe:{track.keyframe_index}",
                                "keyframe_index": track.keyframe_index,
                            }
                            for draw_index, track in enumerate(frame.tracks)
                        ],
                    }
                    for frame in channel.frames
                ],
            }
            for channel_index, channel in enumerate(element.channels)
        ],
    }


def _timeline_transition_slots(animation: Element) -> list[int]:
    """返回根动画的全部可见时间线切换点；这比均匀帧号更贴近 hold 语义。"""
    slots = {0, max(0, animation.frame_count - 1)}
    for channel in animation.channels:
        slots.update(frame.slot for frame in channel.frames if 0 <= frame.slot < animation.frame_count)
    return sorted(slots)


def _select_animation_witnesses(animations: tuple[Element, ...]) -> tuple[list[Element], str]:
    """文档级预算：动画很多时保留首尾和均匀分布的代表根，绝不宣称已逐动画渲染。"""
    if len(animations) <= MAX_WITNESS_ANIMATIONS_PER_DOCUMENT:
        return list(animations), "all_animations"
    indexes = {
        round(index * (len(animations) - 1) / (MAX_WITNESS_ANIMATIONS_PER_DOCUMENT - 1))
        for index in range(MAX_WITNESS_ANIMATIONS_PER_DOCUMENT)
    }
    return [animations[index] for index in sorted(indexes)], "deterministic_stratified_animations"


def _critical_slots(animation: Element) -> tuple[list[int], int, str]:
    """受预算地选择见证槽位，并保留源候选数量以避免把抽样误称为全覆盖。"""
    candidates = _timeline_transition_slots(animation)
    if len(candidates) <= MAX_WITNESS_SLOTS_PER_ANIMATION:
        return candidates, len(candidates), "all_transition_slots"
    selected = {
        candidates[round(index * (len(candidates) - 1) / (MAX_WITNESS_SLOTS_PER_ANIMATION - 1))]
        for index in range(MAX_WITNESS_SLOTS_PER_ANIMATION)
    }
    return sorted(selected), len(candidates), "deterministic_stratified_transition_slots"


def build_render_witnesses(
    document: BileDocument,
    atlas: Atlas,
    *,
    canvas_size: tuple[int, int] = (256, 192),
    background: tuple[int, int, int, int] = (35, 38, 44, 255),
) -> dict[str, Any]:
    """建立不可编辑的关键槽位 RGBA 哈希清单，不保存画面也不改变源资源。"""
    animations: list[dict[str, Any]] = []
    selected_animations, animation_sampling = _select_animation_witnesses(document.animations)
    for animation in selected_animations:
        frames: list[dict[str, Any]] = []
        slots, candidate_slot_count, sampling = _critical_slots(animation)
        for slot in slots:
            image = render_frame(
                document,
                atlas,
                animation.name,
                slot,
                canvas_size=canvas_size,
                background=background,
                nested_timing="reference_v4",
            )
            frames.append({
                "slot": slot,
                "rgba_sha256": hashlib.sha256(image.tobytes()).hexdigest(),
            })
        animations.append({
            "animation_id": f"element:{animation.index}",
            "name": animation.name,
            "candidate_transition_slot_count": candidate_slot_count,
            "sampling": sampling,
            "frames": frames,
        })
    return {
        "renderer": WITNESS_RENDERER,
        "canvas": {"width": canvas_size[0], "height": canvas_size[1]},
        "background_rgba": list(background),
        "animation_coverage": {
            "candidate_animation_count": len(document.animations),
            "selected_animation_count": len(selected_animations),
            "sampling": animation_sampling,
            "per_animation_slot_budget": MAX_WITNESS_SLOTS_PER_ANIMATION,
        },
        "slot_selection": "all root timeline transition slots plus slot 0/final slot when <= 8; otherwise deterministic stratified transition slots under the per-animation budget",
        "animations": animations,
    }


def build_scene_interchange(
    document: BileDocument,
    atlas: Atlas,
    *,
    source_bin: Path,
    source_xml: Path,
    source_image: Path,
    include_render_witnesses: bool = False,
) -> dict[str, Any]:
    """构建可 JSON 序列化的 BILE 场景投影，严格只读。"""
    payload: dict[str, Any] = {
        "schema": SCENE_SCHEMA,
        "kind": SCENE_KIND,
        "read_only": True,
        "writeback": "forbidden",
        "source": {
            "bin": {"name": source_bin.name, "sha256": _sha256(source_bin), "version": document.header.version, "fps": document.header.fps},
            "atlas": {
                "xml_name": source_xml.name,
                "xml_sha256": _sha256(source_xml),
                "image_name": source_image.name,
                "image_sha256": _sha256(source_image),
                "image_format": atlas.source_image_format,
                "region_count": len(atlas.regions),
            },
        },
        "coordinate_contract": {
            "matrix": "point(x,y)=(xx*x+yx*y+x, xy*x+yy*y+y)",
            "color": "straight ARGB modulation; nested draw colors multiply channel-wise",
            "timeline": "each channel holds its last frame whose slot <= local slot",
            "nested_timing": "reference_v4: nested animation slot derives from parent frame slot, initial_phase and playback_mode; v2 payload fields are read-only approximations",
            "order": "timeline draw order is source track order; final compositing order remains renderer-version-specific and must be checked by preview regression",
        },
        "nodes": [_element_node(element, atlas) for element in document.elements],
        "keyframes": [
            {
                "id": f"keyframe:{index}",
                "index": index,
                "transform": _matrix(keyframe),
                "argb": f"0x{keyframe.argb:08X}",
                "rgba": {"r": keyframe.rgba[0], "g": keyframe.rgba[1], "b": keyframe.rgba[2], "a": keyframe.rgba[3]},
                "nested_playback": {
                    "initial_phase": keyframe.initial_phase,
                    "playback_mode": keyframe.playback_mode,
                    "mode_status": "supported_reference_v4" if document.header.version in (3, 4) and keyframe.has_known_playback_mode else "read_only_or_unconfirmed",
                },
            }
            for index, keyframe in enumerate(document.keyframes)
        ],
        "timelines": [_timeline(animation) for animation in document.animations],
        "diagnostics": {
            "graph_cycles": [list(cycle) for cycle in document.graph_cycles],
            "source_structure": {
                "element_count": len(document.elements),
                "sprite_count": len(document.sprites),
                "animation_count": len(document.animations),
                "keyframe_count": len(document.keyframes),
                "channel_count": sum(len(element.channels) for element in document.animations),
                "frame_count": sum(len(channel.frames) for element in document.animations for channel in element.channels),
                "track_count": sum(len(frame.tracks) for element in document.animations for channel in element.channels for frame in channel.frames),
            },
            "boundary": "该 JSON 是只读场景投影。它不携带 BILE opaque fields、区块偏移或写回权限；不能被当作 patch 或实验性重建 BIN 输入。",
        },
    }
    if include_render_witnesses:
        payload["render_witnesses"] = build_render_witnesses(document, atlas)
    return payload


def export_scene_interchange(
    bin_path: str | Path,
    xml_path: str | Path,
    image_path: str | Path,
    output_path: str | Path,
    *,
    include_render_witnesses: bool = False,
) -> dict[str, Any]:
    """从一套 BILE 三件套导出 Scene Interchange v1，不修改任何输入文件。"""
    source_bin = Path(bin_path)
    source_xml = Path(xml_path)
    source_image = Path(image_path)
    document = parse_file(source_bin)
    atlas = load_atlas(source_xml, source_image)
    payload = build_scene_interchange(
        document,
        atlas,
        source_bin=source_bin,
        source_xml=source_xml,
        source_image=source_image,
        include_render_witnesses=include_render_witnesses,
    )
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload
