"""BILE v4 动画的完整序列导出。

导出仅基于已经解析的 BIN/XML/WebP 三件套；不会写入或改变任何游戏资源。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .bile_format import BileDocument
from .preview_renderer import Atlas, render_frame

ExportKind = Literal["png-sequence", "gif", "apng"]
MAX_EXPORT_FRAMES = 240
MAX_FRAME_PIXELS = 1_048_576


@dataclass(frozen=True)
class SequenceExportResult:
    kind: ExportKind
    animation: str
    start_slot: int
    end_slot: int
    frame_count: int
    fps: float
    canvas_size: tuple[int, int]
    output_paths: tuple[Path, ...]
    manifest_path: Path


def _validate_range(document: BileDocument, animation: str, start_slot: int, end_slot: int, canvas_size: tuple[int, int]) -> tuple[int, int]:
    target = next((element for element in document.animations if element.name == animation), None)
    if target is None:
        raise KeyError(f"未找到动画元素：{animation}")
    if not isinstance(start_slot, int) or not isinstance(end_slot, int) or start_slot < 0 or end_slot < start_slot:
        raise ValueError("导出槽位范围无效")
    if end_slot >= target.frame_count:
        raise ValueError(f"结束槽位 {end_slot} 超出动画 '{animation}' 的范围 0..{target.frame_count - 1}")
    count = end_slot - start_slot + 1
    if count > MAX_EXPORT_FRAMES:
        raise ValueError(f"导出帧数 {count} 超过安全上限 {MAX_EXPORT_FRAMES}；请分段导出")
    width, height = canvas_size
    if width <= 0 or height <= 0 or width * height > MAX_FRAME_PIXELS:
        raise ValueError(f"画布 {width}×{height} 超出安全上限 {MAX_FRAME_PIXELS} 像素")
    return count, target.frame_count


def _render_slots(
    document: BileDocument,
    atlas: Atlas,
    animation: str,
    start_slot: int,
    end_slot: int,
    canvas_size: tuple[int, int],
    transparent: bool,
) -> list:
    background = (0, 0, 0, 0) if transparent else (35, 38, 44, 255)
    return [
        render_frame(document, atlas, animation, slot, canvas_size=canvas_size, background=background, nested_timing="reference_v4")
        for slot in range(start_slot, end_slot + 1)
    ]


def _write_manifest(result: SequenceExportResult, output_dir: Path, transparent: bool) -> Path:
    manifest = output_dir / f"{result.animation}_slots_{result.start_slot}-{result.end_slot}_{result.kind}.manifest.json"
    payload = {
        "schema": "bile-workbench.sequence-export/v1",
        "kind": result.kind,
        "animation": result.animation,
        "start_slot": result.start_slot,
        "end_slot": result.end_slot,
        "frame_count": result.frame_count,
        "fps": result.fps,
        "canvas_size": list(result.canvas_size),
        "output_paths": [str(path.name) for path in result.output_paths],
        "transparent_background": transparent,
        "nested_timing": "reference_v4",
        "note": "此导出仅用于预览和回归；游戏资源修改应使用带 SHA-256 的保守补丁。",
    }
    manifest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def export_sequence(
    document: BileDocument,
    atlas: Atlas,
    animation: str,
    output_path: str | Path,
    kind: ExportKind,
    start_slot: int = 0,
    end_slot: int | None = None,
    canvas_size: tuple[int, int] = (512, 384),
    transparent: bool = False,
) -> SequenceExportResult:
    """导出连续整数槽位；GIF/APNG 为循环预览，PNG 序列逐帧保存。"""
    target = next((element for element in document.animations if element.name == animation), None)
    if target is None:
        raise KeyError(f"未找到动画元素：{animation}")
    final_slot = target.frame_count - 1 if end_slot is None else end_slot
    frame_count, _ = _validate_range(document, animation, start_slot, final_slot, canvas_size)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []

    if kind == "png-sequence":
        frame_dir = destination if destination.suffix == "" else destination.with_suffix("")
        frame_dir.mkdir(parents=True, exist_ok=True)
        background = (0, 0, 0, 0) if transparent else (35, 38, 44, 255)
        for slot in range(start_slot, final_slot + 1):
            frame = render_frame(document, atlas, animation, slot, canvas_size=canvas_size, background=background, nested_timing="reference_v4")
            path = frame_dir / f"{animation}_slot_{slot:04d}.png"
            frame.save(path)
            outputs.append(path)
        output_dir = frame_dir
    elif kind in {"gif", "apng"}:
        frames = _render_slots(document, atlas, animation, start_slot, final_slot, canvas_size, transparent)
        extension = ".gif" if kind == "gif" else ".png"
        path = destination.with_suffix(extension)
        duration = max(1, round(1000.0 / max(document.header.fps, 1.0)))
        first, rest = frames[0], frames[1:]
        if kind == "gif":
            first.convert("P", palette=0).save(path, save_all=True, append_images=[frame.convert("P", palette=0) for frame in rest], duration=duration, loop=0, disposal=2)
        else:
            first.save(path, format="PNG", save_all=True, append_images=rest, duration=duration, loop=0, disposal=2)
        outputs.append(path)
        output_dir = path.parent
    else:
        raise ValueError(f"不支持的导出类型：{kind}")

    provisional = SequenceExportResult(kind, animation, start_slot, final_slot, frame_count, document.header.fps, canvas_size, tuple(outputs), Path())
    manifest = _write_manifest(provisional, output_dir, transparent)
    return SequenceExportResult(kind, animation, start_slot, final_slot, frame_count, document.header.fps, canvas_size, tuple(outputs), manifest)
