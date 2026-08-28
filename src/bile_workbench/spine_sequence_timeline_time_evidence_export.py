from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

from .spine_sequence_timeline_time_audit import audit_sequence_region_index_at_time
from .spine_sequence_timeline_atlas_candidate_audit import audit_sequence_candidate_name_at_time

if TYPE_CHECKING:
    from .spine_workspace import SpineStaticWorkspace


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def export_sequence_time_audit_evidence(
    workspace: "SpineStaticWorkspace",
    animation_name: str,
    target_time: float,
    output_path: Path,
) -> Path:
    """导出指定 raw time 的 sequence region-index 审计，不创建可播放或可渲染状态。"""
    if workspace.engine != "spine41" or workspace.timeline_archive is None:
        raise ValueError("仅完整读取的 Spine 4.1 workspace 可以导出 sequence time audit evidence")
    animation = next((item for item in workspace.timeline_archive.animations if item.name == animation_name), None)
    if animation is None:
        raise ValueError(f"未找到动画：{animation_name}")
    static_sequences = getattr(workspace.document, "sequence_evidence", ())
    timeline_evidence = getattr(animation, "sequence_timeline_evidence", ())
    audits = [asdict(audit_sequence_region_index_at_time(item, static_sequences, target_time)) for item in timeline_evidence]
    candidate_name_audits = [
        asdict(audit_sequence_candidate_name_at_time(item, static_sequences, workspace.atlas.regions, target_time))
        for item in timeline_evidence
    ]
    payload = {
        "schema": "easytech-spine-sequence-time-audit/v1",
        "read_only": True,
        "frame_selection": "forbidden",
        "image_sampling": "forbidden",
        "attachment_application": "forbidden",
        "rendering": "forbidden",
        "writeback": "forbidden",
        "source_sha256": _sha256(workspace.bin_path),
        "engine": workspace.engine,
        "spine_version": workspace.document.header.version,
        "animation": animation.name,
        "target_time": target_time,
        "time_domain": "unlooped_raw_animation_time_only",
        "audits": audits,
        "candidate_name_audits": candidate_name_audits,
        "boundary": "只导出已消费的 timeline/static/ATLAS 名称 evidence 的 mode 与候选名称身份审计；不选择图像帧、不采样图像、不创建 Slot、不应用 attachment、不渲染、不重写 Spine BIN。",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output_path
