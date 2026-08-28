from __future__ import annotations

from .bile_scene_proposal import BileSceneProposal, BileSceneProposalError
from .document_session import AnimationDocumentSession, SetAnchorCommand, SetKeyframeCommand


def apply_scene_proposal(session: AnimationDocumentSession, proposal: BileSceneProposal) -> int:
    snapshot = session.snapshot
    if snapshot.bile_version not in (3, 4) or proposal.source_version != snapshot.bile_version:
        raise BileSceneProposalError("提案版本与当前可编辑 BILE v3/v4 文档不匹配")
    if proposal.source_bin_sha256 != session.edit_session.source_sha256:
        raise BileSceneProposalError("提案源 SHA-256 与当前 BIN 不匹配")
    commands = []
    for item in proposal.keyframes:
        if not 0 <= item.keyframe_index < len(snapshot.document.keyframes):
            raise BileSceneProposalError(f"关键帧索引越界：{item.keyframe_index}")
        current = snapshot.document.keyframes[item.keyframe_index]
        transform = item.transform or {"xx": current.xx, "xy": current.xy, "yx": current.yx, "yy": current.yy, "x": current.x, "y": current.y}
        commands.append(SetKeyframeCommand(item.keyframe_index, transform, current.argb if item.argb is None else item.argb, current.initial_phase if item.initial_phase is None else item.initial_phase, "应用 AI 场景关键帧提案"))
    for item in proposal.anchors:
        if not 0 <= item.element_index < len(snapshot.document.elements):
            raise BileSceneProposalError(f"元素索引越界：{item.element_index}")
        commands.append(SetAnchorCommand(item.element_index, item.x, item.y, "应用 AI 场景锚点提案"))
    for command in commands:
        session.execute(command)
    return len(commands)
