"""AI Motion DSL v1：仅用于 Spine pose 审阅的可逆内存提案。

该模块故意不包含任何 BIN 序列化或补丁代码。提案不能扩大 pose 投影器的
runtime 覆盖范围；每次应用都会产生明确的非 runtime 覆盖诊断。
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, Mapping

from .spine_pose import PoseProjection, project_pose
from .spine_pose_renderer import PoseRender, render_pose_layers
from .spine_workspace import SpinePoseSession

MOTION_DSL_SCHEMA = "easytech-motion-proposal/v1"
_ALLOWED_BONE_DELTA_FIELDS = frozenset(("x", "y", "rotation", "scale_x", "scale_y", "shear_x", "shear_y"))


class MotionDslError(ValueError):
    """提案格式、绑定或受限选择器无效。"""


def source_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class MotionTimeRange:
    start: float
    end: float

    def factor_at(self, time: float) -> float:
        if time < self.start:
            return 0.0
        if self.end <= self.start or time >= self.end:
            return 1.0
        return (time - self.start) / (self.end - self.start)


@dataclass(frozen=True)
class BoneDeltaOperation:
    operation_id: str
    bone: str
    time: MotionTimeRange
    delta: tuple[tuple[str, float], ...]
    kind: Literal["bone_delta"] = "bone_delta"


@dataclass(frozen=True)
class SlotAttachmentOperation:
    operation_id: str
    slot: str
    time: MotionTimeRange
    attachment: str | None
    kind: Literal["slot_attachment"] = "slot_attachment"


MotionOperation = BoneDeltaOperation | SlotAttachmentOperation


@dataclass(frozen=True)
class MotionProposal:
    name: str
    source_sha256: str
    engine: str
    animation: str
    operations: tuple[MotionOperation, ...]
    schema: str = MOTION_DSL_SCHEMA
    read_only: bool = True
    writeback: Literal["forbidden"] = "forbidden"


@dataclass(frozen=True)
class ProposalPreview:
    projection: PoseProjection
    rendered: PoseRender
    active_operation_ids: tuple[str, ...]
    proposal_diagnostics: tuple[str, ...]


def _finite_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise MotionDslError(f"{label} 必须是有限数字")
    return float(value)


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise MotionDslError(f"{label} 必须是对象")
    return value


def _time_range(value: object, duration: float, label: str) -> MotionTimeRange:
    raw = _mapping(value, f"{label}.time")
    start = _finite_number(raw.get("start"), f"{label}.time.start")
    end = _finite_number(raw.get("end"), f"{label}.time.end")
    if start < 0 or end < start or end > duration:
        raise MotionDslError(f"{label}.time 必须落在当前动画的 0..{duration:.6f} 秒范围内")
    return MotionTimeRange(start, end)


def parse_motion_proposal(payload: Mapping[str, Any], session: SpinePoseSession) -> MotionProposal:
    """解析并验证提案；不改变会话、图集或源 BIN。"""
    if payload.get("schema") != MOTION_DSL_SCHEMA:
        raise MotionDslError(f"schema 必须为 {MOTION_DSL_SCHEMA}")
    if payload.get("read_only") is not True or payload.get("writeback") != "forbidden":
        raise MotionDslError("AI Motion DSL v1 必须声明 read_only=true 且 writeback=forbidden")
    source = _mapping(payload.get("source"), "source")
    digest = source.get("sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        raise MotionDslError("source.sha256 必须是 64 位十六进制 SHA-256")
    actual_digest = source_sha256(session.workspace.bin_path)
    if digest.lower() != actual_digest:
        raise MotionDslError("提案绑定的 source.sha256 与当前 Spine BIN 不匹配；已拒绝应用")
    engine = source.get("engine")
    if engine != session.workspace.engine:
        raise MotionDslError("提案绑定的 source.engine 与当前工作区不匹配")
    animation = source.get("animation")
    if animation != session.animation.name:
        raise MotionDslError("提案绑定的 source.animation 与当前 pose 会话不匹配")
    name = payload.get("name", "未命名 AI Motion 提案")
    if not isinstance(name, str) or not name.strip() or len(name) > 120:
        raise MotionDslError("name 必须是 1..120 个字符的非空文本")
    raw_ops = payload.get("operations")
    if not isinstance(raw_ops, list) or not raw_ops or len(raw_ops) > 256:
        raise MotionDslError("operations 必须是含 1..256 项的数组")
    bone_names = {bone.name for bone in session.workspace.document.bones}
    slot_names = {slot.name for slot in session.workspace.document.slots}
    attachment_names_by_slot: dict[str, set[str]] = {name: set() for name in slot_names}
    for attachment in session.workspace.document.region_attachments:
        attachment_names_by_slot[session.workspace.document.slots[attachment.slot_index].name].add(attachment.name)
    operations: list[MotionOperation] = []
    ids: set[str] = set()
    for index, raw_op in enumerate(raw_ops):
        item = _mapping(raw_op, f"operations[{index}]")
        operation_id = item.get("id")
        if not isinstance(operation_id, str) or not operation_id or len(operation_id) > 80 or operation_id in ids:
            raise MotionDslError(f"operations[{index}].id 必须唯一且为 1..80 个字符")
        ids.add(operation_id)
        kind = item.get("kind")
        time_range = _time_range(item.get("time"), session.animation.duration, f"operations[{index}]")
        if kind == "bone_delta":
            bone = item.get("bone")
            if not isinstance(bone, str) or bone not in bone_names:
                raise MotionDslError(f"operations[{index}].bone 必须是当前静态骨架中的骨骼名")
            delta_raw = _mapping(item.get("delta"), f"operations[{index}].delta")
            if not delta_raw or set(delta_raw) - _ALLOWED_BONE_DELTA_FIELDS:
                allowed = "、".join(sorted(_ALLOWED_BONE_DELTA_FIELDS))
                raise MotionDslError(f"operations[{index}].delta 必须只包含：{allowed}")
            delta = tuple(sorted((field, _finite_number(amount, f"operations[{index}].delta.{field}")) for field, amount in delta_raw.items()))
            operations.append(BoneDeltaOperation(operation_id, bone, time_range, delta))
        elif kind == "slot_attachment":
            slot = item.get("slot")
            attachment = item.get("attachment")
            if not isinstance(slot, str) or slot not in slot_names:
                raise MotionDslError(f"operations[{index}].slot 必须是当前静态骨架中的插槽名")
            if attachment is not None and (not isinstance(attachment, str) or attachment not in attachment_names_by_slot[slot]):
                raise MotionDslError(f"operations[{index}].attachment 必须是 slot {slot!r} 的已知 region attachment 名或 null")
            operations.append(SlotAttachmentOperation(operation_id, slot, time_range, attachment))
        else:
            raise MotionDslError(f"operations[{index}].kind 仅支持 bone_delta 或 slot_attachment")
    return MotionProposal(name.strip(), actual_digest, session.workspace.engine, session.animation.name, tuple(operations))


def load_motion_proposal(path: Path, session: SpinePoseSession) -> MotionProposal:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MotionDslError(f"无法读取 Motion DSL JSON：{exc}") from exc
    return parse_motion_proposal(_mapping(payload, "根对象"), session)


def proposal_template(session: SpinePoseSession) -> dict[str, Any]:
    """生成可交给 AI 填写的、源文件绑定的安全模板。"""
    document = session.workspace.document
    return {
        "schema": MOTION_DSL_SCHEMA,
        "name": f"{session.animation.name} 的只读 pose 提案",
        "read_only": True,
        "writeback": "forbidden",
        "source": {"sha256": source_sha256(session.workspace.bin_path), "engine": session.workspace.engine, "animation": session.animation.name},
        "operations": [
            {
                "id": "raise_root_01",
                "kind": "bone_delta",
                "bone": document.bones[0].name if document.bones else "<bone-name>",
                "time": {"start": 0.0, "end": min(0.2, session.animation.duration)},
                "delta": {"y": 8.0, "rotation": 0.0},
            }
        ],
        "contract": "仅用于内存 pose 预览；所有字段为相对增量；不生成补丁、不重写 BIN；未实现的 Spine runtime 特性仍会显示降级诊断。",
    }


class MotionProposalSession:
    """管理同一 pose 会话上的提案叠加、撤销与重做；状态只存在于内存。"""

    def __init__(self, pose_session: SpinePoseSession) -> None:
        self.pose_session = pose_session
        self._active: list[MotionProposal] = []
        self._undo: list[MotionProposal] = []
        self._redo: list[MotionProposal] = []

    @property
    def active_proposals(self) -> tuple[MotionProposal, ...]:
        return tuple(self._active)

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def apply(self, proposal: MotionProposal) -> None:
        if proposal.source_sha256 != source_sha256(self.pose_session.workspace.bin_path):
            raise MotionDslError("源 BIN 在提案解析后发生变化；已拒绝应用内存提案")
        if proposal.engine != self.pose_session.workspace.engine or proposal.animation != self.pose_session.animation.name:
            raise MotionDslError("提案不能跨引擎或跨动画根应用")
        self._active.append(proposal)
        self._undo.append(proposal)
        self._redo.clear()

    def undo(self) -> MotionProposal | None:
        if not self._undo:
            return None
        proposal = self._undo.pop()
        self._active.remove(proposal)
        self._redo.append(proposal)
        return proposal

    def redo(self) -> MotionProposal | None:
        if not self._redo:
            return None
        proposal = self._redo.pop()
        self._active.append(proposal)
        self._undo.append(proposal)
        return proposal

    def preview(self, time: float) -> ProposalPreview:
        document = self.pose_session.workspace.document
        bone_indexes = {bone.name: bone.index for bone in document.bones}
        slot_indexes = {slot.name: slot.index for slot in document.slots}
        deltas: dict[int, dict[str, float]] = {}
        attachments: dict[int, str | None] = {}
        active_ids: list[str] = []
        diagnostics: list[str] = []
        for proposal in self._active:
            for operation in proposal.operations:
                factor = operation.time.factor_at(time)
                if factor <= 0:
                    continue
                active_ids.append(operation.operation_id)
                if isinstance(operation, BoneDeltaOperation):
                    target = deltas.setdefault(bone_indexes[operation.bone], {})
                    for field, value in operation.delta:
                        target[field] = target.get(field, 0.0) + value * factor
                else:
                    attachments[slot_indexes[operation.slot]] = operation.attachment
        if active_ids:
            diagnostics.append("AI Motion DSL 提案覆盖已在内存应用；该画面不代表完整 Spine runtime，且绝不写回 BIN。")
        projection = project_pose(document, self.pose_session.animation, time, bone_deltas=deltas or None, attachment_overrides=attachments or None)
        rendered = render_pose_layers(projection, self.pose_session.workspace.atlas)
        return ProposalPreview(projection, rendered, tuple(active_ids), tuple(diagnostics + list(rendered.diagnostics)))


def export_proposal_evidence(path: Path, proposal_session: MotionProposalSession, sample_times: tuple[float, ...] = ()) -> Path:
    """导出已激活提案及可重复 sample pose 的只读证据 JSON。"""
    pose_session = proposal_session.pose_session
    times = sample_times or (0.0, pose_session.animation.duration * 0.5, pose_session.animation.duration)
    previews = [proposal_session.preview(time) for time in times]
    payload = {
        "schema": MOTION_DSL_SCHEMA,
        "read_only": True,
        "writeback": "forbidden",
        "source": {"sha256": source_sha256(pose_session.workspace.bin_path), "engine": pose_session.workspace.engine, "animation": pose_session.animation.name},
        "active_proposals": [
            {
                "name": proposal.name,
                "source_sha256": proposal.source_sha256,
                "operations": [asdict(operation) for operation in proposal.operations],
            }
            for proposal in proposal_session.active_proposals
        ],
        "samples": [
            {
                "requested_time": time,
                "effective_time": preview.projection.effective_time,
                "active_operation_ids": list(preview.active_operation_ids),
                "coverage_complete": preview.projection.coverage_complete,
                "layer_count": preview.rendered.rendered_layer_count,
                "diagnostics": list(preview.proposal_diagnostics),
            }
            for time, preview in zip(times, previews)
        ],
        "boundary": "AI Motion DSL 只作用于内存 pose 预览，可撤销；不生成任何 Spine BIN 补丁、不能绕过未实现 runtime 特性。",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
