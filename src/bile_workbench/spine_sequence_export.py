"""Spine 只读 pose 序列导出；绝不修改源 BIN。"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image

if TYPE_CHECKING:
    from .spine_workspace import SpinePoseSession


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class SpinePoseSequenceResult:
    output_path: Path
    evidence_path: Path
    frame_count: int
    partial_frame_count: int
    animation_name: str
    duration: float


def export_spine_pose_sequence(session: SpinePoseSession, output_path: Path, *, frame_count: int = 30, kind: str = "gif") -> SpinePoseSequenceResult:
    if frame_count < 2 or frame_count > 300:
        raise ValueError("Spine pose 序列帧数必须在 2..300 之间")
    duration = session.animation.duration
    poses = []
    for index in range(frame_count):
        time = duration * index / (frame_count - 1)
        projection, rendered = session.preview(time)
        poses.append((time, projection, rendered))
    width = max(item[2].image.width for item in poses)
    height = max(item[2].image.height for item in poses)
    frames: list[Image.Image] = []
    for _, _, rendered in poses:
        frame = Image.new("RGBA", (width, height), (20, 23, 28, 255))
        frame.alpha_composite(rendered.image, ((width - rendered.image.width) // 2, (height - rendered.image.height) // 2))
        frames.append(frame)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    delay = max(20, int(max(duration, 0.1) * 1000 / (frame_count - 1)))
    if kind == "gif":
        # 直接传递 RGBA 帧并禁止优化；逐帧 adaptive P 转换可能导致 Pillow 在保存时折叠原本不同的 pose 帧。
        frames[0].save(output_path, save_all=True, append_images=frames[1:], duration=delay, loop=0, disposal=2, optimize=False)
    elif kind == "apng":
        frames[0].save(output_path, save_all=True, append_images=frames[1:], duration=delay, loop=0, disposal=2)
    else:
        raise ValueError(f"不支持的 Spine pose 序列格式：{kind}")
    evidence_path = output_path.with_suffix(output_path.suffix + ".evidence.json")
    payload = {
        "schema": "easytech-spine-pose-preview/v1",
        "read_only": True,
        "writeback": "forbidden",
        "source_sha256": _file_sha256(session.workspace.bin_path),
        "engine": session.workspace.engine,
        "animation": session.animation.name,
        "duration": duration,
        "frame_count": frame_count,
        "kind": kind,
        "partial_frame_count": sum(not item[1].coverage_complete for item in poses),
        "frames": [
            {
                "time": time,
                "coverage_complete": projection.coverage_complete,
                "layer_count": rendered.rendered_layer_count,
                "diagnostics": list(rendered.diagnostics),
            }
            for time, projection, rendered in poses
        ],
        "boundary": "仅执行只读 setup blend pose：已支持经捕获的 bone 变换、cubic Bezier、slot attachment/light RGBA/alpha 与 draw-order；constraint、复杂 transform inheritance、dark/two-color、非 normal blend、deform、mesh、sequence、完整 runtime playback 与 Spine BIN 写回不在此输出范围。",
    }
    evidence_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return SpinePoseSequenceResult(output_path, evidence_path, frame_count, payload["partial_frame_count"], session.animation.name, duration)
