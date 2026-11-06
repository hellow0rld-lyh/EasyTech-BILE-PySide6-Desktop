"""BILE 原始字节镜像。

该层把解析模型与原始文件分开保存：语义解析用于理解，原始镜像负责保证
未知字段、Section Header、字符串池和所有未解释字节都能逐字节保留。
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .bile_format import BileDocument, BileFormatError, parse_bytes


@dataclass(frozen=True)
class RawBileSection:
    index: int
    tag: str
    offset: int
    total_size: int
    count: int
    header_size: int
    header_bytes: bytes
    payload_bytes: bytes

    @property
    def end_offset(self) -> int:
        return self.offset + self.total_size


@dataclass(frozen=True)
class RawBileImage:
    """完整原始 BIN 的不可变镜像及其独立语义解析结果。"""

    source_path: str
    data: bytes
    sha256: str
    document: BileDocument
    sections: tuple[RawBileSection, ...]

    @classmethod
    def from_bytes(
        cls,
        data: bytes | bytearray | memoryview,
        source_path: str = "<memory>",
    ) -> "RawBileImage":
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise TypeError("BILE 原始镜像必须由 bytes-like 数据构造")
        owned = bytes(data)
        document = parse_bytes(owned)
        sections: list[RawBileSection] = []
        for index, section in enumerate(document.sections.values()):
            header_size = section.payload_offset - section.offset
            sections.append(
                RawBileSection(
                    index=index,
                    tag=section.tag,
                    offset=section.offset,
                    total_size=section.total_size,
                    count=section.count,
                    header_size=header_size,
                    header_bytes=owned[section.offset:section.payload_offset],
                    payload_bytes=owned[section.payload_offset:section.offset + section.total_size],
                )
            )
        return cls(
            source_path=str(source_path),
            data=owned,
            sha256=hashlib.sha256(owned).hexdigest(),
            document=document,
            sections=tuple(sections),
        )

    @classmethod
    def read(cls, path: str | Path) -> "RawBileImage":
        source = Path(path)
        if source.is_symlink():
            raise BileFormatError(f"拒绝通过符号链接读取 BILE 源文件：{source}")
        if not source.is_file():
            raise FileNotFoundError(f"BILE 源文件不存在或不是普通文件：{source}")
        resolved = source.resolve(strict=True)
        return cls.from_bytes(resolved.read_bytes(), str(resolved))

    def section(self, tag: str) -> RawBileSection:
        for section in self.sections:
            if section.tag == tag:
                return section
        raise KeyError(f"BILE 不包含 Section：{tag}")

    def to_bytes(self) -> bytes:
        """返回原始字节，不经过重新序列化。"""
        return self.data

    def exact_round_trip(self) -> bool:
        """确认原始镜像导出与输入逐字节相同。"""
        return self.to_bytes() == self.data
