#!/usr/bin/env python3
"""定位 anim_status 初相位候选补丁的实际渲染差异。"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bile_workbench.diff_analysis import compare_animation
from bile_workbench.interchange import SCHEMA, apply_patch
from bile_workbench.preview_renderer import load_atlas, render_frame


def count(left, right) -> int:
    return sum(a != b for a, b in zip(left.getdata(), right.getdata()))


def main() -> int:
    assets = ROOT / "sample_assets"
    source = assets / "anim_status.bin"
    original = source.read_bytes()
    atlas = load_atlas(assets / "anim_status.xml", assets / "anim_status.webp")
    with tempfile.TemporaryDirectory() as temp_dir:
        temp = Path(temp_dir)
        patch = temp / "patch.json"
        candidate = temp / "candidate.bin"
        patch.write_text(json.dumps({"schema": SCHEMA, "kind": "patch", "source_sha256": hashlib.sha256(original).hexdigest(), "keyframes": [{"index": 698, "initial_phase": 2}]}), encoding="utf-8")
        original_doc = apply_patch(source, temp / "empty.json", candidate) if False else None
        apply_patch(source, patch, candidate)
        from bile_workbench.bile_format import parse_file
        before_doc = parse_file(source)
        after_doc = parse_file(candidate)
        print("slot, pixel_delta")
        for slot in range(42):
            before = render_frame(before_doc, atlas, "anim_upgrade", slot, canvas_size=(512, 384))
            after = render_frame(after_doc, atlas, "anim_upgrade", slot, canvas_size=(512, 384))
            delta = count(before, after)
            if delta:
                print(slot, delta)
        result = compare_animation(source, candidate, atlas, "anim_upgrade", temp / "report", (512, 384))
        print("result", result.changed_slots, result.total_changed_pixels)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
