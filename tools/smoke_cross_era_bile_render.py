"""批量加载新增完整 BILE 三件套并渲染代表帧；完全只读。"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from bile_workbench.assets import AssetTripletError, discover_triplet
from bile_workbench.bile_format import BileFormatError, parse_file
from bile_workbench.preview_renderer import load_atlas, render_frame


@dataclass(frozen=True)
class RenderResult:
    path: str
    version: int | None
    status: str
    animation: str | None
    slot: int | None
    non_background_pixels: int | None
    detail: str


def verify(path: Path, root: Path) -> RenderResult | None:
    if path.read_bytes()[:4] != b"BILE":
        return None
    try:
        triplet = discover_triplet(path)
        document = parse_file(path)
        animation = next((item for item in document.animations if item.frame_count > 0), None)
        if animation is None:
            return RenderResult(str(path.relative_to(root)), document.header.version, "SKIP", None, None, None, "没有可渲染动画根。")
        slot = min(animation.frame_count - 1, max(0, animation.frame_count // 2))
        atlas = load_atlas(triplet.xml_path, triplet.image_path)
        canvas = render_frame(document, atlas, animation.name, slot, canvas_size=(512, 384), nested_timing="reference_v4")
        background = (35, 38, 44, 255)
        non_background = sum(pixel != background for pixel in canvas.getdata())
        return RenderResult(
            str(path.relative_to(root)),
            document.header.version,
            "PASS",
            animation.name,
            slot,
            non_background,
            "图集加载与代表帧离线渲染通过。",
        )
    except (AssetTripletError, FileNotFoundError):
        return None
    except (BileFormatError, OSError, ValueError, KeyError) as exc:
        return RenderResult(str(path.relative_to(root)), None, "REJECT", None, None, None, str(exc))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    results = [outcome for path in sorted(args.root.rglob("*.bin")) if (outcome := verify(path, args.root)) is not None]
    payload = {"schema": "bile-workbench.cross-era-render-smoke/v1", "scope": "existing strict parser, XML atlas loader, and offline reference renderer", "results": [asdict(row) for row in results]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# 新增 BILE 三件套：离线代表帧冒烟", "", "| 结果 | 数量 |", "|---|---:|"]
    for status in ("PASS", "REJECT", "SKIP"):
        lines.append(f"| {status} | {sum(row.status == status for row in results)} |")
    lines.extend(["", "| 路径 | 版本 | 动画 | 槽位 | 非背景像素 | 状态 | 说明 |", "|---|---:|---|---:|---:|---|---|"])
    for row in results:
        lines.append(f"| `{row.path}` | {row.version if row.version is not None else '—'} | {row.animation or '—'} | {row.slot if row.slot is not None else '—'} | {row.non_background_pixels if row.non_background_pixels is not None else '—'} | {row.status} | {row.detail} |")
    args.output.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"已写入：{args.output}")
    print(f"已写入：{args.output.with_suffix('.md')}")


if __name__ == "__main__":
    main()
