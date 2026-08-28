"""导出 Spine deform 的只读审计 evidence；不含投影、顶点应用或 BIN 写回。"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .spine_deform_evidence import DeformTimelineEvidence
from .spine_workspace import SpinePoseSession
from .spine_unweighted_deform_validation import validate_unweighted_deform_identity_and_span


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def export_deform_audit_evidence(session: SpinePoseSession, output_path: Path) -> Path:
    static = session.workspace.document
    meshes = {(item.skin, item.slot_index, item.name): item for item in getattr(static, "mesh_attachments", ()) if item.vertices is not None}
    timelines = []
    for item in session.animation.deform_evidence:
        if not isinstance(item, DeformTimelineEvidence):
            continue
        mesh = meshes.get((item.skin, item.slot_index, item.attachment_name))
        validation = validate_unweighted_deform_identity_and_span(mesh, item) if mesh is not None else None
        timelines.append({
            "skin": item.skin,
            "slot_index": item.slot_index,
            "attachment_name": item.attachment_name,
            "frames": [
                {"time": frame.time, "start": frame.start, "values": list(frame.values), "curve": frame.curve}
                for frame in item.frames
            ],
            "unweighted_identity_span_validation": None if validation is None else {
                "accepted": validation.accepted,
                "reason": validation.reason,
                "vertex_scalar_count": validation.vertex_scalar_count,
                "frame_count": validation.frame_count,
            },
        })
    payload = {
        "schema": "easytech-spine-deform-audit/v1",
        "read_only": True,
        "writeback": "forbidden",
        "vertex_application": "forbidden",
        "source_sha256": _sha256(session.workspace.bin_path),
        "engine": session.workspace.engine,
        "spine_version": session.workspace.document.header.version,
        "animation": session.animation.name,
        "timelines": timelines,
        "boundary": "导出的是已消费的 deform evidence 和纯 identity/span 预检；不插值、不修改 mesh vertices、不渲染 deform、不重写 Spine BIN。",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output_path
