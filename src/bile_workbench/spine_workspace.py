"""欧7/征2 Spine 静态与动画结构的只读工作区服务。"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from .spine38_format import Spine38FormatError, Spine38StaticDocument, parse_file as parse_spine38
from .spine38_timeline import Spine38AnimationArchive, parse_spine38_animations, parse_spine38_pose_animation
from .spine41_format import Spine41StaticDocument, parse_file as parse_spine41
from .spine41_timeline import Spine41AnimationArchive, parse_spine41_animations, parse_spine41_pose_animation
from .spine_atlas import SpineAtlas, SpineAtlasError, load_spine_atlas
from .spine_pose import PoseAnimation, PoseProjection, project_pose
from .spine_attachment_evidence import attachment_evidence_status
from .spine_sequence_atlas_validation import validate_sequence_atlas_candidates
from .spine_linked_mesh_validation import validate_linked_mesh_parent
from .spine_sequence_timeline_static_validation import validate_sequence_timeline_static_range
from .spine_clipping_validation import validate_clipping_static_boundary
from .spine_blend_mode_evidence import collect_non_normal_blend_evidence
from .spine_pose_renderer import PoseRender, render_pose_layers

SpineStaticDocument = Spine38StaticDocument | Spine41StaticDocument
SpineTimelineArchive = Spine38AnimationArchive | Spine41AnimationArchive


@dataclass(frozen=True)
class SpineStaticWorkspace:
    bin_path: Path
    atlas_path: Path
    engine: Literal["spine38", "spine41"]
    document: SpineStaticDocument
    atlas: SpineAtlas
    timeline_archive: SpineTimelineArchive | None
    timeline_error: str | None

    @property
    def timeline_count(self) -> int:
        return sum(len(animation.timelines) for animation in self.timeline_archive.animations) if self.timeline_archive else 0


@dataclass(frozen=True)
class SpinePoseSession:
    """单 animation 的只读 pose 审阅缓存；不持有任何可写回状态。"""
    workspace: SpineStaticWorkspace
    animation: PoseAnimation

    def preview(self, time: float) -> tuple[PoseProjection, PoseRender]:
        projection = project_pose(self.workspace.document, self.animation, time)
        return projection, render_pose_layers(projection, self.workspace.atlas)


def create_pose_session(workspace: SpineStaticWorkspace, animation_name: str) -> SpinePoseSession:
    if workspace.timeline_archive is None:
        raise Spine38FormatError("当前 Spine 动画段未通过严格读取，不能建立 pose 审阅会话")
    if workspace.engine == "spine38":
        _, animation = parse_spine38_pose_animation(workspace.bin_path, animation_name)
    else:
        _, animation = parse_spine41_pose_animation(workspace.bin_path, animation_name)
    return SpinePoseSession(workspace, animation)


def load_spine_static_workspace(bin_path: Path) -> SpineStaticWorkspace:
    """自动分流已验证的欧7 3.8 与征2 4.1，并优先读取完整 animations 段。"""
    atlas_path = bin_path.with_suffix(".atlas")
    if not atlas_path.exists():
        raise FileNotFoundError(f"未找到同名 Spine ATLAS：{atlas_path.name}")
    failures: list[str] = []
    parsers = (
        ("spine38", parse_spine38, parse_spine38_animations),
        ("spine41", parse_spine41, parse_spine41_animations),
    )
    for engine, static_parser, timeline_parser in parsers:
        try:
            document = static_parser(bin_path)
            atlas = load_spine_atlas(atlas_path)
        except (Spine38FormatError, SpineAtlasError, OSError) as exc:
            failures.append(f"{engine}: {exc}")
            continue
        try:
            archive = timeline_parser(bin_path)
            return SpineStaticWorkspace(bin_path, atlas_path, engine, archive.static, atlas, archive, None)
        except (Spine38FormatError, OSError) as exc:
            # 保留静态审阅能力，但不把未完整消费的动画段误标为已读取。
            return SpineStaticWorkspace(bin_path, atlas_path, engine, document, atlas, None, str(exc))
    raise Spine38FormatError("不是当前已验证的欧7 Spine 3.8 或征2 Spine 4.1 静态资源。\n" + "\n".join(failures))


def _timeline_manifest(workspace: SpineStaticWorkspace) -> dict | None:
    archive = workspace.timeline_archive
    if archive is None:
        return None
    return {
        "animation_start": archive.animation_start,
        "animation_end": archive.animation_end,
        "event_definitions": list(archive.event_names),
        "timeline_type_counts": archive.timeline_type_counts,
        "animations": [asdict(animation) for animation in archive.animations],
        "full_file_consumption": archive.animation_end == workspace.bin_path.stat().st_size,
    }


def _sequence_timeline_evidence(workspace: SpineStaticWorkspace) -> tuple[object, ...]:
    """汇总 animation archive 的只读 sequence timeline 证据，不进入 pose 或渲染路径。"""
    if workspace.timeline_archive is None:
        return ()
    return tuple(
        item
        for animation in workspace.timeline_archive.animations
        for item in getattr(animation, "sequence_timeline_evidence", ())
    )


def static_manifest(workspace: SpineStaticWorkspace) -> dict:
    document = asdict(workspace.document)
    document["source_path"] = str(workspace.bin_path)
    linked_meshes = getattr(workspace.document, "linked_mesh_evidence", ())
    sequences = getattr(workspace.document, "sequence_evidence", ())
    clippings = getattr(workspace.document, "clipping_evidence", ())
    evidence_status = attachment_evidence_status(linked_meshes, sequences)
    linked_mesh_validations = tuple(validate_linked_mesh_parent(item, workspace.document.mesh_attachments, sequences) for item in linked_meshes)
    sequence_validations = tuple(validate_sequence_atlas_candidates(item, workspace.atlas.regions) for item in sequences)
    sequence_timeline_evidence = _sequence_timeline_evidence(workspace)
    sequence_timeline_static_validations = tuple(validate_sequence_timeline_static_range(item, sequences) for item in sequence_timeline_evidence)
    clipping_validations = tuple(validate_clipping_static_boundary(item, workspace.document.slots) for item in clippings)
    blend_evidence = collect_non_normal_blend_evidence(workspace.document.slots)
    full_timeline = workspace.timeline_archive is not None
    return {
        "schema": "easytech-spine-workspace/v2",
        "read_only": True,
        "writeback": "forbidden",
        "engine": workspace.engine,
        "bin": str(workspace.bin_path),
        "atlas": {
            "path": str(workspace.atlas_path),
            "image": str(workspace.atlas.image_path),
            "dialect": workspace.atlas.dialect,
            "page_name": workspace.atlas.page_name,
            "image_size": workspace.atlas.image_size,
            "regions": [asdict(region) for region in workspace.atlas.regions],
        },
        "static_document": document,
        "slot_blend_evidence": {
            "non_normal_slots": [asdict(item) for item in blend_evidence],
            "normal_alpha_fallback": "existing_renderer_may_preview_as_normal_alpha_only",
            "non_normal_blend_application": "forbidden",
            "writeback": "forbidden",
        },
        "attachment_evidence": {
            "linked_meshes": [asdict(item) for item in linked_meshes],
            "linked_mesh_parent_validations": [asdict(item) for item in linked_mesh_validations],
            "sequences": [asdict(item) for item in sequences],
            "clippings": [asdict(item) for item in clippings],
            "clipping_static_validations": [asdict(item) for item in clipping_validations],
            "status": asdict(evidence_status),
            "sequence_atlas_validations": [asdict(item) for item in sequence_validations],
            "sequence_timeline_evidence": [asdict(item) for item in sequence_timeline_evidence],
            "sequence_timeline_static_validations": [asdict(item) for item in sequence_timeline_static_validations],
            "selection": "forbidden",
            "selection_detail": "raw mode/index/delay evidence does not select sequence frames",
            "rendering": "forbidden; evidence-only metadata does not select frames, render linked mesh/sequence attachments, or apply clipping",
        },
        "timeline_document": _timeline_manifest(workspace),
        "boundary": {
            "parsed": "static skeleton, constraints, skins, attachments and complete animations timeline" if full_timeline else "header, strings, bones, slots, constraints, skins and static attachments through skins end",
            "not_decoded": "IK softness/non-direct chains, local/relative transform constraints, advanced transform inheritance, dark/two-color blend, non-normal slot blend, mesh/deform/sequence/clipping rendering and full runtime playback" if full_timeline else "events and animation timelines after static_end",
            "pose_preview": "read-only setup-blend pose supports verified bone tracks, cubic Bezier, slot attachment/light color alpha, draw-order, IK/transform constraint mix tracks, normal-transform IK subset and absolute-world transform subset; per-frame diagnostics declare remaining downgrade features",
            "timeline_error": workspace.timeline_error,
            "editing": "not implemented; source BIN remains unmodified",
        },
    }


def export_static_manifest(workspace: SpineStaticWorkspace, output: Path) -> Path:
    output.write_text(json.dumps(static_manifest(workspace), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


def diagnostics_text(workspace: SpineStaticWorkspace) -> str:
    document = workspace.document
    header = document.header
    linked_meshes = getattr(document, "linked_mesh_evidence", ())
    evidence_status = attachment_evidence_status(linked_meshes, getattr(document, "sequence_evidence", ()))
    sequence_evidence = getattr(document, "sequence_evidence", ())
    clipping_evidence = getattr(document, "clipping_evidence", ())
    clipping_validations = tuple(validate_clipping_static_boundary(item, document.slots) for item in clipping_evidence)
    blend_evidence = collect_non_normal_blend_evidence(document.slots)
    blend_counts = {name: sum(item.blend_mode_name == name for item in blend_evidence) for name in ("additive", "multiply", "screen")}
    clipping_verified = sum(item.state == "clipping_static_boundary_verified_only" for item in clipping_validations)
    clipping_rejected = sum(item.state == "clipping_static_boundary_rejected" for item in clipping_validations)
    linked_mesh_validations = tuple(validate_linked_mesh_parent(item, document.mesh_attachments, sequence_evidence) for item in linked_meshes)
    linked_verified = sum(item.state == "verified_static_identity_only" for item in linked_mesh_validations)
    linked_sequence_mesh_verified = sum(item.state == "verified_static_identity_sequence_mesh_only" for item in linked_mesh_validations)
    linked_rejected = sum(item.state == "candidate_parent_rejected" for item in linked_mesh_validations)
    lines = [
        f"Spine 工作区（{workspace.engine}）",
        f"资源：{workspace.bin_path.name}",
        f"版本：{header.version}",
        f"骨骼 / 插槽：{len(document.bones)} / {len(document.slots)}",
        f"皮肤 / 区域附件：{len(document.skin_names)} / {len(document.region_attachments)}",
        f"约束 IK / Transform / Path：{document.ik_constraint_count} / {document.transform_constraint_count} / {document.path_constraint_count}",
        f"ATLAS：{workspace.atlas_path.name} · {workspace.atlas.dialect} · {len(workspace.atlas.regions)} 个区域",
        f"Attachment evidence：linked mesh {evidence_status.linked_mesh_count} [{evidence_status.linked_mesh_state}] · sequence {evidence_status.sequence_count} [{evidence_status.sequence_state}] · clipping {len(clipping_evidence)} [{'captured_static_only' if clipping_evidence else 'not_captured_in_current_sample'}]（仅审计，不渲染）",
        f"Linked mesh 父级静态身份：普通 mesh 已核验 {linked_verified} · sequence mesh 身份已核验 {linked_sequence_mesh_verified} · 拒绝 {linked_rejected}（不解析顶点、不选帧、不渲染）。",
        f"Clipping 静态边界：已核验 {clipping_verified} · 拒绝 {clipping_rejected}（不保留顶点、不应用裁剪、不渲染）。",
        f"非 normal slot blend 静态证据：additive {blend_counts['additive']} · multiply {blend_counts['multiply']} · screen {blend_counts['screen']}（renderer 仍仅 normal-alpha fallback；非 normal 合成禁止）。",
    ]
    if workspace.timeline_archive is not None:
        archive = workspace.timeline_archive
        sequence_timeline_evidence = _sequence_timeline_evidence(workspace)
        sequence_timeline_frame_count = sum(len(item.frames) for item in sequence_timeline_evidence)
        sequence_timeline_static_validations = tuple(validate_sequence_timeline_static_range(item, getattr(document, "sequence_evidence", ())) for item in sequence_timeline_evidence)
        sequence_timeline_span_observed = sum(item.state == "timeline_static_identity_verified_raw_region_index_observed_only" for item in sequence_timeline_static_validations)
        sequence_timeline_span_outside = sum(item.state == "timeline_static_identity_verified_raw_region_index_outside_only" for item in sequence_timeline_static_validations)
        sequence_timeline_static_rejected = sum(item.state == "timeline_static_attachment_rejected" for item in sequence_timeline_static_validations)
        lines.extend((
            f"动画根 / 时间线：{len(archive.animations)} / {workspace.timeline_count}",
            f"动画读取边界：{archive.animation_start}..{archive.animation_end - 1}；全文件消费：是",
            f"时间线类型：{json.dumps(archive.timeline_type_counts, ensure_ascii=False, sort_keys=True)}",
            f"Sequence timeline 原始证据：{len(sequence_timeline_evidence)} 条 / {sequence_timeline_frame_count} 帧（mode/index/delay；仅审计，不选帧、不渲染）。",
            f"Sequence timeline–static range：raw region index 范围内 {sequence_timeline_span_observed} · 范围外 {sequence_timeline_span_outside} · static identity 拒绝 {sequence_timeline_static_rejected}（不解释 mode、不选帧）。",
            "只读 pose：已支持 bone 变换、cubic Bezier、slot attachment/light RGBA/alpha、draw-order、IK/transform mix timeline，以及受限 normal IK / absolute-world transform（按每帧诊断显示覆盖）。",
            "仍未实现：IK softness/非直接链、local/relative transform、复杂 transform inheritance、dark/two-color、非 normal blend、mesh/deform/sequence 与完整 runtime playback。",
        ))
    else:
        lines.extend((
            f"静态读取边界：0..{document.static_end - 1}；未解码 animations 尾部：{document.undecoded_tail_bytes} 字节",
            f"动画读取状态：未通过严格累计消费；原因：{workspace.timeline_error}",
        ))
    lines.append("写回边界：Spine 新引擎分支当前严格只读，不生成补丁、不重写 BIN。")
    return "\n".join(lines)
