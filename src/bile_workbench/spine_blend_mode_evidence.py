from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


_BLEND_NAMES = {0: "normal", 1: "additive", 2: "multiply", 3: "screen"}


class _Slot(Protocol):
    index: int
    name: str
    blend_mode: int


@dataclass(frozen=True)
class NonNormalBlendEvidence:
    slot_index: int
    slot_name: str
    blend_mode_ordinal: int
    blend_mode_name: str
    static_state: str = "static_slot_fact_only"
    normal_alpha_fallback: str = "existing_renderer_may_preview_as_normal_alpha_only"
    non_normal_blend_application: str = "forbidden"
    writeback: str = "forbidden"


def collect_non_normal_blend_evidence(slots: tuple[_Slot, ...]) -> tuple[NonNormalBlendEvidence, ...]:
    """仅从已读取的 static slot ordinal 生成审计事实；不实施 blend。"""
    evidence: list[NonNormalBlendEvidence] = []
    for slot in slots:
        name = _BLEND_NAMES.get(slot.blend_mode)
        if slot.blend_mode == 0:
            continue
        if name is None:
            raise ValueError(f"slot {slot.index} 包含未验证的 blend ordinal：{slot.blend_mode}")
        evidence.append(NonNormalBlendEvidence(slot.index, slot.name, slot.blend_mode, name))
    return tuple(evidence)
