#!/usr/bin/env python3
"""导出 anim_failure 的完整序列演示，用于验证 GIF/APNG/PNG 输出。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bile_workbench.bile_format import parse_file
from bile_workbench.preview_renderer import load_atlas
from bile_workbench.sequence_export import export_sequence


def main() -> int:
    assets = ROOT / "sample_assets"
    out = ROOT / "research" / "sequence_export_demo"
    out.mkdir(exist_ok=True)
    document = parse_file(assets / "anim_failure.bin")
    atlas = load_atlas(assets / "anim_failure.xml", assets / "anim_failure.webp")
    gif = export_sequence(document, atlas, "failure_a", out / "failure_a.gif", "gif", canvas_size=(320, 240))
    apng = export_sequence(document, atlas, "failure_a", out / "failure_a.apng", "apng", canvas_size=(320, 240), transparent=True)
    png = export_sequence(document, atlas, "failure_a", out / "frames", "png-sequence", 0, 5, (320, 240))
    summary = {
        "gif": {"path": str(gif.output_paths[0]), "manifest": str(gif.manifest_path), "frames": gif.frame_count},
        "apng": {"path": str(apng.output_paths[0]), "manifest": str(apng.manifest_path), "frames": apng.frame_count},
        "png_sequence": {"directory": str(png.output_paths[0].parent), "manifest": str(png.manifest_path), "frames": png.frame_count},
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
