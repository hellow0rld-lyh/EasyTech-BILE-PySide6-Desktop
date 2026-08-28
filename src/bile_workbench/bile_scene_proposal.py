"""BILE Scene Interchange 的安全 AI 编辑提案契约。

本模块仅定义和校验意图；不直接写入 BIN。
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from .document_session import AnimationDocumentSession

PROPOSAL_SCHEMA = "easytech-bile-scene-proposal/v1"


class BileSceneProposalError(ValueError):
    pass


@dataclass(frozen=True)
class KeyframeProposal:
    keyframe_index: int
    transform: dict[str, float] | None = None
    argb: int | None = None
    initial_phase: int | None = None


@dataclass(frozen=True)
class AnchorProposal:
    element_index: int
    x: float
    y: float


@dataclass(frozen=True)
class BileSceneProposal:
    source_bin_sha256: str
    source_version: int
    keyframes: tuple[KeyframeProposal, ...]
    anchors: tuple[AnchorProposal, ...]


def proposal_template(session: AnimationDocumentSession) -> dict[str, Any]:
    """创建仅供候选审阅的 v3/v4 提案模板；不改变会话或源 BIN。"""
    snapshot = session.snapshot
    if snapshot.bile_version not in (3, 4) or not snapshot.editable:
        raise BileSceneProposalError("仅 BILE v3/v4 可导出候选提案模板；v2 严格只读")
    if not snapshot.document.keyframes:
        raise BileSceneProposalError("当前文档不含可提案的 BELE 关键帧")
    first = snapshot.document.keyframes[0]
    return {
        "schema": PROPOSAL_SCHEMA,
        "writeback": "candidate_only",
        "source": {"bin_sha256": session.edit_session.source_sha256, "version": snapshot.bile_version},
        "keyframes": [{
            "keyframe_index": 0,
            "transform": {"xx": first.xx, "xy": first.xy, "yx": first.yx, "yy": first.yy, "x": first.x, "y": first.y},
            "argb": first.argb,
            "initial_phase": first.initial_phase,
        }],
        "anchors": [],
        "note": "候选提案模板：可仅调整白名单字段；加载后只进入暂存编辑，源 BIN 不会被写入。",
    }


def export_proposal_evidence(path: str | Path, session: AnimationDocumentSession, proposal: BileSceneProposal) -> dict[str, Any]:
    """导出已接受提案与当前暂存快照；不创建或写入任何 BIN。"""
    snapshot = session.snapshot
    if snapshot.bile_version not in (3, 4) or proposal.source_version != snapshot.bile_version:
        raise BileSceneProposalError("提案证据版本与当前 BILE v3/v4 会话不匹配")
    if proposal.source_bin_sha256 != session.edit_session.source_sha256:
        raise BileSceneProposalError("提案证据源 SHA-256 与当前 BIN 不匹配")
    payload: dict[str, Any] = {
        "schema": "easytech-bile-scene-proposal-evidence/v1",
        "kind": "candidate_session_snapshot",
        "binary_writeback": "none",
        "source": {"bin_sha256": session.edit_session.source_sha256, "version": snapshot.bile_version},
        "accepted_proposal": {
            "schema": PROPOSAL_SCHEMA,
            "writeback": "candidate_only",
            "keyframes": [
                {"keyframe_index": item.keyframe_index, "transform": item.transform, "argb": item.argb, "initial_phase": item.initial_phase}
                for item in proposal.keyframes
            ],
            "anchors": [
                {"element_index": item.element_index, "x": item.x, "y": item.y}
                for item in proposal.anchors
            ],
        },
        "current_staged_patch": session.edit_session.patch_payload(),
        "note": "该快照不等同于候选 BIN，且可能包含提案加载后的后续受限人工编辑。",
    }
    try:
        Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        raise BileSceneProposalError(f"无法写入提案证据 JSON：{exc}") from exc
    return payload


def load_proposal(path: str | Path) -> BileSceneProposal:
    """从 UTF-8 JSON 文件读取并执行严格 schema/白名单验证。"""
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BileSceneProposalError(f"无法读取提案 JSON：{exc}") from exc
    if not isinstance(payload, dict):
        raise BileSceneProposalError("提案根节点必须是 JSON object")
    return parse_proposal(payload)


def parse_proposal(payload: dict[str, Any]) -> BileSceneProposal:
    if payload.get("schema") != PROPOSAL_SCHEMA:
        raise BileSceneProposalError("提案 schema 不匹配")
    if payload.get("writeback") not in (None, "candidate_only"):
        raise BileSceneProposalError("提案不得要求直接写回")
    source = payload.get("source")
    if not isinstance(source, dict) or not isinstance(source.get("bin_sha256"), str) or len(source["bin_sha256"]) != 64:
        raise BileSceneProposalError("提案缺少源 BIN SHA-256")
    version = source.get("version")
    if version not in (3, 4):
        raise BileSceneProposalError("仅 BILE v3/v4 可接受候选提案；v2 严格只读")
    allowed = {"schema", "writeback", "source", "keyframes", "anchors", "note"}
    extra = set(payload) - allowed
    if extra:
        raise BileSceneProposalError(f"提案包含禁止字段：{sorted(extra)}")
    keyframes = []
    for item in payload.get("keyframes", []):
        if not isinstance(item, dict) or set(item) - {"keyframe_index", "transform", "argb", "initial_phase"}:
            raise BileSceneProposalError("关键帧提案包含禁止字段")
        index = item.get("keyframe_index")
        if not isinstance(index, int) or index < 0:
            raise BileSceneProposalError("关键帧索引无效")
        transform = item.get("transform")
        if transform is not None and (not isinstance(transform, dict) or set(transform) != {"xx", "xy", "yx", "yy", "x", "y"} or not all(isinstance(value, (int, float)) for value in transform.values())):
            raise BileSceneProposalError("仿射提案必须完整包含 xx/xy/yx/yy/x/y")
        argb = item.get("argb")
        phase = item.get("initial_phase")
        if argb is not None and (not isinstance(argb, int) or not 0 <= argb <= 0xFFFFFFFF):
            raise BileSceneProposalError("ARGB 无效")
        if phase is not None and (not isinstance(phase, int) or not 0 <= phase <= 0xFFFFFFFF):
            raise BileSceneProposalError("initial_phase 无效")
        if transform is None and argb is None and phase is None:
            raise BileSceneProposalError("关键帧提案为空")
        keyframes.append(KeyframeProposal(index, None if transform is None else {key: float(value) for key, value in transform.items()}, argb, phase))
    anchors = []
    for item in payload.get("anchors", []):
        if not isinstance(item, dict) or set(item) != {"element_index", "x", "y"}:
            raise BileSceneProposalError("锚点提案字段无效")
        if not isinstance(item["element_index"], int) or item["element_index"] < 0 or not all(isinstance(item[name], (int, float)) for name in ("x", "y")):
            raise BileSceneProposalError("锚点提案值无效")
        anchors.append(AnchorProposal(item["element_index"], float(item["x"]), float(item["y"])))
    return BileSceneProposal(source["bin_sha256"].lower(), version, tuple(keyframes), tuple(anchors))
