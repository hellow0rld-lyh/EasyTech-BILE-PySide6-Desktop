"""BILE 候选文件的精确字节门禁与事务式发布。

本模块只提供固定长度字段覆盖所需的底层机制，不解释或放宽任何 BILE 字段语义。
字段白名单与上下文约束由 interchange.py 等上层调用者负责。
"""
from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .bile_format import BileDocument, BileFormatError
from .raw_image import RawBileImage


class BileMutationError(BileFormatError):
    """候选 BIN 未通过安全写入合同。"""


def changed_byte_offsets(original: bytes, candidate: bytes) -> tuple[int, ...]:
    if len(original) != len(candidate):
        raise BileMutationError(
            f"候选文件长度发生变化：原始 {len(original)}，候选 {len(candidate)}"
        )
    return tuple(index for index, (old, new) in enumerate(zip(original, candidate)) if old != new)


class BileMutationBuffer:
    """固定长度、逐字节记账的候选缓冲区。"""

    def __init__(self, image: RawBileImage) -> None:
        self._image = image
        self._data = bytearray(image.data)
        self._expected_changed_offsets: set[int] = set()

    def read(self, offset: int, width: int) -> bytes:
        if offset < 0 or width < 0 or offset + width > len(self._data):
            raise BileMutationError(
                f"读取范围越界：offset=0x{offset:X}, width={width}, file={len(self._data)}"
            )
        return bytes(self._data[offset:offset + width])

    def replace(self, offset: int, replacement: bytes, label: str) -> None:
        if not isinstance(replacement, bytes):
            raise TypeError("字段替换内容必须是 bytes")
        if offset < 0 or offset + len(replacement) > len(self._data):
            raise BileMutationError(
                f"{label} 写入范围越界：offset=0x{offset:X}, width={len(replacement)}"
            )
        old = bytes(self._data[offset:offset + len(replacement)])
        if len(old) != len(replacement):
            raise BileMutationError(f"{label} 不允许改变字段宽度")
        self._expected_changed_offsets.update(
            offset + index
            for index, (before, after) in enumerate(zip(old, replacement))
            if before != after
        )
        self._data[offset:offset + len(replacement)] = replacement

    @property
    def expected_changed_offsets(self) -> tuple[int, ...]:
        return tuple(sorted(self._expected_changed_offsets))

    def to_bytes(self) -> bytes:
        return bytes(self._data)


@dataclass(frozen=True)
class BileMutationReport:
    input_path: str
    output_path: str
    input_sha256: str
    output_sha256: str
    size: int
    version: int
    section_count: int
    changed_byte_offsets: tuple[int, ...]
    document: BileDocument


def _allowed_mutation_offsets(image: RawBileImage) -> set[int]:
    """返回当前 Python 编辑器实际开放的字段字节范围。"""
    allowed: set[int] = set()
    bele = image.document.sections["BELE"]
    for index in range(bele.count):
        record_start = bele.payload_offset + index * 44
        # BELE affine (0x00..0x17), ARGB (0x18..0x1B), initial_phase (0x1C..0x1F)。
        allowed.update(range(record_start, record_start + 32))

    bmti = image.document.sections["BMTI"]
    for index in range(bmti.count):
        record_start = bmti.payload_offset + index * 56
        # BMTI anchor only; type, counts and all opaque words remain read-only.
        allowed.update(range(record_start + 8, record_start + 16))

    brts = image.document.sections["BRTS"]
    name_offset_users: dict[int, int] = {}
    for element in image.document.elements:
        name_offset_users[element.name_offset] = name_offset_users.get(element.name_offset, 0) + 1
    for element in image.document.elements:
        # 多个元素共享字符串偏移时，原位改名会同时改变它们的显示名。
        # 当前编辑器不开放这类有多元素副作用的字节范围。
        if name_offset_users[element.name_offset] != 1:
            continue
        start = brts.payload_offset + element.name_offset
        allowed.update(range(start, start + len(element.name.encode("utf-8"))))
    return allowed


def verify_candidate_bytes(
    original_image: RawBileImage,
    candidate_bytes: bytes,
    expected_changed_offsets: Iterable[int],
) -> tuple[RawBileImage, tuple[int, ...]]:
    """验证结构不变，并要求实际变化字节集合与编辑计划完全一致。"""
    version = original_image.document.header.version
    if version not in (3, 4):
        raise BileMutationError(
            f"BILE v{version} 当前严格只读；底层候选门禁仅开放给 v3/v4"
        )
    candidate_image = RawBileImage.from_bytes(candidate_bytes, "<candidate>")
    if len(candidate_image.data) != len(original_image.data):
        raise BileMutationError("候选 BIN 改变了原始文件长度")
    if candidate_image.document.header.version != original_image.document.header.version:
        raise BileMutationError("候选 BIN 改变了 BILE 版本")
    if candidate_image.document.header.section_count != original_image.document.header.section_count:
        raise BileMutationError("候选 BIN 改变了 Section 数量")
    if len(candidate_image.sections) != len(original_image.sections):
        raise BileMutationError("候选 BIN 改变了 Section 布局")

    for before, after in zip(original_image.sections, candidate_image.sections):
        if (
            before.index != after.index
            or before.tag != after.tag
            or before.offset != after.offset
            or before.total_size != after.total_size
            or before.count != after.count
            or before.header_size != after.header_size
            or before.header_bytes != after.header_bytes
            or len(before.payload_bytes) != len(after.payload_bytes)
        ):
            raise BileMutationError(
                f"候选 BIN 改变了 {before.tag} 的 Section Header、顺序、计数或尺寸"
            )

    before_string_offsets = tuple(original_image.document.strings)
    after_string_offsets = tuple(candidate_image.document.strings)
    if before_string_offsets != after_string_offsets:
        raise BileMutationError("候选 BIN 改变了 BRTS 字符串池偏移或边界")
    for string_offset, before_text in original_image.document.strings.items():
        after_text = candidate_image.document.strings[string_offset]
        if len(before_text.encode("utf-8")) != len(after_text.encode("utf-8")):
            raise BileMutationError(
                f"候选 BIN 改变了 BRTS[{string_offset}] 的 UTF-8 字节长度"
            )

    raw_expected = tuple(expected_changed_offsets)
    if any(not isinstance(offset, int) or isinstance(offset, bool) for offset in raw_expected):
        raise BileMutationError("编辑计划中的 changed offsets 必须是整数")
    expected = tuple(sorted(set(raw_expected)))
    if len(expected) != len(raw_expected):
        raise BileMutationError("编辑计划中的 changed offsets 存在重复")
    actual = changed_byte_offsets(original_image.data, candidate_image.data)
    allowed_offsets = _allowed_mutation_offsets(original_image)
    forbidden = tuple(offset for offset in actual if offset not in allowed_offsets)
    if forbidden:
        raise BileMutationError(
            "候选 BIN 修改了当前编辑器未开放的字段："
            f"{forbidden[:12]}"
        )
    if actual != expected:
        unexpected = sorted(set(actual) - set(expected))
        missing = sorted(set(expected) - set(actual))
        raise BileMutationError(
            "实际 changed-byte set 与编辑计划不一致；"
            f"计划外变化={unexpected[:12]}，未发生的计划变化={missing[:12]}"
        )
    return candidate_image, actual


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def publish_verified_candidate(
    source_path: str | Path,
    output_path: str | Path,
    candidate_bytes: bytes,
    expected_source_sha256: str,
    expected_changed_offsets: Iterable[int],
    *,
    overwrite: bool = False,
) -> BileMutationReport:
    """验证源文件未漂移后，以同目录临时文件和原子发布写出候选 BIN。

    默认不覆盖已有目标。显式 overwrite=True 时先准备并验证备份，再原子替换；
    任何发布后校验失败都会尝试恢复原目标。
    """
    if not isinstance(overwrite, bool):
        raise TypeError("overwrite 必须是 bool")

    source_input = Path(source_path)
    if source_input.is_symlink():
        raise BileMutationError(f"拒绝通过符号链接修改 BILE 源文件：{source_input}")
    if not source_input.is_file():
        raise FileNotFoundError(f"BILE 源文件不存在或不是普通文件：{source_input}")
    source = source_input.resolve(strict=True)

    output_input = Path(output_path)
    if output_input.is_symlink():
        raise BileMutationError(f"拒绝将候选 BIN 写入符号链接：{output_input}")
    if not output_input.name or output_input.name in (".", ".."):
        raise BileMutationError("候选 BIN 输出路径无效")
    if not output_input.parent.exists() or not output_input.parent.is_dir():
        raise FileNotFoundError(f"候选 BIN 输出目录不存在：{output_input.parent}")
    output = output_input.parent.resolve(strict=True) / output_input.name

    if os.path.normcase(str(source)) == os.path.normcase(str(output)):
        raise BileMutationError("拒绝覆盖输入 BIN；候选文件必须另存为")
    if output.exists():
        try:
            if os.path.samefile(source, output):
                raise BileMutationError("输入与输出是同一个底层文件，拒绝覆盖")
        except OSError:
            pass
        if output.is_symlink() or not output.is_file():
            raise BileMutationError(f"候选输出已存在但不是普通文件：{output}")
        if not overwrite:
            raise BileMutationError(f"候选输出已存在；需要显式确认覆盖：{output}")
        previous_output_bytes = output.read_bytes()
        previous_output_sha256 = _sha256(previous_output_bytes)
    else:
        previous_output_bytes = None
        previous_output_sha256 = None

    original_bytes = source.read_bytes()
    input_sha256 = _sha256(original_bytes)
    if not isinstance(expected_source_sha256, str) or input_sha256 != expected_source_sha256.lower():
        raise BileMutationError("源 BIN SHA-256 与补丁绑定值不一致；拒绝写入")
    original_image = RawBileImage.from_bytes(original_bytes, str(source))
    candidate_image, actual_changed_offsets = verify_candidate_bytes(
        original_image, bytes(candidate_bytes), expected_changed_offsets
    )
    output_sha256 = candidate_image.sha256

    temp_fd, temp_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".candidate.tmp", dir=str(output.parent)
    )
    temp_path: Path | None = Path(temp_name)
    backup_path: Path | None = None
    try:
        with os.fdopen(temp_fd, "wb") as stream:
            stream.write(candidate_image.data)
            stream.flush()
            os.fsync(stream.fileno())

        staged_bytes = temp_path.read_bytes()
        if staged_bytes != candidate_image.data or _sha256(staged_bytes) != output_sha256:
            raise BileMutationError("临时候选文件回读或 SHA-256 校验失败")
        RawBileImage.from_bytes(staged_bytes, str(temp_path))

        if _sha256(source.read_bytes()) != input_sha256:
            raise BileMutationError("候选准备期间源 BIN 已发生变化；拒绝发布")

        if previous_output_bytes is None:
            if output.exists() or output.is_symlink():
                raise BileMutationError("候选输出在发布前被其他进程创建；拒绝覆盖")
            try:
                os.link(temp_path, output)
            except FileExistsError as exc:
                raise BileMutationError("候选输出在发布时已存在；拒绝覆盖") from exc
            except OSError as exc:
                raise BileMutationError(
                    "当前文件系统不支持安全的原子 no-overwrite 发布；未写入候选文件"
                ) from exc
            try:
                published = output.read_bytes()
                if published != candidate_image.data or _sha256(published) != output_sha256:
                    raise BileMutationError("候选发布后回读与验证结果不一致")
                RawBileImage.from_bytes(published, str(output))
            except Exception:
                try:
                    if output.is_file() and _sha256(output.read_bytes()) == output_sha256:
                        output.unlink()
                except OSError:
                    pass
                raise
        else:
            if (
                not output.exists()
                or output.is_symlink()
                or not output.is_file()
                or _sha256(output.read_bytes()) != previous_output_sha256
            ):
                raise BileMutationError("候选输出在准备期间发生变化；拒绝覆盖")
            backup_fd, backup_name = tempfile.mkstemp(
                prefix=f".{output.name}.", suffix=".backup.tmp", dir=str(output.parent)
            )
            backup_path = Path(backup_name)
            with os.fdopen(backup_fd, "wb") as backup_stream:
                backup_stream.write(previous_output_bytes)
                backup_stream.flush()
                os.fsync(backup_stream.fileno())
            if _sha256(backup_path.read_bytes()) != previous_output_sha256:
                raise BileMutationError("候选输出备份校验失败；拒绝覆盖")
            if _sha256(output.read_bytes()) != previous_output_sha256:
                raise BileMutationError("候选输出在备份期间发生变化；拒绝覆盖")
            os.replace(temp_path, output)
            temp_path = None
            try:
                published = output.read_bytes()
                if published != candidate_image.data or _sha256(published) != output_sha256:
                    raise BileMutationError("覆盖发布后的候选文件校验失败")
                RawBileImage.from_bytes(published, str(output))
            except Exception:
                try:
                    os.replace(backup_path, output)
                except OSError as restore_error:
                    retained_backup = backup_path
                    backup_path = None
                    raise BileMutationError(
                        f"发布校验失败且无法恢复旧候选；备份保留在：{retained_backup}"
                    ) from restore_error
                backup_path = None
                raise
            try:
                backup_path.unlink()
            except OSError:
                pass
            backup_path = None

        return BileMutationReport(
            input_path=str(source),
            output_path=str(output),
            input_sha256=input_sha256,
            output_sha256=output_sha256,
            size=len(candidate_image.data),
            version=candidate_image.document.header.version,
            section_count=candidate_image.document.header.section_count,
            changed_byte_offsets=actual_changed_offsets,
            document=candidate_image.document,
        )
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
        if backup_path is not None:
            try:
                backup_path.unlink(missing_ok=True)
            except OSError:
                pass
