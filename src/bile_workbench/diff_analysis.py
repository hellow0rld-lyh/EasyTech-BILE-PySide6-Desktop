"""BILE 候选 BIN 与原始 BIN 的可复现逐槽位像素差异分析。"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

from .bile_format import BileDocument, parse_file
from .preview_renderer import Atlas, render_frame


@dataclass(frozen=True)
class SlotDifference:
    slot: int
    changed_pixels: int
    changed_ratio: float
    bbox: tuple[int, int, int, int] | None
    artifact: str | None


@dataclass(frozen=True)
class AnimationDifferenceResult:
    animation: str
    frame_count: int
    changed_slots: int
    total_changed_pixels: int
    report_path: Path
    markdown_path: Path
    artifacts: tuple[Path, ...]
    binary_change_count: int


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pixel_delta(left: Image.Image, right: Image.Image) -> tuple[int, tuple[int, int, int, int] | None, Image.Image]:
    rgb_left = left.convert("RGB")
    rgb_right = right.convert("RGB")
    difference = ImageChops.difference(rgb_left, rgb_right)
    bbox = difference.getbbox()
    if bbox is None:
        return 0, None, difference
    count = sum(pixel != (0, 0, 0) for pixel in difference.getdata())
    return count, bbox, difference


def _make_artifact(before: Image.Image, after: Image.Image, diff: Image.Image, animation: str, slot: int, changed: int) -> Image.Image:
    width, height = before.size
    header = 30
    canvas = Image.new("RGBA", (width * 3, height + header), (24, 27, 32, 255))
    canvas.alpha_composite(before, (0, header))
    canvas.alpha_composite(after, (width, header))
    # 放大颜色差异以便肉眼定位；原始像素差异仍由 JSON 精确记录。
    hot = diff.point(lambda value: min(255, value * 4)).convert("RGBA")
    canvas.alpha_composite(hot, (width * 2, header))
    draw = ImageDraw.Draw(canvas)
    draw.text((8, 8), "Original", fill=(235, 238, 244, 255))
    draw.text((width + 8, 8), "Candidate", fill=(235, 238, 244, 255))
    draw.text((width * 2 + 8, 8), f"Heatmap · slot {slot} · {changed} px", fill=(235, 238, 244, 255))
    return canvas


def compare_animation(
    original_bin: str | Path,
    candidate_bin: str | Path,
    atlas: Atlas,
    animation: str,
    output_dir: str | Path,
    canvas_size: tuple[int, int] = (512, 384),
    max_artifacts: int = 12,
) -> AnimationDifferenceResult:
    """比较同名动画的所有槽位，输出所有数值和差异最大的若干可视化证据。"""
    original_path = Path(original_bin)
    candidate_path = Path(candidate_bin)
    original = parse_file(original_path)
    candidate = parse_file(candidate_path)
    before_element = next((item for item in original.animations if item.name == animation), None)
    after_element = next((item for item in candidate.animations if item.name == animation), None)
    if before_element is None or after_element is None:
        raise KeyError(f"原始或候选 BIN 缺少动画：{animation}")
    if before_element.frame_count != after_element.frame_count:
        raise ValueError("候选动画帧范围已变化；保守差异分析只支持相同帧数的动画")
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    binary_changes = _collect_conservative_field_changes(original, candidate)
    rows: list[SlotDifference] = []
    staged: list[tuple[int, int, Image.Image, Image.Image, Image.Image]] = []
    for slot in range(before_element.frame_count):
        before = render_frame(original, atlas, animation, slot, canvas_size=canvas_size, nested_timing="reference_v4")
        after = render_frame(candidate, atlas, animation, slot, canvas_size=canvas_size, nested_timing="reference_v4")
        changed, bbox, diff = _pixel_delta(before, after)
        if changed:
            staged.append((slot, changed, before, after, diff))
        rows.append(SlotDifference(slot, changed, changed / float(canvas_size[0] * canvas_size[1]), bbox, None))
    artifacts: list[Path] = []
    for slot, changed, before, after, diff in sorted(staged, key=lambda row: (-row[1], row[0]))[:max_artifacts]:
        path = destination / f"{animation}_slot_{slot:04d}_diff.png"
        _make_artifact(before, after, diff, animation, slot, changed).save(path)
        artifacts.append(path)
        rows[slot] = SlotDifference(rows[slot].slot, rows[slot].changed_pixels, rows[slot].changed_ratio, rows[slot].bbox, path.name)
    payload = {
        "schema": "bile-workbench.animation-diff/v1",
        "original": {"file": original_path.name, "sha256": _sha256(original_path)},
        "candidate": {"file": candidate_path.name, "sha256": _sha256(candidate_path)},
        "animation": animation,
        "frame_count": before_element.frame_count,
        "canvas_size": list(canvas_size),
        "nested_timing": "reference_v4",
        "slots": [{**asdict(row), "bbox": list(row.bbox) if row.bbox else None} for row in rows],
        "binary_field_changes": binary_changes,
    }
    report_path = destination / f"{animation}_animation_diff.json"
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    changed_rows = [row for row in rows if row.changed_pixels]
    markdown = [
        f"# 动画候选差异报告：{animation}",
        "",
        f"原始 BIN：`{original_path.name}`  ",
        f"候选 BIN：`{candidate_path.name}`  ",
        f"帧数：{before_element.frame_count}；画布：{canvas_size[0]}×{canvas_size[1]}；嵌套时钟：`reference_v4`。",
        "",
        "| 指标 | 值 |",
        "|---|---:|",
        f"| 变化槽位数 | {len(changed_rows)} |",
        f"| 总变化像素 | {sum(row.changed_pixels for row in changed_rows)} |",
        f"| 最大单槽位变化 | {max((row.changed_pixels for row in changed_rows), default=0)} |",
        f"| 保守字段变化数 | {len(binary_changes)} |",
        "",
        "| 槽位 | 变化像素 | 变化比例 | 变更边界 | 证据图 |",
        "|---:|---:|---:|---|---|",
    ]
    for row in changed_rows:
        bbox = str(row.bbox) if row.bbox else "—"
        artifact = f"[{row.artifact}]({row.artifact})" if row.artifact else "—"
        markdown.append(f"| {row.slot} | {row.changed_pixels} | {row.changed_ratio:.4%} | `{bbox}` | {artifact} |")
    if not changed_rows:
        markdown.append("| — | 0 | 0.0000% | — | — |")
    if binary_changes:
        markdown.extend(["", "## 二进制字段变化", "", "| 对象 | 索引 | 字段 | 原值 | 候选值 |", "|---|---:|---|---|---|"])
        for change in binary_changes:
            markdown.append(f"| {change['object']} | {change['index']} | `{change['field']}` | `{change['before']}` | `{change['after']}` |")
    markdown_path = destination / f"{animation}_animation_diff.md"
    markdown_path.write_text("\n".join(markdown) + "\n", encoding="utf-8")
    return AnimationDifferenceResult(animation, before_element.frame_count, len(changed_rows), sum(row.changed_pixels for row in changed_rows), report_path, markdown_path, tuple(artifacts), len(binary_changes))


def _collect_conservative_field_changes(original: BileDocument, candidate: BileDocument) -> list[dict]:
    """比较当前补丁白名单相关字段；即使当前槽位像素相同也保留审计证据。"""
    changes: list[dict] = []
    if len(original.keyframes) != len(candidate.keyframes) or len(original.elements) != len(candidate.elements):
        changes.append({"object": "document", "index": -1, "field": "record_count", "before": f"BELE={len(original.keyframes)},BMTI={len(original.elements)}", "after": f"BELE={len(candidate.keyframes)},BMTI={len(candidate.elements)}"})
        return changes
    for index, (before, after) in enumerate(zip(original.keyframes, candidate.keyframes)):
        for field in ("xx", "xy", "yx", "yy", "x", "y", "argb", "initial_phase", "playback_mode"):
            if getattr(before, field) != getattr(after, field):
                changes.append({"object": "BELE", "index": index, "field": field, "before": getattr(before, field), "after": getattr(after, field)})
    for index, (before, after) in enumerate(zip(original.elements, candidate.elements)):
        for field in ("name", "x", "y"):
            if getattr(before, field) != getattr(after, field):
                changes.append({"object": "BMTI", "index": index, "field": field, "before": getattr(before, field), "after": getattr(after, field)})
    return changes
