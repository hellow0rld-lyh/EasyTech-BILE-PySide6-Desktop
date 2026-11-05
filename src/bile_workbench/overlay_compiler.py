"""Sequential Existing-BILE Edit Set overlay compiler.

This module consumes a validated Project Edit Set, applies field overlays in
sequence, validates every intermediate byte image, and publishes only a separate
candidate through the Safe Mutation Engine.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .raw_image import RawBileImage
from .safe_mutation import (
    BileMutationBuffer,
    BileMutationError,
    BileMutationReport,
    publish_verified_candidate,
    verify_candidate_bytes,
)
from .project_model import (
    _load_project_files,
    validate_project,
)


class OverlayCompilationError(BileMutationError):
    """Edit Set replay or candidate publication failed; no partial output is accepted."""


@dataclass(frozen=True)
class OverlayOperationResult:
    operation_id: str
    sequence: int
    target: str
    field: str
    storage_section: str
    storage_offset: int
    width: int
    changed_byte_offsets: tuple[int, ...]


@dataclass(frozen=True)
class OverlayCompilationReport:
    project_dir: str
    output_path: str
    input_sha256: str
    output_sha256: str
    size: int
    version: int
    operation_count: int
    changed_byte_offsets: tuple[int, ...]
    operations: tuple[OverlayOperationResult, ...]
    mutation_report: BileMutationReport


def _metadata_object_digest(*payloads: dict[str, Any]) -> str:
    encoded = json.dumps(
        payloads, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _metadata_digest(root: Path, project: dict[str, Any]) -> str:
    paths = (
        "project.json",
        project["paths"]["assetManifest"],
        project["paths"]["recordIdentities"],
        project["paths"]["editSet"],
    )
    digest = hashlib.sha256()
    for relative in paths:
        path = root / relative
        data = path.read_bytes()
        encoded = relative.encode("utf-8")
        digest.update(len(encoded).to_bytes(4, "little"))
        digest.update(encoded)
        digest.update(len(data).to_bytes(8, "little"))
        digest.update(data)
    return digest.hexdigest()


def _planned_changed_offsets(
    original: bytes,
    final_overlay: dict[int, int],
) -> tuple[int, ...]:
    offsets = []
    for offset, value in final_overlay.items():
        if not 0 <= offset < len(original) or not 0 <= value <= 0xFF:
            raise OverlayCompilationError("Edit Set overlay 超出原始 BIN 字节边界")
        if original[offset] != value:
            offsets.append(offset)
    return tuple(sorted(offsets))


def _resolve_output_outside_project(root: Path, output_path: str | Path) -> Path:
    output = Path(output_path).expanduser().absolute()
    if not output.name or output.is_symlink():
        raise OverlayCompilationError("候选 BIN 输出路径无效或是符号链接")
    if not output.parent.is_dir():
        raise FileNotFoundError(f"候选 BIN 输出目录不存在：{output.parent}")
    resolved = output.parent.resolve(strict=True) / output.name
    try:
        resolved.relative_to(root.resolve(strict=True))
    except ValueError:
        return resolved
    raise OverlayCompilationError("候选 BIN 必须另存到 Project 目录之外；Project 保持 reference-only")


def compile_project_candidate(
    project_dir: str | Path,
    output_path: str | Path,
    *,
    overwrite: bool = False,
) -> OverlayCompilationReport:
    """按序叠加 Edit Set 并原子发布独立候选 BIN；绝不原位写回 source。"""
    if not isinstance(overwrite, bool):
        raise TypeError("overwrite 必须是 bool")

    initial_report = validate_project(project_dir)
    if initial_report.writer_capability != "Conditional":
        raise OverlayCompilationError("当前 BILE 版本没有 Existing-BILE 候选编译能力")
    if initial_report.operation_count == 0:
        raise OverlayCompilationError("Edit Set 为空；没有可编译的字段操作")

    root, project, assets, identities, edit_set = _load_project_files(project_dir)
    loaded_metadata_digest = _metadata_object_digest(project, assets, identities, edit_set)
    metadata_sha256 = _metadata_digest(root, project)
    source_reference = project["source"]["bin"]
    source_path = Path(source_reference["path"])
    image = RawBileImage.read(source_path)
    if image.sha256 != initial_report.source_sha256:
        raise OverlayCompilationError("编译期间源 BIN SHA-256 已变化")

    # Revalidate that the in-memory Project/Edit Set objects still match disk.
    current_report = validate_project(root)
    root_check, project_check, assets_check, identities_check, edit_set_check = _load_project_files(root)
    if (
        current_report.source_sha256 != initial_report.source_sha256
        or current_report.operation_count != initial_report.operation_count
        or _metadata_object_digest(project_check, assets_check, identities_check, edit_set_check)
        != loaded_metadata_digest
        or _metadata_digest(root_check, project_check) != metadata_sha256
    ):
        raise OverlayCompilationError("Project/Edit Set 在编译开始时发生变化；拒绝继续")

    output = _resolve_output_outside_project(root, output_path)
    buffer = BileMutationBuffer(image)
    planned_final: dict[int, int] = {}
    operation_results: list[OverlayOperationResult] = []

    for operation in edit_set["operations"]:
        operation_id = operation["operationId"]
        sequence = operation["sequence"]
        storage = operation["storage"]
        offset = storage["offset"]
        width = storage["width"]
        if (
            not isinstance(offset, int) or isinstance(offset, bool)
            or not isinstance(width, int) or isinstance(width, bool)
            or width <= 0
        ):
            raise OverlayCompilationError(f"{operation_id} storage offset/width 类型无效")
        try:
            before_raw = bytes.fromhex(operation["beforeRawHex"])
            after_raw = bytes.fromhex(operation["afterRawHex"])
            if len(before_raw) != width or len(after_raw) != width:
                raise OverlayCompilationError(f"{operation_id} 改变了字段宽度")
            current_raw = buffer.read(offset, width)
            if current_raw != before_raw:
                raise OverlayCompilationError(
                    f"{operation_id} beforeRaw 与当前 overlay 不一致；"
                    "事务已中止，未发布任何候选"
                )
            changed_for_operation = tuple(
                offset + index
                for index, (before, after) in enumerate(zip(current_raw, after_raw))
                if before != after
            )
            buffer.replace(offset, after_raw, operation_id)
            for index, value in enumerate(after_raw):
                planned_final[offset + index] = value

            expected_intermediate = _planned_changed_offsets(image.data, planned_final)
            # Every intermediate overlay must remain a valid, same-layout BILE image.
            verify_candidate_bytes(
                image,
                buffer.to_bytes(),
                expected_intermediate,
            )
        except Exception as exc:
            if isinstance(exc, OverlayCompilationError):
                raise
            raise OverlayCompilationError(
                f"Edit Set 操作 {operation_id}（{operation.get('field')}）失败；"
                "内存 overlay 已丢弃，未发布候选"
            ) from exc

        target = operation["target"]
        operation_results.append(OverlayOperationResult(
            operation_id=operation_id,
            sequence=sequence,
            target=f"{target['section']}[{target['index']}]",
            field=operation["field"],
            storage_section=storage["section"],
            storage_offset=offset,
            width=width,
            changed_byte_offsets=changed_for_operation,
        ))

    final_changed_offsets = _planned_changed_offsets(image.data, planned_final)
    if not final_changed_offsets:
        raise OverlayCompilationError(
            "Edit Set 的最终 overlay 与原始 BIN 完全相同；拒绝生成空候选"
        )
    candidate_bytes = buffer.to_bytes()
    verify_candidate_bytes(image, candidate_bytes, final_changed_offsets)

    # Project metadata is immutable during compilation; the source hash is checked
    # again by publish_verified_candidate immediately before publication.
    final_report = validate_project(root)
    root_check, project_check, assets_check, identities_check, edit_set_check = _load_project_files(root)
    if (
        final_report.source_sha256 != initial_report.source_sha256
        or final_report.operation_count != initial_report.operation_count
        or _metadata_object_digest(project_check, assets_check, identities_check, edit_set_check)
        != loaded_metadata_digest
        or _metadata_digest(root_check, project_check) != metadata_sha256
    ):
        raise OverlayCompilationError("候选准备期间 Project/Edit Set 或源身份发生变化")

    try:
        mutation = publish_verified_candidate(
            source_path,
            output,
            candidate_bytes,
            image.sha256,
            final_changed_offsets,
            overwrite=overwrite,
        )
    except BileMutationError as exc:
        raise OverlayCompilationError(f"Safe Mutation 原子发布失败：{exc}") from exc

    return OverlayCompilationReport(
        project_dir=str(root),
        output_path=mutation.output_path,
        input_sha256=mutation.input_sha256,
        output_sha256=mutation.output_sha256,
        size=mutation.size,
        version=mutation.version,
        operation_count=len(operation_results),
        changed_byte_offsets=mutation.changed_byte_offsets,
        operations=tuple(operation_results),
        mutation_report=mutation,
    )
