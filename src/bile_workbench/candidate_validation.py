"""Canonical offline validation for an Existing-BILE candidate.

Validation independently replays the Project Edit Set against the bound source BIN.
A candidate is accepted only when its complete byte image exactly equals that replay.
This is not a substitute for testing the candidate in the original game.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from .project_model import (
    ProjectModelError,
    _load_project_files,
    validate_project,
)
from .raw_image import RawBileImage
from .safe_mutation import (
    BileMutationBuffer,
    BileMutationError,
    changed_byte_offsets,
    verify_candidate_bytes,
)


VALIDATION_SCHEMA = "bile-workbench.candidate-validation/v1"


class CandidateValidationError(ValueError):
    """Candidate does not match its validated Project/Edit Set contract."""


@dataclass(frozen=True)
class CanonicalValidationReport:
    schema: str
    status: str
    scope: str
    project_id: str
    project_dir: str
    source_path: str
    source_sha256: str
    source_size_bytes: int
    source_version: int
    candidate_path: str
    candidate_sha256: str
    expected_candidate_sha256: str
    candidate_size_bytes: int
    candidate_version: int
    operation_count: int
    operation_ids: tuple[str, ...]
    changed_byte_count: int
    changed_byte_offsets: tuple[int, ...]
    changed_byte_offsets_sha256: str
    candidate_exact_match: bool
    checks: dict[str, str]
    sections: tuple[dict[str, Any], ...]
    warnings: tuple[str, ...]
    original_game_validation: str = "NotPerformed"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["operation_ids"] = list(self.operation_ids)
        payload["changed_byte_offsets"] = list(self.changed_byte_offsets)
        payload["sections"] = [dict(section) for section in self.sections]
        payload["warnings"] = list(self.warnings)
        return payload


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _metadata_object_digest(*payloads: dict[str, Any]) -> str:
    encoded = json.dumps(
        payloads, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _project_metadata_digest(root: Path, project: dict[str, Any]) -> str:
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


def _resolve_candidate_path(
    root: Path,
    source_path: Path,
    candidate_path: str | Path,
    *,
    require_exists: bool,
) -> Path:
    candidate_input = Path(candidate_path).expanduser()
    if not candidate_input.is_absolute():
        candidate_input = candidate_input.absolute()
    if candidate_input.is_symlink():
        raise CandidateValidationError("候选 BIN 不允许是符号链接")
    if require_exists:
        if not candidate_input.is_file():
            raise FileNotFoundError(f"候选 BIN 不存在或不是普通文件：{candidate_input}")
        resolved = candidate_input.resolve(strict=True)
    else:
        if candidate_input.exists() and not candidate_input.is_file():
            raise CandidateValidationError("候选输出路径已存在但不是普通文件")
        if not candidate_input.parent.is_dir():
            raise FileNotFoundError(f"候选输出目录不存在：{candidate_input.parent}")
        resolved = candidate_input.parent.resolve(strict=True) / candidate_input.name

    try:
        resolved.relative_to(root.resolve(strict=True))
    except ValueError:
        pass
    else:
        raise CandidateValidationError("候选 BIN 必须位于 Project 目录之外")

    source_resolved = source_path.resolve(strict=True)
    if os.path.normcase(str(resolved)) == os.path.normcase(str(source_resolved)):
        raise CandidateValidationError("候选 BIN 不得与原始 source BIN 使用同一路径")
    if resolved.exists():
        try:
            if os.path.samefile(source_resolved, resolved):
                raise CandidateValidationError("候选 BIN 与原始 source BIN 是同一个底层文件")
        except OSError:
            pass
    return resolved


def _replay_edit_set(
    source_image: RawBileImage,
    operations: list[dict[str, Any]],
) -> tuple[bytes, tuple[int, ...], tuple[str, ...]]:
    if not operations:
        raise CandidateValidationError("Edit Set 为空；不存在可验证的候选修改")
    if source_image.document.header.version not in (3, 4):
        raise CandidateValidationError("BILE v2 及其他只读版本不允许候选验证/编译")

    buffer = BileMutationBuffer(source_image)
    operation_ids: list[str] = []
    for operation in operations:
        operation_id = operation["operationId"]
        storage = operation["storage"]
        offset = storage["offset"]
        width = storage["width"]
        try:
            before_raw = bytes.fromhex(operation["beforeRawHex"])
            after_raw = bytes.fromhex(operation["afterRawHex"])
            if len(before_raw) != width or len(after_raw) != width:
                raise CandidateValidationError(f"{operation_id} 字段宽度发生变化")
            current = buffer.read(offset, width)
            if current != before_raw:
                raise CandidateValidationError(
                    f"{operation_id} beforeRaw 与当前重放状态不一致"
                )
            buffer.replace(offset, after_raw, operation_id)
        except (KeyError, TypeError, ValueError, BileMutationError) as exc:
            if isinstance(exc, CandidateValidationError):
                raise
            raise CandidateValidationError(
                f"{operation_id} 无法重放；拒绝接受候选"
            ) from exc
        operation_ids.append(operation_id)

    expected_bytes = buffer.to_bytes()
    expected_offsets = changed_byte_offsets(source_image.data, expected_bytes)
    if not expected_offsets:
        raise CandidateValidationError("Edit Set 最终未改变任何源字节；拒绝空候选")
    return expected_bytes, expected_offsets, tuple(operation_ids)


def _validate_candidate_bytes(
    project_dir: str | Path,
    candidate_bytes: bytes,
    *,
    candidate_path: str | Path | None,
) -> CanonicalValidationReport:
    if not isinstance(candidate_bytes, bytes):
        raise TypeError("candidate_bytes 必须是 bytes")

    try:
        root, project, assets, identities, edit_set = _load_project_files(project_dir)
        loaded_objects_digest = _metadata_object_digest(
            project, assets, identities, edit_set
        )
        metadata_digest = _project_metadata_digest(root, project)
        project_report = validate_project(root)
        (
            root_check, project_check, assets_check, identities_check, edit_set_check
        ) = _load_project_files(root)
        if (
            _metadata_object_digest(
                project_check, assets_check, identities_check, edit_set_check
            ) != loaded_objects_digest
            or _project_metadata_digest(root_check, project_check) != metadata_digest
        ):
            raise CandidateValidationError(
                "Project/Edit Set 在读取期间发生变化；拒绝使用不一致的内存快照"
            )
    except ProjectModelError as exc:
        raise CandidateValidationError(f"Project 校验失败：{exc}") from exc

    source_value = project["source"]["bin"]["path"]
    source_input = Path(source_value)
    if source_input.is_symlink() or not source_input.is_file():
        raise CandidateValidationError("原始 source BIN 必须是普通文件且不能是符号链接")
    source_path = source_input.resolve(strict=True)

    resolved_candidate: Path | None = None
    if candidate_path is not None:
        resolved_candidate = _resolve_candidate_path(
            root, source_path, candidate_path, require_exists=False
        )

    try:
        source_image = RawBileImage.read(source_path)
    except (OSError, ValueError) as exc:
        raise CandidateValidationError(f"无法读取原始 source BIN：{exc}") from exc
    if source_image.sha256 != project_report.source_sha256:
        raise CandidateValidationError("原始 source BIN 在 Project 校验后发生变化")

    expected_bytes, expected_offsets, operation_ids = _replay_edit_set(
        source_image, edit_set["operations"]
    )
    try:
        candidate_image, actual_offsets = verify_candidate_bytes(
            source_image, candidate_bytes, expected_offsets
        )
    except (BileMutationError, ValueError) as exc:
        raise CandidateValidationError(f"候选 BIN 结构/字段门禁失败：{exc}") from exc

    if candidate_bytes != expected_bytes:
        mismatches = tuple(
            index
            for index, (expected, actual) in enumerate(zip(expected_bytes, candidate_bytes))
            if expected != actual
        )
        raise CandidateValidationError(
            "候选 BIN 与 Edit Set 独立重放结果不完全一致；"
            f"首批差异偏移={mismatches[:16]}"
        )

    # Close the read/validate window: neither the source nor Project metadata may drift.
    if source_input.is_symlink() or not source_input.is_file():
        raise CandidateValidationError("验证期间原始 source BIN 路径发生变化")
    if _sha256_file(source_path) != source_image.sha256:
        raise CandidateValidationError("验证期间原始 source BIN 内容发生变化")
    try:
        final_report = validate_project(root)
        (
            root_check, project_check, assets_check, identities_check, edit_set_check
        ) = _load_project_files(root)
        final_metadata_digest = _project_metadata_digest(root_check, project_check)
        final_objects_digest = _metadata_object_digest(
            project_check, assets_check, identities_check, edit_set_check
        )
    except ProjectModelError as exc:
        raise CandidateValidationError(f"验证期间 Project 失效：{exc}") from exc
    if (
        final_report.source_sha256 != project_report.source_sha256
        or final_report.operation_count != project_report.operation_count
        or final_metadata_digest != metadata_digest
        or final_objects_digest != loaded_objects_digest
    ):
        raise CandidateValidationError("验证期间 Project/Edit Set metadata 发生变化")

    offsets_payload = b"".join(
        offset.to_bytes(8, "little", signed=False) for offset in actual_offsets
    )
    checks = {
        "projectSchemaAndEditSet": "Passed",
        "sourceSha256AndRecordIdentity": "Passed",
        "candidateFullParse": "Passed",
        "sectionLayoutPreserved": "Passed",
        "editSetSequentialReplay": "Passed",
        "exactCandidateByteMatch": "Passed",
        "changedByteSetExact": "Passed",
        "sourceStableDuringValidation": "Passed",
        "projectMetadataStableDuringValidation": "Passed",
        "candidateFileStableDuringValidation": "NotApplicable",
    }
    sections = tuple({
        "index": section.index,
        "tag": section.tag,
        "offset": section.offset,
        "totalSize": section.total_size,
        "count": section.count,
        "headerSize": section.header_size,
    } for section in candidate_image.sections)

    return CanonicalValidationReport(
        schema=VALIDATION_SCHEMA,
        status="OfflineValid",
        scope="OfflineStructuralAndEditSet",
        project_id=project["projectId"],
        project_dir=str(root),
        source_path=str(source_path),
        source_sha256=source_image.sha256,
        source_size_bytes=len(source_image.data),
        source_version=source_image.document.header.version,
        candidate_path=str(resolved_candidate) if resolved_candidate is not None else "<memory>",
        candidate_sha256=candidate_image.sha256,
        expected_candidate_sha256=_sha256(expected_bytes),
        candidate_size_bytes=len(candidate_bytes),
        candidate_version=candidate_image.document.header.version,
        operation_count=len(operation_ids),
        operation_ids=operation_ids,
        changed_byte_count=len(actual_offsets),
        changed_byte_offsets=actual_offsets,
        changed_byte_offsets_sha256=_sha256(offsets_payload),
        candidate_exact_match=True,
        checks=checks,
        sections=sections,
        warnings=final_report.warnings,
    )


def validate_candidate_bytes(
    project_dir: str | Path,
    candidate_bytes: bytes,
    *,
    candidate_path: str | Path | None = None,
) -> CanonicalValidationReport:
    """独立验证内存候选；供 Overlay Compiler 在发布前调用。"""
    return _validate_candidate_bytes(
        project_dir, candidate_bytes, candidate_path=candidate_path
    )


def validate_project_candidate(
    project_dir: str | Path,
    candidate_path: str | Path,
) -> CanonicalValidationReport:
    """验证已发布候选文件，并检查候选在验证期间没有发生变化。"""
    try:
        root, project, _assets, _identities, _edit_set = _load_project_files(project_dir)
        source_path = Path(project["source"]["bin"]["path"])
        candidate = _resolve_candidate_path(
            root, source_path, candidate_path, require_exists=True
        )
        candidate_bytes = candidate.read_bytes()
    except ProjectModelError as exc:
        raise CandidateValidationError(f"Project 校验失败：{exc}") from exc

    report = _validate_candidate_bytes(
        root, candidate_bytes, candidate_path=candidate
    )
    if candidate.is_symlink() or not candidate.is_file():
        raise CandidateValidationError("验证期间候选 BIN 路径发生变化")
    if candidate.read_bytes() != candidate_bytes:
        raise CandidateValidationError("验证期间候选 BIN 内容发生变化")
    checks = dict(report.checks)
    checks["candidateFileStableDuringValidation"] = "Passed"
    return replace(report, checks=checks)
