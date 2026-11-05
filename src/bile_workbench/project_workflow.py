"""Qt-free Project lifecycle, edit, compile and candidate-state orchestration."""
from __future__ import annotations

import hashlib
import json
import os
import struct
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .candidate_validation import (
    CandidateValidationError,
    CanonicalValidationReport,
    VALIDATION_SCHEMA,
    validate_project_candidate,
)
from .edit_session import EditSession
from .overlay_compiler import (
    OverlayCompilationError,
    OverlayCompilationReport,
    compile_project_candidate,
)
from .project_model import (
    ProjectModelError,
    ProjectValidationReport,
    _load_project_files,
    append_edit_operation,
    import_bile_project,
    validate_project,
)

ARTIFACT_MANIFEST_SCHEMA = "bile-workbench.candidate-artifact/v1"


class ProjectWorkflowError(ValueError):
    """Project workflow state or operation violates its contract."""


@dataclass(frozen=True)
class CandidateArtifactState:
    status: str
    path: str | None = None
    sha256: str | None = None
    manifest_path: str | None = None
    message: str | None = None
    validation: CanonicalValidationReport | None = None


@dataclass(frozen=True)
class ProjectWorkflowSnapshot:
    status: str
    project_dir: str
    project_id: str
    project_kind: str
    source_path: str
    source_sha256: str
    source_version: int
    operation_count: int
    writer_capability: str
    warnings: tuple[str, ...]
    candidate: CandidateArtifactState

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProjectCandidateBuildResult:
    compilation: OverlayCompilationReport
    validation: CanonicalValidationReport
    snapshot: ProjectWorkflowSnapshot
    manifest_written: bool
    warnings: tuple[str, ...]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_path(candidate: Path) -> Path:
    return candidate.with_name(candidate.name + ".bile-workbench.json")


def _metadata_digest(root: Path, project: dict[str, Any]) -> str:
    digest = hashlib.sha256()
    for relative in (
        "project.json",
        project["paths"]["assetManifest"],
        project["paths"]["recordIdentities"],
        project["paths"]["editSet"],
    ):
        data = (root / relative).read_bytes()
        encoded = relative.encode("utf-8")
        digest.update(len(encoded).to_bytes(4, "little"))
        digest.update(encoded)
        digest.update(len(data).to_bytes(8, "little"))
        digest.update(data)
    return digest.hexdigest()


def _u32(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise ProjectWorkflowError(f"{label} 不能是 bool")
    try:
        result = int(value, 0) if isinstance(value, str) else int(value)
    except (TypeError, ValueError) as exc:
        raise ProjectWorkflowError(f"{label} 不是有效 u32") from exc
    if not 0 <= result <= 0xFFFFFFFF:
        raise ProjectWorkflowError(f"{label} 超出 u32 范围")
    return result


def _same_packed(field: str, left: Any, right: Any) -> bool:
    try:
        if field.startswith("transform."):
            return struct.pack("<f", float(left)) == struct.pack("<f", float(right))
        if field == "anchor":
            return struct.pack("<ff", *map(float, left)) == struct.pack("<ff", *map(float, right))
        if field in {"argb", "initial_phase"}:
            return struct.pack("<I", _u32(left, field)) == struct.pack("<I", _u32(right, field))
    except (OverflowError, TypeError, ValueError, struct.error) as exc:
        raise ProjectWorkflowError(f"{field} 的 EditSession before/after 值无效") from exc
    raise ProjectWorkflowError(f"EditSession 不支持映射字段：{field}")


class ProjectWorkflowService:
    """可独立使用的 Project 生命周期、字段编辑、候选编译与状态服务。"""

    def __init__(self, project_dir: str | Path, candidate_path: str | Path | None = None) -> None:
        self.project_dir = Path(project_dir).expanduser()
        self._candidate_path = Path(candidate_path).expanduser() if candidate_path is not None else None

    @classmethod
    def import_source(
        cls,
        source_bin: str | Path,
        project_dir: str | Path,
        *,
        xml_path: str | Path | None = None,
        texture_path: str | Path | None = None,
        origin_kind: str = "ImportedOriginal",
        candidate_path: str | Path | None = None,
    ) -> "ProjectWorkflowService":
        import_bile_project(
            source_bin, project_dir, xml_path=xml_path,
            texture_path=texture_path, origin_kind=origin_kind,
        )
        return cls(project_dir, candidate_path)

    def validate(self) -> ProjectValidationReport:
        try:
            return validate_project(self.project_dir)
        except (OSError, ProjectModelError, ValueError) as exc:
            raise ProjectWorkflowError(f"Project 校验失败：{exc}") from exc

    def append_edit(self, *, section: str, index: int, field: str, after: Any) -> dict[str, Any]:
        try:
            return append_edit_operation(
                self.project_dir, section=section, index=index, field=field, after=after
            )
        except (OSError, ProjectModelError, ValueError) as exc:
            raise ProjectWorkflowError(f"追加 Edit Set 操作失败：{exc}") from exc

    def apply_edit_session(self, session: EditSession) -> tuple[dict[str, Any], ...]:
        """将旧 EditSession 的最终字段值一次性映射到空 Project，不导入撤销历史。"""
        if not isinstance(session, EditSession):
            raise TypeError("session 必须是 EditSession")
        report = self.validate()
        if report.operation_count:
            raise ProjectWorkflowError("EditSession 只能映射到空 Edit Set；拒绝覆盖已有 Project 编辑")
        if not session.dirty:
            raise ProjectWorkflowError("EditSession 为空；没有可映射的暂存编辑")

        try:
            _root, project, _assets, _identities, _edit_set = _load_project_files(self.project_dir)
            project_source = Path(project["source"]["bin"]["path"]).resolve(strict=True)
            session_source = session.source_path.resolve(strict=True)
        except (OSError, ProjectModelError, ValueError) as exc:
            raise ProjectWorkflowError(f"无法绑定 EditSession 与 Project source：{exc}") from exc
        if os.path.normcase(str(project_source)) != os.path.normcase(str(session_source)):
            raise ProjectWorkflowError("EditSession 与 Project 必须绑定同一个 source BIN 路径")
        if session.source_sha256 != report.source_sha256:
            raise ProjectWorkflowError("EditSession source SHA-256 与 Project 不一致")

        payload = session.patch_payload()
        if payload.get("source_sha256") != report.source_sha256:
            raise ProjectWorkflowError("EditSession patch payload 与 Project source SHA-256 不一致")

        operations: list[dict[str, Any]] = []
        order = ("xx", "xy", "yx", "yy", "x", "y")
        try:
            for change in payload.get("keyframes", []):
                index = change["index"]
                expected = change["expected"]
                expected_transform = expected.get("transform", {})
                transform = change.get("transform", {})
                if not isinstance(transform, dict):
                    raise ProjectWorkflowError(f"BELE[{index}] transform 必须是对象")
                for field in order:
                    if field not in transform:
                        continue
                    if field not in expected_transform:
                        raise ProjectWorkflowError(f"BELE[{index}] 缺少 transform.{field} expected-old")
                    if not _same_packed(f"transform.{field}", expected_transform[field], transform[field]):
                        operations.append(self.append_edit(
                            section="BELE", index=index, field=f"transform.{field}", after=transform[field]
                        ))
                for field in ("argb", "initial_phase"):
                    if field in change:
                        if field not in expected:
                            raise ProjectWorkflowError(f"BELE[{index}] 缺少 {field} expected-old")
                        if not _same_packed(field, expected[field], change[field]):
                            operations.append(self.append_edit(
                                section="BELE", index=index, field=field, after=change[field]
                            ))
            for change in payload.get("elements", []):
                index = change["index"]
                expected = change["expected"]
                if "anchor" in change:
                    if "anchor" not in expected:
                        raise ProjectWorkflowError(f"BMTI[{index}] 缺少 anchor expected-old")
                    if not _same_packed("anchor", expected["anchor"], change["anchor"]):
                        operations.append(self.append_edit(
                            section="BMTI", index=index, field="anchor", after=change["anchor"]
                        ))
        except (KeyError, TypeError, ProjectWorkflowError) as exc:
            raise ProjectWorkflowError(f"EditSession 映射失败：{exc}") from exc

        if not operations:
            raise ProjectWorkflowError("暂存会话没有产生实际字段字节变化；拒绝建立空 Edit Set")
        if self.validate().operation_count != len(operations):
            raise ProjectWorkflowError("EditSession 映射后 Edit Set 操作数量不一致")
        return tuple(operations)

    def _context(self) -> tuple[ProjectValidationReport, Path, dict[str, Any], str]:
        first_report = self.validate()
        try:
            root, project, _assets, _identities, _edit_set = _load_project_files(
                self.project_dir
            )
            first_digest = _metadata_digest(root, project)
            second_report = self.validate()
            second_root, second_project, _assets2, _identities2, _edit_set2 = (
                _load_project_files(self.project_dir)
            )
            second_digest = _metadata_digest(second_root, second_project)
            if (
                first_report != second_report
                or first_digest != second_digest
                or root != second_root
            ):
                raise ProjectWorkflowError(
                    "Project/Edit Set 在读取 workflow snapshot 期间发生变化"
                )
            edit_set_sha = _sha256_file(
                second_root / second_project["paths"]["editSet"]
            )
        except ProjectWorkflowError:
            raise
        except (OSError, KeyError, ProjectModelError, ValueError) as exc:
            raise ProjectWorkflowError(
                f"读取 Project workflow metadata 失败：{exc}"
            ) from exc
        return second_report, second_root, second_project, edit_set_sha

    def _read_manifest(self, path: Path) -> dict[str, Any] | None:
        if path.is_symlink():
            raise ProjectWorkflowError("候选追踪清单不允许是符号链接")
        if not path.exists():
            return None
        if not path.is_file():
            raise ProjectWorkflowError("候选追踪清单不是普通文件")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ProjectWorkflowError(f"候选追踪清单无法读取：{exc}") from exc
        required = {
            "schema", "projectId", "sourceSha256", "editSetSha256",
            "candidateSha256", "candidateSizeBytes", "validationSchema",
            "validationStatus", "validationScope", "validatedAtUtc",
        }
        if not isinstance(payload, dict) or set(payload) != required:
            raise ProjectWorkflowError("候选追踪清单字段不完整或包含未知字段")
        if (
            payload.get("schema") != ARTIFACT_MANIFEST_SCHEMA
            or payload.get("validationSchema") != VALIDATION_SCHEMA
            or payload.get("validationStatus") != "OfflineValid"
            or payload.get("validationScope") != "OfflineStructuralAndEditSet"
            or not isinstance(payload.get("candidateSizeBytes"), int)
            or isinstance(payload.get("candidateSizeBytes"), bool)
            or payload["candidateSizeBytes"] <= 0
            or not isinstance(payload.get("validatedAtUtc"), str)
            or not isinstance(payload.get("projectId"), str)
            or not payload["projectId"]
        ):
            raise ProjectWorkflowError("候选追踪清单 schema 或状态无效")
        for key in ("sourceSha256", "editSetSha256", "candidateSha256"):
            value = payload.get(key)
            if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                raise ProjectWorkflowError(f"候选追踪清单 {key} 格式无效")
        return payload

    def _write_manifest(
        self, candidate: Path, *, project_id: str, source_sha: str,
        edit_set_sha: str, candidate_sha: str, candidate_size: int,
    ) -> Path:
        path = _manifest_path(candidate)
        if path.is_symlink():
            raise ProjectWorkflowError("拒绝覆盖符号链接形式的候选追踪清单")
        payload = {
            "schema": ARTIFACT_MANIFEST_SCHEMA,
            "projectId": project_id,
            "sourceSha256": source_sha,
            "editSetSha256": edit_set_sha,
            "candidateSha256": candidate_sha,
            "candidateSizeBytes": candidate_size,
            "validationSchema": VALIDATION_SCHEMA,
            "validationStatus": "OfflineValid",
            "validationScope": "OfflineStructuralAndEditSet",
            "validatedAtUtc": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        }
        data = (json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
        fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
        temporary = Path(name)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        return path

    def _candidate_state(
        self, report: ProjectValidationReport, root: Path, project: dict[str, Any],
        edit_set_sha: str, path_value: str | Path | None,
    ) -> CandidateArtifactState:
        if path_value is None:
            return CandidateArtifactState("NotConfigured")
        candidate_input = Path(path_value).expanduser()
        if not candidate_input.is_absolute():
            candidate_input = candidate_input.absolute()
        if candidate_input.is_symlink():
            return CandidateArtifactState(
                "Invalid", str(candidate_input),
                manifest_path=str(_manifest_path(candidate_input)),
                message="候选 BIN 不允许是符号链接",
            )
        try:
            if not candidate_input.parent.is_dir():
                return CandidateArtifactState(
                    "Missing", str(candidate_input),
                    manifest_path=str(_manifest_path(candidate_input)),
                    message="候选 BIN 所在目录不存在",
                )
            candidate = candidate_input.parent.resolve(strict=True) / candidate_input.name
            manifest_path = _manifest_path(candidate)
            if candidate.is_symlink():
                return CandidateArtifactState(
                    "Invalid", str(candidate),
                    manifest_path=str(manifest_path),
                    message="候选 BIN 不允许是符号链接",
                )
            if not candidate.exists():
                return CandidateArtifactState(
                    "Missing", str(candidate),
                    manifest_path=str(manifest_path),
                    message="候选 BIN 尚未生成",
                )
            if not candidate.is_file():
                return CandidateArtifactState(
                    "Invalid", str(candidate),
                    manifest_path=str(manifest_path),
                    message="候选路径不是普通文件",
                )
            manifest = self._read_manifest(manifest_path)
            candidate_sha = _sha256_file(candidate)
            candidate_size = candidate.stat().st_size
            if manifest is not None:
                if (
                    manifest["candidateSha256"] != candidate_sha
                    or manifest["candidateSizeBytes"] != candidate_size
                ):
                    return CandidateArtifactState(
                        "Invalid", str(candidate), candidate_sha, str(manifest_path),
                        "候选 BIN 内容与追踪清单不一致；可能已被替换或修改。",
                    )
                if (
                    manifest["projectId"] != project["projectId"]
                    or manifest["sourceSha256"] != report.source_sha256
                    or manifest["editSetSha256"] != edit_set_sha
                ):
                    return CandidateArtifactState(
                        "Stale", str(candidate), candidate_sha, str(manifest_path),
                        "候选由不同的 Project/source/Edit Set 状态生成；需要重新编译。",
                    )
            validation = validate_project_candidate(root, candidate)
            if (
                _sha256_file(candidate) != candidate_sha
                or candidate.stat().st_size != candidate_size
            ):
                return CandidateArtifactState(
                    "Invalid", str(candidate), manifest_path=str(manifest_path),
                    message="候选 BIN 在工作流状态检查期间发生变化。",
                )
            status = "Current" if manifest is not None else "CurrentUntracked"
            message = (
                "候选与当前 Project/Edit Set 完全一致，规范离线验证通过。"
                if manifest else "候选与当前 Project/Edit Set 完全一致，但没有追踪清单。"
            )
            return CandidateArtifactState(
                status, str(candidate), candidate_sha, str(manifest_path), message, validation
            )
        except (OSError, ProjectWorkflowError, CandidateValidationError, ProjectModelError, ValueError) as exc:
            return CandidateArtifactState(
                "Invalid", str(candidate_input),
                manifest_path=str(_manifest_path(candidate_input)),
                message=f"候选校验失败：{exc}",
            )

    def inspect(self, candidate_path: str | Path | None = None) -> ProjectWorkflowSnapshot:
        if candidate_path is not None:
            self._candidate_path = Path(candidate_path).expanduser()
        report, root, project, edit_set_sha = self._context()
        candidate = self._candidate_state(report, root, project, edit_set_sha, self._candidate_path)
        return ProjectWorkflowSnapshot(
            "Ready", str(root), project["projectId"], report.project_kind,
            project["source"]["bin"]["path"], report.source_sha256,
            report.source_version, report.operation_count, report.writer_capability,
            report.warnings, candidate,
        )

    def validate_candidate(self, candidate_path: str | Path | None = None) -> CanonicalValidationReport:
        if candidate_path is not None:
            self._candidate_path = Path(candidate_path).expanduser()
        if self._candidate_path is None:
            raise ProjectWorkflowError("尚未指定候选 BIN 路径")
        report, root, project, edit_set_sha = self._context()
        candidate = Path(self._candidate_path).expanduser().absolute()
        try:
            validation = validate_project_candidate(root, candidate)
            self._write_manifest(
                candidate.resolve(strict=True),
                project_id=project["projectId"], source_sha=report.source_sha256,
                edit_set_sha=edit_set_sha, candidate_sha=validation.candidate_sha256,
                candidate_size=validation.candidate_size_bytes,
            )
        except (OSError, CandidateValidationError, ProjectWorkflowError, ProjectModelError, ValueError) as exc:
            raise ProjectWorkflowError(f"候选验证/状态登记失败：{exc}") from exc
        self._candidate_path = candidate
        return validation

    def compile_candidate(
        self, output_path: str | Path, *, overwrite: bool = False,
        track_artifact: bool = True,
    ) -> ProjectCandidateBuildResult:
        if not isinstance(overwrite, bool) or not isinstance(track_artifact, bool):
            raise TypeError("overwrite 和 track_artifact 必须是 bool")
        report, root, project, edit_set_sha = self._context()
        try:
            compilation = compile_project_candidate(root, output_path, overwrite=overwrite)
            candidate = Path(compilation.output_path).resolve(strict=True)
            validation = validate_project_candidate(root, candidate)
        except (OSError, CandidateValidationError, OverlayCompilationError, ProjectModelError, ValueError) as exc:
            raise ProjectWorkflowError(f"候选编译失败：{exc}") from exc
        if validation.candidate_sha256 != compilation.output_sha256:
            raise ProjectWorkflowError("发布后候选 SHA-256 与编译报告不一致")

        warnings: list[str] = []
        manifest_written = False
        self._candidate_path = candidate
        if track_artifact:
            try:
                self._write_manifest(
                    candidate, project_id=project["projectId"],
                    source_sha=report.source_sha256, edit_set_sha=edit_set_sha,
                    candidate_sha=validation.candidate_sha256,
                    candidate_size=validation.candidate_size_bytes,
                )
                manifest_written = True
            except (OSError, ProjectWorkflowError) as exc:
                warnings.append(f"ArtifactManifestWriteFailed: 候选已通过离线验证，但追踪清单未写入：{exc}")
        snapshot = self.inspect()
        return ProjectCandidateBuildResult(
            compilation, validation, snapshot, manifest_written, tuple(warnings)
        )
