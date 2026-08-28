from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from bile_workbench.spine_atlas import render_region
from bile_workbench.spine_pose_renderer import _atlas_region_name
from bile_workbench.spine_workspace import create_pose_session, load_spine_static_workspace


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "incoming/cross_era_20260822/征2测试/animation/EmpireCityFire01.bin"
OUTPUT = ROOT / "research/spine_two_color_straight_alpha_probe_20260822.json"


def _proof(region_image) -> dict[str, int | str]:
    rgba = np.asarray(region_image.convert("RGBA"), dtype=np.uint8)
    alpha = rgba[..., 3]
    rgb = rgba[..., :3]
    partial = (alpha > 0) & (alpha < 255)
    proves_straight = partial & np.any(rgb > alpha[..., None], axis=2)
    if int(proves_straight.sum()) > 0:
        state = "straight_alpha_proven_by_rgb_greater_than_alpha"
    elif int(partial.sum()) > 0:
        state = "alpha_encoding_ambiguous"
    else:
        state = "no_partial_alpha_pixels; alpha_encoding_ambiguous"
    return {
        "state": state,
        "partial_alpha_pixel_count": int(partial.sum()),
        "straight_alpha_proof_pixel_count": int(proves_straight.sum()),
    }


def main() -> int:
    session = create_pose_session(load_spine_static_workspace(SOURCE), "Wait")
    projection, _ = session.preview(0.0)
    rows = []
    for layer in projection.layers:
        if layer.dark_rgb is None:
            continue
        name = _atlas_region_name(session.workspace.atlas, layer.attachment_path)
        if name is None:
            rows.append({"slot": layer.slot_name, "state": "no_unique_atlas_region"})
            continue
        row = {
            "slot": layer.slot_name,
            "attachment_path": layer.attachment_path,
            "atlas_region": name,
            "dark_rgb": layer.dark_rgb,
            "blend_mode": layer.blend_mode,
            **_proof(render_region(session.workspace.atlas, name)),
        }
        rows.append(row)
    payload = {
        "schema": "easytech-spine-two-color-straight-alpha-probe/v1",
        "read_only": True,
        "source": str(SOURCE.relative_to(ROOT)),
        "animation": "Wait",
        "time": 0.0,
        "layers": rows,
        "boundary": "Reads decoded atlas crops only to prove or reject straight-alpha preconditions for a future normal-alpha preview. It does not tint pixels, render a preview, select sequence frames, or write BIN.",
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
