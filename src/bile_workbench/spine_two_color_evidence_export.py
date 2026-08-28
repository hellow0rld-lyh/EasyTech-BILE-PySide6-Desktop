from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from .spine_two_color_evidence import collect_two_color_timeline_evidence
from .spine_workspace import SpinePoseSession


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def export_two_color_timeline_evidence(session: SpinePoseSession, output_path: Path) -> Path:
    """导出 raw two-color evidence；不调用 PoseProjection、renderer 或任何写回代码。"""
    workspace = session.workspace
    evidence = collect_two_color_timeline_evidence("3.8" if workspace.engine == "spine38" else "4.1", session.animation)
    payload = {
        "schema": "easytech-spine-two-color-audit/v1",
        "read_only": True,
        "pixel_application": "forbidden",
        "rendering": "forbidden",
        "writeback": "forbidden",
        "source_sha256": _sha256(workspace.bin_path),
        "engine": workspace.engine,
        "spine_version": workspace.document.header.version,
        "animation": session.animation.name,
        "timeline_count": len(evidence),
        "timelines": [asdict(item) for item in evidence],
        "boundary": "只导出已消费的 light/dark slot timeline 通道和 curve evidence；不应用 dark tint、不创建像素输出、不渲染、不写回 Spine BIN。",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output_path
