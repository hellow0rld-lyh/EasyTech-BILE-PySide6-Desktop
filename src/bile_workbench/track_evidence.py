"""BILE 保守编辑的轨道影响范围取证。"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .bile_format import BileDocument
from .track_context import TrackContext, keyframe_contexts


@dataclass(frozen=True)
class KeyframeImpact:
    keyframe_index: int
    contexts: tuple[TrackContext, ...]

    @property
    def animation_names(self) -> tuple[str, ...]:
        return tuple(sorted({context.animation_name for context in self.contexts}))


@dataclass(frozen=True)
class TrackImpactEvidence:
    impacts: tuple[KeyframeImpact, ...]
    json_path: Path | None = None
    markdown_path: Path | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": "bile_track_impact_evidence",
            "keyframes": [
                {
                    "index": impact.keyframe_index,
                    "referencing_animation_names": list(impact.animation_names),
                    "references": [
                        {
                            "animation_index": context.animation_index,
                            "animation_name": context.animation_name,
                            "channel_index": context.channel_index,
                            "frame_slot": context.frame_slot,
                            "hold_end_slot": context.hold_end_slot,
                            "track_index": context.track_index,
                            "target_element_index": context.target_element_index,
                            "target_element_name": context.target_element_name,
                            "target_kind": "sprite" if context.target_is_sprite else "animation",
                        }
                        for context in impact.contexts
                    ],
                }
                for impact in self.impacts
            ],
        }

    def markdown(self) -> str:
        lines = [
            "# BILE 轨道影响范围证据",
            "",
            "> 此报告只描述原始已解析文档中 BELE 的静态引用范围。它不等同于游戏内运行时结论，也不改变任何 BIN。",
            "",
        ]
        if not self.impacts:
            lines.append("当前暂存补丁未包含 BELE 编辑；BMTI 锚点变更不使用该轨道引用表。")
            return "\n".join(lines) + "\n"
        for impact in self.impacts:
            lines.extend(
                [
                    f"## BELE[{impact.keyframe_index}]",
                    "",
                    f"静态引用：{len(impact.contexts)} 条 Track，涉及 {len(impact.animation_names)} 个动画根。",
                    "",
                    "| 动画根 | 通道 | 保持段 | Track | 目标 | 类型 |",
                    "|---|---:|---:|---:|---|---|",
                ]
            )
            for context in impact.contexts:
                lines.append(
                    f"| {context.animation_name} | {context.channel_index + 1} | {context.frame_slot}–{context.hold_end_slot} "
                    f"| {context.track_index + 1} | {context.target_element_name} | {'精灵' if context.target_is_sprite else '子动画'} |"
                )
            lines.append("")
        return "\n".join(lines) + "\n"


def build_track_impact_evidence(document: BileDocument, keyframe_indices: list[int] | tuple[int, ...]) -> TrackImpactEvidence:
    """从已验证的文档图构造 BELE 编辑的静态影响范围。"""
    impacts = tuple(KeyframeImpact(index, keyframe_contexts(document, index)) for index in sorted(set(keyframe_indices)))
    return TrackImpactEvidence(impacts)


def write_track_impact_evidence(
    document: BileDocument,
    keyframe_indices: list[int] | tuple[int, ...],
    output_dir: str | Path,
    stem: str = "track_impact",
) -> TrackImpactEvidence:
    """写入可与候选像素差异和游戏内回归案例并列保存的取证文件。"""
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    evidence = build_track_impact_evidence(document, keyframe_indices)
    json_path = destination / f"{stem}.json"
    markdown_path = destination / f"{stem}.md"
    json_path.write_text(json.dumps(evidence.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(evidence.markdown(), encoding="utf-8")
    return TrackImpactEvidence(evidence.impacts, json_path, markdown_path)
