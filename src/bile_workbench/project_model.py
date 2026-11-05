"""BILE reference-only Project Model and ordered field Edit Set.

The project stores semantic metadata and external source references only. It never
copies the original BIN/XML/texture payloads and never compiles an output BIN.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import struct
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .bile_format import RECORD_WIDTHS, V2_RECORD_WIDTHS
from .raw_image import RawBileImage


PROJECT_SCHEMA = "bile-workbench.project/v1"
ASSET_MANIFEST_SCHEMA = "bile-workbench.asset-references/v1"
RECORD_IDENTITIES_SCHEMA = "bile-workbench.record-identities/v1"
EDIT_SET_SCHEMA = "bile-workbench.edit-set/v1"

_ALLOWED_ORIGIN_KINDS = {"ImportedOriginal", "SyntheticFixture"}
_TRANSFORM_OFFSETS = {
    "transform.xx": 0,
    "transform.xy": 4,
    "transform.yx": 8,
    "transform.yy": 12,
    "transform.x": 16,
    "transform.y": 20,
}


class ProjectModelError(ValueError):
    """Project metadata, source identity, or edit-set contract is invalid."""


@dataclass(frozen=True)
class ProjectValidationReport:
    status: str
    project_kind: str
    source_sha256: str
    source_version: int
    operation_count: int
    writer_capability: str
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_json_bytes(payload))


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(_json_bytes(payload))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProjectModelError(f"无法读取 {label}：{exc}") from exc
    if not isinstance(payload, dict):
        raise ProjectModelError(f"{label} 根节点必须是 JSON object")
    return payload


def _relative_project_file(root: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ProjectModelError(f"{label} 必须是非空相对路径")
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ProjectModelError(f"{label} 不允许绝对路径或目录穿越")
    target = root / relative
    if target.is_symlink():
        raise ProjectModelError(f"{label} 不允许符号链接")
    parent = target.parent
    while parent != root and root in parent.parents:
        if parent.is_symlink():
            raise ProjectModelError(f"{label} 的父目录不允许符号链接")
        parent = parent.parent
    return target


def _file_reference(path: str | Path, role: str) -> dict[str, Any]:
    source = Path(path).expanduser()
    if source.is_symlink() or not source.is_file():
        raise ProjectModelError(f"{role} 必须是普通文件且不能是符号链接：{source}")
    resolved = source.resolve(strict=True)
    return {
        "role": role,
        "path": str(resolved),
        "sha256": _sha256_file(resolved),
        "sizeBytes": resolved.stat().st_size,
        "referenceOnly": True,
    }


def _record_identities(image: RawBileImage) -> dict[str, Any]:
    widths = V2_RECORD_WIDTHS if image.document.header.version == 2 else RECORD_WIDTHS
    section_rows: list[dict[str, Any]] = []
    for raw_section in image.sections:
        section = image.document.sections[raw_section.tag]
        width = widths.get(raw_section.tag)
        records: list[dict[str, Any]] = []
        if width is not None:
            for index in range(raw_section.count):
                start = section.payload_offset + index * width
                raw_record = image.data[start:start + width]
                record_sha = _sha256(raw_record)
                record: dict[str, Any] = {
                    "recordId": f"{raw_section.tag}:{index}:{record_sha[:16]}",
                    "section": raw_section.tag,
                    "index": index,
                    "offset": start,
                    "sizeBytes": width,
                    "sha256": record_sha,
                }
                if raw_section.tag == "BMTI":
                    element = image.document.elements[index]
                    record["label"] = element.name
                    record["elementKind"] = "sprite" if element.has_texture else "animation"
                elif raw_section.tag == "BELE":
                    record["label"] = f"keyframe-{index}"
                records.append(record)
        section_rows.append({
            "tag": raw_section.tag,
            "index": raw_section.index,
            "offset": raw_section.offset,
            "totalSize": raw_section.total_size,
            "headerSize": raw_section.header_size,
            "recordCount": raw_section.count,
            "recordWidth": width,
            "headerSha256": _sha256(raw_section.header_bytes),
            "payloadSha256": _sha256(raw_section.payload_bytes),
            "records": records,
        })

    string_reference_counts: dict[int, int] = {}
    for element in image.document.elements:
        string_reference_counts[element.name_offset] = (
            string_reference_counts.get(element.name_offset, 0) + 1
        )
    strings = []
    for offset, value in sorted(image.document.strings.items()):
        raw = value.encode("utf-8")
        digest = _sha256(raw)
        strings.append({
            "stringId": f"BRTS:{offset}:{digest[:16]}",
            "offset": offset,
            "text": value,
            "byteLength": len(raw),
            "sha256": digest,
            "referenceCount": string_reference_counts.get(offset, 0),
        })

    return {
        "schema": RECORD_IDENTITIES_SCHEMA,
        "sourceSha256": image.sha256,
        "sourceSizeBytes": len(image.data),
        "sourceVersion": image.document.header.version,
        "sectionOrder": [section.tag for section in image.sections],
        "sections": section_rows,
        "strings": strings,
        "rawPayloadIncluded": False,
    }


def _record_map(identities: dict[str, Any]) -> dict[tuple[str, int], dict[str, Any]]:
    output: dict[tuple[str, int], dict[str, Any]] = {}
    for section in identities["sections"]:
        for record in section["records"]:
            output[(record["section"], record["index"])] = record
    return output


def _finite_f32(value: Any, label: str) -> tuple[float, bytes]:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ProjectModelError(f"{label} 必须是有限数字")
    try:
        number = float(value)
        raw = struct.pack("<f", number)
    except (OverflowError, ValueError, struct.error) as exc:
        raise ProjectModelError(f"{label} 超出有限 float32 范围") from exc
    normalized = struct.unpack("<f", raw)[0]
    if not math.isfinite(number) or not math.isfinite(normalized):
        raise ProjectModelError(f"{label} 必须是有限 float32")
    return normalized, raw


def _u32(value: Any, label: str, *, allow_argb_text: bool = False) -> tuple[int, bytes]:
    if allow_argb_text and isinstance(value, str) and value.lower().startswith("0x"):
        digits = value[2:]
        if not 1 <= len(digits) <= 8 or any(c not in "0123456789abcdefABCDEF" for c in digits):
            raise ProjectModelError(f"{label} 必须是 0xAARRGGBB 格式的 u32")
        number = int(digits, 16)
    elif isinstance(value, int) and not isinstance(value, bool):
        number = value
    else:
        raise ProjectModelError(f"{label} 必须是 u32 整数")
    if not 0 <= number <= 0xFFFFFFFF:
        raise ProjectModelError(f"{label} 超出 u32 范围")
    return number, struct.pack("<I", number)


def _field_descriptor(
    image: RawBileImage,
    section: str,
    index: int,
    field: str,
    identities: dict[str, Any],
) -> dict[str, Any]:
    if image.document.header.version not in (3, 4):
        raise ProjectModelError(f"BILE v{image.document.header.version} 严格只读")
    if not isinstance(index, int) or isinstance(index, bool) or index < 0:
        raise ProjectModelError("目标记录索引必须是非负整数")

    record = _record_map(identities).get((section, index))
    if record is None:
        raise ProjectModelError(f"目标记录不存在：{section}[{index}]")
    if section == "BELE":
        if index >= len(image.document.keyframes):
            raise ProjectModelError(f"BELE 索引越界：{index}")
        if field in _TRANSFORM_OFFSETS:
            local = _TRANSFORM_OFFSETS[field]
            absolute = record["offset"] + local
            width = 4
        elif field == "argb":
            local, width = 24, 4
            absolute = record["offset"] + local
        elif field == "initial_phase":
            local, width = 28, 4
            absolute = record["offset"] + local
        else:
            raise ProjectModelError(f"BELE 字段不在 Edit Set 白名单：{field}")
        raw = image.data[absolute:absolute + width]
        return {
            "targetRecord": record,
            "storageSection": "BELE",
            "storageOffset": absolute,
            "fieldOffset": local,
            "width": width,
            "raw": raw,
        }

    if section != "BMTI" or index >= len(image.document.elements):
        raise ProjectModelError(f"当前仅支持 BELE/BMTI 已有记录，目标为 {section}[{index}]")
    element = image.document.elements[index]
    if field == "anchor":
        local, width = 8, 8
        absolute = record["offset"] + local
    elif field == "name":
        users = [
            item.index for item in image.document.elements
            if item.name_offset == element.name_offset
        ]
        if len(users) != 1:
            raise ProjectModelError(
                f"BMTI[{index}] 的 BRTS 偏移被多个元素共享：{users}"
            )
        local = element.name_offset
        width = len(element.name.encode("utf-8"))
        absolute = image.document.sections["BRTS"].payload_offset + local
    else:
        raise ProjectModelError(f"BMTI 字段不在 Edit Set 白名单：{field}")
    raw = image.data[absolute:absolute + width]
    return {
        "targetRecord": record,
        "storageSection": "BMTI" if field == "anchor" else "BRTS",
        "storageOffset": absolute,
        "fieldOffset": local,
        "width": width,
        "raw": raw,
    }


def _pack_field(field: str, value: Any, width: int) -> tuple[Any, bytes]:
    if field.startswith("transform."):
        if field not in _TRANSFORM_OFFSETS:
            raise ProjectModelError(f"未知 transform 字段：{field}")
        return _finite_f32(value, field)
    if field == "argb":
        return _u32(value, field, allow_argb_text=True)
    if field == "initial_phase":
        return _u32(value, field)
    if field == "anchor":
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            raise ProjectModelError("anchor 必须是 [x, y]")
        x, x_raw = _finite_f32(value[0], "anchor.x")
        y, y_raw = _finite_f32(value[1], "anchor.y")
        if width != 8:
            raise ProjectModelError("anchor 原始宽度不正确")
        return [x, y], x_raw + y_raw
    if field == "name":
        if not isinstance(value, str) or "\0" in value:
            raise ProjectModelError("name 必须是 UTF-8 字符串且不得包含 NUL")
        try:
            raw = value.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ProjectModelError("name 不是有效 UTF-8 字符串") from exc
        if len(raw) != width:
            raise ProjectModelError("name 只允许等 UTF-8 字节长度的原位改名")
        return value, raw
    raise ProjectModelError(f"不支持的 Edit Set 字段：{field}")


def _decode_field(field: str, raw: bytes) -> Any:
    if field.startswith("transform."):
        return struct.unpack("<f", raw)[0]
    if field in {"argb", "initial_phase"}:
        return struct.unpack("<I", raw)[0]
    if field == "anchor":
        return list(struct.unpack("<ff", raw))
    if field == "name":
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ProjectModelError("Edit Set name 原始值不是 UTF-8") from exc
    raise ProjectModelError(f"不支持的 Edit Set 字段：{field}")


def _validate_edit_set(
    image: RawBileImage,
    identities: dict[str, Any],
    edit_set: dict[str, Any],
) -> None:
    expected_root_keys = {
        "schema", "projectId", "sourceSha256", "sourceVersion", "canEdit",
        "state", "operations", "structuralEditsAllowed", "compilerState",
    }
    if set(edit_set) != expected_root_keys:
        raise ProjectModelError("Edit Set 根字段不完整或包含未知字段")
    if edit_set.get("schema") != EDIT_SET_SCHEMA:
        raise ProjectModelError("Edit Set schema 不匹配")
    if edit_set.get("structuralEditsAllowed") is not False:
        raise ProjectModelError("Project Edit Set 永远不允许结构性修改")
    if edit_set.get("compilerState") not in {"PendingOverlayCompiler", "Available"}:
        raise ProjectModelError("Edit Set compilerState 不受支持")
    if edit_set.get("sourceSha256") != image.sha256:
        raise ProjectModelError("Edit Set sourceSha256 与原始 BIN 不一致")
    if edit_set.get("sourceVersion") != image.document.header.version:
        raise ProjectModelError("Edit Set sourceVersion 与原始 BIN 不一致")
    operations = edit_set.get("operations")
    if not isinstance(operations, list):
        raise ProjectModelError("Edit Set operations 必须是数组")
    can_edit = image.document.header.version in (3, 4)
    if edit_set.get("canEdit") is not can_edit:
        raise ProjectModelError("Edit Set canEdit 与 BILE 版本策略不一致")
    if operations and not can_edit:
        raise ProjectModelError("BILE v2 不允许包含任何写入操作")
    expected_state = "Validated" if operations else "Empty"
    if edit_set.get("state") != expected_state:
        raise ProjectModelError("Edit Set state 与 operations 数量不一致")

    records = _record_map(identities)
    current_raw: dict[tuple[str, int, str], bytes] = {}
    seen_ids: set[str] = set()
    for expected_sequence, operation in enumerate(operations, 1):
        if not isinstance(operation, dict):
            raise ProjectModelError("Edit Set operation 必须是对象")
        allowed_keys = {
            "operationId", "sequence", "kind", "target", "field", "storage",
            "before", "after", "beforeRawHex", "afterRawHex",
            "validationState", "validation",
        }
        if set(operation) != allowed_keys:
            raise ProjectModelError("Edit Set operation 字段不完整或包含未知字段")
        operation_id = operation.get("operationId")
        if operation_id != f"op-{expected_sequence:06d}" or operation_id in seen_ids:
            raise ProjectModelError("Edit Set operationId/sequence 不连续或重复")
        seen_ids.add(operation_id)
        sequence = operation.get("sequence")
        if (
            not isinstance(sequence, int) or isinstance(sequence, bool)
            or sequence != expected_sequence or operation.get("kind") != "SetField"
        ):
            raise ProjectModelError("Edit Set 仅允许按序排列的 SetField 操作")

        target = operation.get("target")
        if not isinstance(target, dict) or set(target) != {"section", "index", "recordId"}:
            raise ProjectModelError("Edit Set target 身份字段无效")
        section, index = target["section"], target["index"]
        identity = records.get((section, index))
        if identity is None or target["recordId"] != identity["recordId"]:
            raise ProjectModelError(f"Edit Set 目标身份与原始记录不匹配：{section}[{index}]")
        field = operation.get("field")
        if not isinstance(field, str):
            raise ProjectModelError(f"{operation_id} field 必须是字符串")
        descriptor = _field_descriptor(image, section, index, field, identities)
        storage = operation.get("storage")
        expected_storage = {
            "section": descriptor["storageSection"],
            "offset": descriptor["storageOffset"],
            "width": descriptor["width"],
        }
        if storage != expected_storage:
            raise ProjectModelError(f"{operation_id} storage 范围与目标字段不匹配")

        try:
            before_raw = bytes.fromhex(operation["beforeRawHex"])
            after_raw = bytes.fromhex(operation["afterRawHex"])
        except (TypeError, ValueError) as exc:
            raise ProjectModelError(f"{operation_id} raw hex 无效") from exc
        if len(before_raw) != descriptor["width"] or len(after_raw) != descriptor["width"]:
            raise ProjectModelError(f"{operation_id} 改变了字段字节宽度")

        key = (section, index, field)
        expected_before = current_raw.get(key, descriptor["raw"])
        if before_raw != expected_before:
            raise ProjectModelError(f"{operation_id} beforeRaw 与原始值或前序操作结果不一致")
        before_value, packed_before = _pack_field(field, operation["before"], descriptor["width"])
        after_value, packed_after = _pack_field(field, operation["after"], descriptor["width"])
        if packed_before != before_raw or packed_after != after_raw:
            raise ProjectModelError(f"{operation_id} before/after 与 raw bit pattern 不一致")
        if before_raw == after_raw:
            raise ProjectModelError(f"{operation_id} 是无实际变化的空操作")

        validation = operation.get("validation")
        required_checks = {
            "sourceSha256Bound": True,
            "recordIdentityMatched": True,
            "beforeValueMatched": True,
            "fieldWhitelisted": True,
            "structurePreserving": True,
            "requiresOriginalGameValidation": True,
        }
        if operation.get("validationState") != "Validated" or validation != required_checks:
            raise ProjectModelError(f"{operation_id} 缺少完整的 Edit Set 校验状态")
        current_raw[key] = after_raw


def import_bile_project(
    source_bin: str | Path,
    project_dir: str | Path,
    *,
    xml_path: str | Path | None = None,
    texture_path: str | Path | None = None,
    origin_kind: str = "ImportedOriginal",
) -> ProjectValidationReport:
    """创建 reference-only 工程；不复制任何 BIN/XML/WebP/PNG 原始资源。"""
    if origin_kind not in _ALLOWED_ORIGIN_KINDS:
        raise ProjectModelError(f"不允许的 origin_kind：{origin_kind}")
    image = RawBileImage.read(source_bin)
    source = Path(image.source_path)
    destination = Path(project_dir).expanduser().absolute()
    if not destination.name or destination.is_symlink():
        raise ProjectModelError("Project 输出目录无效或是符号链接")
    if destination.exists():
        raise ProjectModelError(f"Project 输出目录已存在；拒绝覆盖：{destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)

    if xml_path is None:
        candidate = source.with_suffix(".xml")
        xml_path = candidate if candidate.is_file() else None
    if texture_path is None:
        webp = source.with_suffix(".webp")
        png = source.with_suffix(".png")
        texture_path = webp if webp.is_file() else (png if png.is_file() else None)

    references = [_file_reference(source, "bile")]
    if xml_path is not None:
        references.append(_file_reference(xml_path, "atlas-xml"))
    if texture_path is not None:
        references.append(_file_reference(texture_path, "texture"))

    project_id = f"bile-{image.sha256[:20]}"
    version = image.document.header.version
    writer_capability = "Conditional" if version in (3, 4) else "NoGo"
    project = {
        "schema": PROJECT_SCHEMA,
        "projectId": project_id,
        "displayName": source.stem,
        "format": "BILE",
        "originKind": origin_kind,
        "createdAtUtc": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "source": {
            "bin": references[0],
            "version": version,
            "fps": image.document.header.fps,
        },
        "paths": {
            "assetManifest": "assets/manifest.json",
            "recordIdentities": "metadata/record-identities.json",
            "editSet": "metadata/edit-set.json",
            "motionsDirectory": "motions",
            "rawPolicy": "raw/README.md",
        },
        "writer": {
            "capability": writer_capability,
            "scope": "ExistingBileOnly",
            "newBileGeneration": "NoGo",
            "structuralEdits": "NoGo",
            "playbackMode": "NoGo",
        },
        "compiler": {
            "status": "Available",
            "writesBinary": True,
            "candidateOnly": True,
            "inPlaceWrite": False,
        },
        "validation": {
            "sourceParse": "Passed",
            "sourceSha256Bound": True,
            "recordIdentities": "Generated",
            "originalGame": "NotYetOriginalValidated",
        },
    }
    asset_manifest = {
        "schema": ASSET_MANIFEST_SCHEMA,
        "projectId": project_id,
        "sourceSha256": image.sha256,
        "storagePolicy": "ReferenceOnly",
        "references": references,
        "copiedPayloads": [],
    }
    identities = _record_identities(image)
    edit_set = {
        "schema": EDIT_SET_SCHEMA,
        "projectId": project_id,
        "sourceSha256": image.sha256,
        "sourceVersion": version,
        "canEdit": version in (3, 4),
        "state": "Empty",
        "operations": [],
        "structuralEditsAllowed": False,
        "compilerState": "Available",
    }
    if references[0]["sha256"] != image.sha256 or references[0]["sizeBytes"] != len(image.data):
        raise ProjectModelError("读取 BIN 与建立 source reference 期间源文件发生变化")

    stage = Path(tempfile.mkdtemp(prefix=f".{destination.name}.", dir=str(destination.parent)))
    try:
        for directory in ("assets", "motions", "metadata", "raw"):
            (stage / directory).mkdir()
        _write_json(stage / "project.json", project)
        _write_json(stage / "assets" / "manifest.json", asset_manifest)
        _write_json(stage / "metadata" / "record-identities.json", identities)
        _write_json(stage / "metadata" / "edit-set.json", edit_set)
        (stage / "motions" / "README.md").write_text(
            "# Motions\n\n本目录用于后续保存语义动作分组与编辑意图；当前不包含原始 BILE 或游戏资源。\n",
            encoding="utf-8",
        )
        (stage / "raw" / "README.md").write_text(
            "# Raw References\n\n原始 BIN/XML/纹理始终保留在外部源路径。Project 只保存路径、SHA-256、记录身份和字段级 Edit Set，不复制原始 payload。\n",
            encoding="utf-8",
        )
        if destination.exists() or destination.is_symlink():
            raise ProjectModelError(f"Project 输出目录在导入期间已被创建：{destination}")
        validate_project(stage)
        os.rename(stage, destination)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    try:
        return validate_project(destination)
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise


def _load_project_files(project_dir: str | Path) -> tuple[Path, dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    root_input = Path(project_dir).expanduser()
    if root_input.is_symlink() or not root_input.is_dir():
        raise ProjectModelError(f"Project 目录不存在或不是普通目录：{root_input}")
    root = root_input.resolve(strict=True)
    for directory in ("assets", "motions", "metadata", "raw"):
        child = root / directory
        if child.is_symlink() or not child.is_dir():
            raise ProjectModelError(f"Project 子目录缺失或不允许符号链接：{directory}")
    project_path = root / "project.json"
    if project_path.is_symlink():
        raise ProjectModelError("project.json 不允许符号链接")
    project = _read_json(project_path, "project.json")
    if project.get("schema") != PROJECT_SCHEMA or project.get("format") != "BILE":
        raise ProjectModelError("Project schema/format 不匹配")
    paths = project.get("paths")
    if not isinstance(paths, dict):
        raise ProjectModelError("project.json 缺少 paths")
    asset_manifest = _read_json(
        _relative_project_file(root, paths.get("assetManifest"), "paths.assetManifest"),
        "assets/manifest.json",
    )
    identities = _read_json(
        _relative_project_file(root, paths.get("recordIdentities"), "paths.recordIdentities"),
        "metadata/record-identities.json",
    )
    edit_set = _read_json(
        _relative_project_file(root, paths.get("editSet"), "paths.editSet"),
        "metadata/edit-set.json",
    )
    return root, project, asset_manifest, identities, edit_set


def validate_project(project_dir: str | Path) -> ProjectValidationReport:
    root, project, asset_manifest, identities, edit_set = _load_project_files(project_dir)
    origin_kind = project.get("originKind")
    if origin_kind not in _ALLOWED_ORIGIN_KINDS:
        raise ProjectModelError(f"Project originKind 不受支持：{origin_kind}")
    source = project.get("source")
    if not isinstance(source, dict) or not isinstance(source.get("bin"), dict):
        raise ProjectModelError("project.json 缺少 source.bin reference")
    source_ref = source["bin"]
    source_path_value = source_ref.get("path")
    if (
        source_ref.get("role") != "bile"
        or source_ref.get("referenceOnly") is not True
        or not isinstance(source_path_value, str)
        or not Path(source_path_value).is_absolute()
    ):
        raise ProjectModelError("source.bin 必须是带绝对路径的 reference-only BILE 文件")
    source_path = Path(source_path_value)
    try:
        image = RawBileImage.read(source_path)
    except (OSError, ValueError) as exc:
        raise ProjectModelError(f"无法读取外部源 BIN：{exc}") from exc
    if image.sha256 != source_ref.get("sha256"):
        raise ProjectModelError("外部源 BIN SHA-256 已变化；Project source identity 失效")
    if (
        not isinstance(source_ref.get("sizeBytes"), int)
        or isinstance(source_ref.get("sizeBytes"), bool)
        or not isinstance(source.get("version"), int)
        or isinstance(source.get("version"), bool)
    ):
        raise ProjectModelError("source.bin size/version 类型无效")
    if len(image.data) != source_ref.get("sizeBytes"):
        raise ProjectModelError("外部源 BIN 文件大小与 Project reference 不一致")
    if image.document.header.version != source.get("version"):
        raise ProjectModelError("外部源 BIN 版本与 Project reference 不一致")
    if source.get("fps") != image.document.header.fps:
        raise ProjectModelError("外部源 BIN FPS 与 Project reference 不一致")
    if project.get("projectId") != f"bile-{image.sha256[:20]}":
        raise ProjectModelError("projectId 与源 BIN SHA-256 不一致")

    if set(asset_manifest) != {
        "schema", "projectId", "sourceSha256", "storagePolicy", "references", "copiedPayloads"
    }:
        raise ProjectModelError("Asset manifest 字段不完整或包含未知字段")
    if asset_manifest.get("schema") != ASSET_MANIFEST_SCHEMA:
        raise ProjectModelError("Asset manifest schema 不匹配")
    if asset_manifest.get("storagePolicy") != "ReferenceOnly" or asset_manifest.get("copiedPayloads") != []:
        raise ProjectModelError("Asset manifest 违反 reference-only 策略")
    if asset_manifest.get("projectId") != project["projectId"] or asset_manifest.get("sourceSha256") != image.sha256:
        raise ProjectModelError("Asset manifest 与 Project source identity 不一致")
    references = asset_manifest.get("references")
    if not isinstance(references, list) or not references or references[0] != source_ref:
        raise ProjectModelError("Asset manifest 必须以当前 BILE source reference 开头")
    warnings: list[str] = []
    for reference in references[1:]:
        if (
            not isinstance(reference, dict)
            or reference.get("referenceOnly") is not True
            or not isinstance(reference.get("role"), str)
            or not isinstance(reference.get("path"), str)
            or not isinstance(reference.get("sha256"), str)
        ):
            raise ProjectModelError("Optional asset reference 格式无效")
        path = Path(reference["path"])
        if not path.is_file() or path.is_symlink():
            warnings.append(f"OptionalAssetUnavailable:{reference.get('role')}")
        elif _sha256_file(path) != reference.get("sha256"):
            warnings.append(f"OptionalAssetHashMismatch:{reference.get('role')}")

    expected_identities = _record_identities(image)
    if identities != expected_identities:
        raise ProjectModelError("record-identities.json 与当前源 BIN 的记录身份/哈希不一致")
    if edit_set.get("projectId") != project["projectId"]:
        raise ProjectModelError("Edit Set projectId 与 Project 不一致")
    _validate_edit_set(image, identities, edit_set)

    forbidden = [
        path for pattern in ("*.bin", "*.xml", "*.webp", "*.png")
        for path in root.rglob(pattern)
    ]
    if forbidden:
        raise ProjectModelError(
            f"Project 违反 reference-only 策略，发现复制的原始资源：{forbidden[0].name}"
        )

    writer = project.get("writer")
    expected_capability = "Conditional" if image.document.header.version in (3, 4) else "NoGo"
    if (
        not isinstance(writer, dict)
        or writer.get("capability") != expected_capability
        or writer.get("scope") != "ExistingBileOnly"
        or writer.get("newBileGeneration") != "NoGo"
        or writer.get("structuralEdits") != "NoGo"
        or writer.get("playbackMode") != "NoGo"
    ):
        raise ProjectModelError("Project writer capability 越过当前安全边界")
    compiler = project.get("compiler")
    if not isinstance(compiler, dict):
        raise ProjectModelError("Project 缺少 compiler capability")
    compiler_status = compiler.get("status")
    if compiler_status == "PendingOverlayCompiler":
        if compiler.get("writesBinary") is not False:
            raise ProjectModelError("Pending Overlay Compiler 不得写出 BIN")
    elif compiler_status == "Available":
        if (
            compiler.get("writesBinary") is not True
            or compiler.get("candidateOnly") is not True
            or compiler.get("inPlaceWrite") is not False
        ):
            raise ProjectModelError("Overlay Compiler 仅允许另存候选，禁止原位写回")
    else:
        raise ProjectModelError("Project compiler status 不受支持")
    expected_paths = {
        "assetManifest": "assets/manifest.json",
        "recordIdentities": "metadata/record-identities.json",
        "editSet": "metadata/edit-set.json",
        "motionsDirectory": "motions",
        "rawPolicy": "raw/README.md",
    }
    if project.get("paths") != expected_paths:
        raise ProjectModelError("Project 内部路径布局与 schema 不一致")
    operations = edit_set["operations"]
    project_kind = (
        "SyntheticFixture"
        if origin_kind == "SyntheticFixture"
        else ("ImportedModified" if operations else "ImportedOriginal")
    )
    return ProjectValidationReport(
        status="Valid",
        project_kind=project_kind,
        source_sha256=image.sha256,
        source_version=image.document.header.version,
        operation_count=len(operations),
        writer_capability=project["writer"]["capability"],
        warnings=tuple(warnings),
    )


def append_edit_operation(
    project_dir: str | Path,
    *,
    section: str,
    index: int,
    field: str,
    after: Any,
) -> dict[str, Any]:
    """追加一个带 target identity 与 before/after raw bits 的字段级操作；不编译 BIN。"""
    report = validate_project(project_dir)
    if report.writer_capability != "Conditional":
        raise ProjectModelError("当前 BILE 版本没有可用的 Existing-BILE 写入能力")
    root, project, _assets, identities, edit_set = _load_project_files(project_dir)
    source_path = Path(project["source"]["bin"]["path"])
    image = RawBileImage.read(source_path)
    descriptor = _field_descriptor(image, section, index, field, identities)
    key = (section, index, field)
    previous = next(
        (
            operation for operation in reversed(edit_set["operations"])
            if (
                operation["target"]["section"],
                operation["target"]["index"],
                operation["field"],
            ) == key
        ),
        None,
    )
    before_raw = (
        bytes.fromhex(previous["afterRawHex"])
        if previous is not None
        else descriptor["raw"]
    )
    before_value = _decode_field(field, before_raw)
    if field.startswith("transform.") and not math.isfinite(before_value):
        raise ProjectModelError("拒绝基线包含 NaN/Infinity 的 transform 字段")
    if field == "anchor" and not all(math.isfinite(value) for value in before_value):
        raise ProjectModelError("拒绝基线包含 NaN/Infinity 的 anchor")
    normalized_after, after_raw = _pack_field(field, after, descriptor["width"])
    if before_raw == after_raw:
        raise ProjectModelError("Edit Set 不接受无实际变化的空操作")

    sequence = len(edit_set["operations"]) + 1
    operation = {
        "operationId": f"op-{sequence:06d}",
        "sequence": sequence,
        "kind": "SetField",
        "target": {
            "section": section,
            "index": index,
            "recordId": descriptor["targetRecord"]["recordId"],
        },
        "field": field,
        "storage": {
            "section": descriptor["storageSection"],
            "offset": descriptor["storageOffset"],
            "width": descriptor["width"],
        },
        "before": before_value,
        "after": normalized_after,
        "beforeRawHex": before_raw.hex(),
        "afterRawHex": after_raw.hex(),
        "validationState": "Validated",
        "validation": {
            "sourceSha256Bound": True,
            "recordIdentityMatched": True,
            "beforeValueMatched": True,
            "fieldWhitelisted": True,
            "structurePreserving": True,
            "requiresOriginalGameValidation": True,
        },
    }
    candidate_edit_set = {
        **edit_set,
        "state": "Validated",
        "operations": [*edit_set["operations"], operation],
    }
    _validate_edit_set(image, identities, candidate_edit_set)
    _write_json_atomic(
        _relative_project_file(root, project["paths"]["editSet"], "paths.editSet"),
        candidate_edit_set,
    )
    validate_project(root)
    return operation
