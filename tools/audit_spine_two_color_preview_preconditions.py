from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from bile_workbench.spine_atlas import render_region
from bile_workbench.spine_pose_renderer import _atlas_region_name
from bile_workbench.spine_workspace import create_pose_session, load_spine_static_workspace


ROOT = Path(__file__).resolve().parents[1]
SCAN = ROOT / "research/spine_two_color_timeline_sample_scan_20260822.json"
OUTPUT = ROOT / "research/spine_two_color_preview_preconditions_20260822.json"


def alpha_proof(image) -> dict[str, int | str]:
    rgba = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    alpha = rgba[..., 3]
    partial = (alpha > 0) & (alpha < 255)
    proof = partial & np.any(rgba[..., :3] > alpha[..., None], axis=2)
    return {
        "state": "straight_alpha_proven_by_rgb_greater_than_alpha" if int(proof.sum()) else "alpha_encoding_ambiguous",
        "partial_alpha_pixel_count": int(partial.sum()),
        "straight_alpha_proof_pixel_count": int(proof.sum()),
    }


def main() -> int:
    source_rows = json.loads(SCAN.read_text(encoding="utf-8"))["timelines"]
    jobs = sorted({(str(row["path"]), str(row["animation"]), float(row["first_time"])) for row in source_rows})
    rows: list[dict[str, object]] = []
    for relative, animation, time in jobs:
        path = ROOT / relative
        try:
            session = create_pose_session(load_spine_static_workspace(path), animation)
            projection, _ = session.preview(time)
        except Exception as exc:  # audit must report unverified candidates, never repair them.
            rows.append({"path": relative, "animation": animation, "time": time, "state": "workspace_or_pose_unavailable", "reason": str(exc)})
            continue
        dark_layers = tuple(layer for layer in projection.layers if layer.dark_rgb is not None and layer.blend_mode == 0)
        if not dark_layers:
            rows.append({"path": relative, "animation": animation, "time": time, "state": "no_normal_region_dark_layer_at_audited_time"})
            continue
        for layer in dark_layers:
            region = _atlas_region_name(session.workspace.atlas, layer.attachment_path)
            if region is None:
                rows.append({"path": relative, "animation": animation, "time": time, "slot": layer.slot_name, "state": "no_unique_atlas_region"})
                continue
            rows.append({
                "path": relative,
                "animation": animation,
                "time": time,
                "slot": layer.slot_name,
                "attachment_path": layer.attachment_path,
                "atlas_region": region,
                "dark_rgb": layer.dark_rgb,
                "light_rgba": layer.rgba,
                "blend_mode": layer.blend_mode,
                **alpha_proof(render_region(session.workspace.atlas, region)),
            })
    proven = sum(row.get("state") == "straight_alpha_proven_by_rgb_greater_than_alpha" for row in rows)
    payload = {
        "schema": "easytech-spine-two-color-preview-preconditions/v1",
        "read_only": True,
        "job_count": len(jobs),
        "straight_alpha_proven_region_layer_count": proven,
        "rows": rows,
        "boundary": "Audits only normal-blend region layers and source-alpha evidence. Does not tint a pixel, generate a preview, handle mesh/sequence/clipping/non-normal blend, or write BIN.",
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"job_count": len(jobs), "rows": len(rows), "straight_alpha_proven_region_layer_count": proven}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
