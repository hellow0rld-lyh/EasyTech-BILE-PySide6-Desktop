from __future__ import annotations

import tempfile
from pathlib import Path

from bile_workbench.spine_deform_evidence_export import export_deform_audit_evidence
from bile_workbench.spine_workspace import create_pose_session, load_spine_static_workspace

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "incoming/cross_era_20260822/征2测试/animation/[mini]form_main1.bin"
workspace = load_spine_static_workspace(SOURCE)
session = create_pose_session(workspace, "Wait")
with tempfile.TemporaryDirectory() as directory:
    output = export_deform_audit_evidence(session, Path(directory) / "audit.json")
    evidence = session.animation.deform_evidence
    print({
        "timelines": len(evidence),
        "frames": sum(len(item.frames) for item in evidence),
        "values": sum(len(frame.values) for item in evidence for frame in item.frames),
        "json_bytes": output.stat().st_size,
        "source_bytes": SOURCE.stat().st_size,
    })
