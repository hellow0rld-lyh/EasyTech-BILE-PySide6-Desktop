"""BILE 单动画的只读静态取证档案。

本模块只投影已解析的离散槽位、保持段、Track 和 BELE 引用；不推断游戏运行时实例数，
也不修改文档、补丁或 BILE 块结构。
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from .bile_format import BileDocument
from .track_context import TrackContext, keyframe_contexts, tracks_for_animation


@dataclass(frozen=True)
class SlotCoverage:
    slot: int
    active_track_count: int
    active_channel_count: int
    keyframe_indices: tuple[int, ...]


@dataclass(frozen=True)
class KeyframeReuse:
    keyframe_index: int
    current_animation_track_count: int
    document_track_count: int
    document_animation_count: int
    target_names: tuple[str, ...]
    scope_samples: tuple[str, ...]


@dataclass(frozen=True)
class AnimationEvidence:
    animation_index: int
    animation_name: str
    bile_version: int
    frame_count: int
    channel_count: int
    static_track_count: int
    unique_keyframe_count: int
    coverage: tuple[SlotCoverage, ...]
    keyframe_reuse: tuple[KeyframeReuse, ...]
    contexts: tuple[TrackContext, ...]
    json_path: Path | None = None
    markdown_path: Path | None = None


def build_animation_evidence(document: BileDocument, animation_index: int) -> AnimationEvidence:
    """构建单个动画根的静态引用档案，不触发渲染或写入。"""
    animation = document.elements[animation_index]
    if animation.has_texture:
        raise ValueError(f"元素不是动画根：{animation.name}")
    contexts = tracks_for_animation(document, animation_index)
    coverage: list[SlotCoverage] = []
    for slot in range(animation.frame_count):
        active = tuple(context for context in contexts if context.frame_slot <= slot <= context.hold_end_slot)
        coverage.append(
            SlotCoverage(
                slot=slot,
                active_track_count=len(active),
                active_channel_count=len({context.channel_index for context in active}),
                keyframe_indices=tuple(sorted({context.keyframe_index for context in active})),
            )
        )
    reuse: list[KeyframeReuse] = []
    for keyframe_index in sorted({context.keyframe_index for context in contexts}):
        local = tuple(context for context in contexts if context.keyframe_index == keyframe_index)
        global_contexts = keyframe_contexts(document, keyframe_index)
        reuse.append(
            KeyframeReuse(
                keyframe_index=keyframe_index,
                current_animation_track_count=len(local),
                document_track_count=len(global_contexts),
                document_animation_count=len({context.animation_index for context in global_contexts}),
                target_names=tuple(sorted({context.target_element_name for context in global_contexts})),
                scope_samples=tuple(context.scope_label for context in global_contexts[:4]),
            )
        )
    return AnimationEvidence(
        animation_index=animation.index,
        animation_name=animation.name,
        bile_version=document.header.version,
        frame_count=animation.frame_count,
        channel_count=len(animation.channels),
        static_track_count=len(contexts),
        unique_keyframe_count=len(reuse),
        coverage=tuple(coverage),
        keyframe_reuse=tuple(reuse),
        contexts=contexts,
    )


def _payload(evidence: AnimationEvidence) -> dict:
    return {
        "schema": "bile-workbench.animation-evidence/v1",
        "scope": "static parsed track references only; not game runtime instance counts",
        "animation": {
            "index": evidence.animation_index,
            "name": evidence.animation_name,
            "bile_version": evidence.bile_version,
            "frame_count": evidence.frame_count,
            "channel_count": evidence.channel_count,
        },
        "summary": {
            "static_track_count": evidence.static_track_count,
            "unique_keyframe_count": evidence.unique_keyframe_count,
            "max_active_tracks": max((row.active_track_count for row in evidence.coverage), default=0),
            "max_active_channels": max((row.active_channel_count for row in evidence.coverage), default=0),
        },
        "slot_coverage": [asdict(row) for row in evidence.coverage],
        "keyframe_reuse": [asdict(row) for row in evidence.keyframe_reuse],
        "tracks": [asdict(context) for context in evidence.contexts],
    }


def _markdown(evidence: AnimationEvidence) -> str:
    max_tracks = max((row.active_track_count for row in evidence.coverage), default=0)
    max_channels = max((row.active_channel_count for row in evidence.coverage), default=0)
    lines = [
        f"# BILE 动画静态取证档案：{evidence.animation_name}",
        "",
        "> 本档案只描述解析器观察到的离散槽位、保持段与静态 Track 引用。它不等同于游戏内单位人数、引擎实例数量或最终渲染结论。",
        "",
        "## 概览",
        "",
        "| 项目 | 值 |",
        "|---|---:|",
        f"| BILE 版本 | {evidence.bile_version} |",
        f"| 动画索引 | {evidence.animation_index} |",
        f"| 槽位数 | {evidence.frame_count} |",
        f"| 通道数 | {evidence.channel_count} |",
        f"| 静态 Track 数 | {evidence.static_track_count} |",
        f"| 不同 BELE 数 | {evidence.unique_keyframe_count} |",
        f"| 单槽位最大活动 Track | {max_tracks} |",
        f"| 单槽位最大活动通道 | {max_channels} |",
        "",
        "## BELE 复用警戒",
        "",
        "同一 BELE 可能被当前动画中的多个 Track，或全文档中的多个动画根静态引用。编辑前应审阅全文档范围，而不是假定它仅影响当前画面。",
        "",
        "| BELE | 当前动画 Track | 全文档 Track | 动画根数 | 目标元素 | 静态引用示例 |",
        "|---:|---:|---:|---:|---|---|",
    ]
    for row in evidence.keyframe_reuse:
        targets = "、".join(row.target_names) or "—"
        samples = "<br>".join(row.scope_samples) or "—"
        lines.append(
            f"| {row.keyframe_index} | {row.current_animation_track_count} | {row.document_track_count} | "
            f"{row.document_animation_count} | {targets} | {samples} |"
        )
    if not evidence.keyframe_reuse:
        lines.append("| — | 0 | 0 | 0 | — | — |")
    lines.extend([
        "",
        "## 槽位覆盖",
        "",
        "| 槽位 | 活动 Track | 活动通道 | 活动 BELE |",
        "|---:|---:|---:|---|",
    ])
    for row in evidence.coverage:
        keyframes = ", ".join(str(index) for index in row.keyframe_indices) or "—"
        lines.append(f"| {row.slot} | {row.active_track_count} | {row.active_channel_count} | `{keyframes}` |")
    return "\n".join(lines) + "\n"


def write_animation_evidence(document: BileDocument, animation_index: int, output_dir: str | Path) -> AnimationEvidence:
    """写出机器可读和人工可读的只读动画取证档案。"""
    evidence = build_animation_evidence(document, animation_index)
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    stem = f"{evidence.animation_name}_static_evidence"
    json_path = destination / f"{stem}.json"
    markdown_path = destination / f"{stem}.md"
    json_path.write_text(json.dumps(_payload(evidence), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(_markdown(evidence), encoding="utf-8")
    return replace(evidence, json_path=json_path, markdown_path=markdown_path)
