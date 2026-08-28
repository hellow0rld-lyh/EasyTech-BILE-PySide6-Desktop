"""严格只读验证新增 BILE 候选；不会修改源 BIN、XML、图像或新引擎容器。"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from bile_workbench.assets import AssetTripletError, discover_triplet
from bile_workbench.bile_format import BileFormatError, parse_file


@dataclass(frozen=True)
class CandidateResult:
    package: str
    path: str
    version: int | None
    status: str
    detail: str
    has_complete_triplet: bool
    element_count: int | None
    animation_count: int | None
    sprite_count: int | None
    keyframe_count: int | None
    channel_count: int | None
    max_channels: int | None
    max_frame_count: int | None


def verify(root: Path) -> list[CandidateResult]:
    results: list[CandidateResult] = []
    for path in sorted(root.rglob("*.bin")):
        prefix = path.read_bytes()[:4]
        if prefix != b"BILE":
            continue
        package = path.relative_to(root).parts[0]
        try:
            document = parse_file(path)
            animations = tuple(document.animations)
            channels = [channel for element in animations for channel in element.channels]
            try:
                discover_triplet(path)
                complete_triplet = True
            except (AssetTripletError, FileNotFoundError):
                complete_triplet = False
            results.append(
                CandidateResult(
                    package=package,
                    path=str(path.relative_to(root)),
                    version=document.header.version,
                    status="PASS",
                    detail="严格解析和累计时间线消费通过。",
                    has_complete_triplet=complete_triplet,
                    element_count=len(document.elements),
                    animation_count=len(animations),
                    sprite_count=sum(element.has_texture for element in document.elements),
                    keyframe_count=len(document.keyframes),
                    channel_count=len(channels),
                    max_channels=max((len(element.channels) for element in animations), default=0),
                    max_frame_count=max((element.frame_count for element in animations), default=0),
                )
            )
        except (BileFormatError, OSError, ValueError) as exc:
            results.append(
                CandidateResult(
                    package=package,
                    path=str(path.relative_to(root)),
                    version=None,
                    status="REJECT",
                    detail=str(exc),
                    has_complete_triplet=False,
                    element_count=None,
                    animation_count=None,
                    sprite_count=None,
                    keyframe_count=None,
                    channel_count=None,
                    max_channels=None,
                    max_frame_count=None,
                )
            )
    return results


def report(results: list[CandidateResult]) -> str:
    lines = [
        "# 新增跨代 BILE 候选：严格只读验证",
        "",
        "> 本报告仅对前四字节为 `BILE` 的新 BIN 调用既有严格解析器。`PASS` 表示文件头、节布局、引用边界和累计时间线消费通过；它不代表新字段、写回或游戏内行为已经验证。",
        "",
        "## 汇总",
        "",
        "| 指标 | 数值 |",
        "|---|---:|",
        f"| BILE 候选 | {len(results)} |",
        f"| 严格通过 | {sum(row.status == 'PASS' for row in results)} |",
        f"| 严格拒绝 | {sum(row.status == 'REJECT' for row in results)} |",
        f"| 完整传统三件套 | {sum(row.has_complete_triplet for row in results)} |",
        "",
        "## 按包汇总",
        "",
        "| 资源包 | v2 | v3 | v4 | 通过 | 完整三件套 | 最大元素 | 最大 BELE | 最大动画槽位 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    packages = sorted({row.package for row in results})
    for package in packages:
        rows = [row for row in results if row.package == package]
        passed = [row for row in rows if row.status == "PASS"]
        lines.append(
            f"| {package} | {sum(row.version == 2 for row in passed)} | {sum(row.version == 3 for row in passed)} | "
            f"{sum(row.version == 4 for row in passed)} | {len(passed)} | {sum(row.has_complete_triplet for row in passed)} | "
            f"{max((row.element_count or 0 for row in passed), default=0)} | {max((row.keyframe_count or 0 for row in passed), default=0)} | "
            f"{max((row.max_frame_count or 0 for row in passed), default=0)} |"
        )
    lines.extend([
        "",
        "## 候选明细",
        "",
        "| 路径 | 版本 | 状态 | 三件套 | 元素 | 动画 | BELE | 通道 | 最大通道 | 最大槽位 | 说明 |",
        "|---|---:|---|---|---:|---:|---:|---:|---:|---:|---|",
    ])
    for row in results:
        lines.append(
            f"| `{row.path}` | {row.version if row.version is not None else '—'} | {row.status} | "
            f"{'完整' if row.has_complete_triplet else '不完整'} | {row.element_count if row.element_count is not None else '—'} | "
            f"{row.animation_count if row.animation_count is not None else '—'} | {row.keyframe_count if row.keyframe_count is not None else '—'} | "
            f"{row.channel_count if row.channel_count is not None else '—'} | {row.max_channels if row.max_channels is not None else '—'} | "
            f"{row.max_frame_count if row.max_frame_count is not None else '—'} | {row.detail} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    results = verify(args.root)
    payload = {
        "schema": "bile-workbench.cross-era-bile-verification/v1",
        "scope": "strict existing BILE parser and triplet discovery only",
        "results": [asdict(row) for row in results],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.output.with_suffix(".md").write_text(report(results), encoding="utf-8")
    print(f"已写入：{args.output}")
    print(f"已写入：{args.output.with_suffix('.md')}")


if __name__ == "__main__":
    main()
