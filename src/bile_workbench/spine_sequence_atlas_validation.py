"""Spine sequence 静态帧范围与 ATLAS 名称的只读核验；不执行帧选择或渲染。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .spine_attachment_evidence import SequenceEvidence
from .spine_atlas import SpineAtlasRegion


@dataclass(frozen=True)
class SequenceAtlasValidation:
    attachment: str
    expected_region_names: tuple[str, ...]
    matched_region_names: tuple[str, ...]
    missing_region_names: tuple[str, ...]
    duplicate_region_names: tuple[str, ...]
    state: str
    rendering_state: str = "forbidden"


def validate_sequence_atlas_candidates(evidence: SequenceEvidence, regions: Iterable[SpineAtlasRegion]) -> SequenceAtlasValidation:
    """核验完整零填充候选范围；任何问题都只返回拒绝状态。"""
    if evidence.count <= 0 or evidence.digits < 0:
        return SequenceAtlasValidation(evidence.name, (), (), (), (), "invalid_static_range")
    expected = tuple(f"{evidence.name}{index:0{evidence.digits}d}" for index in range(evidence.start, evidence.start + evidence.count))
    by_name: dict[str, int] = {}
    for region in regions:
        by_name[region.name] = by_name.get(region.name, 0) + 1
    matched = tuple(name for name in expected if by_name.get(name) == 1)
    missing = tuple(name for name in expected if name not in by_name)
    duplicates = tuple(name for name in expected if by_name.get(name, 0) > 1)
    state = "candidate_range_verified_static_only" if not missing and not duplicates else "candidate_range_rejected"
    return SequenceAtlasValidation(evidence.name, expected, matched, missing, duplicates, state)
