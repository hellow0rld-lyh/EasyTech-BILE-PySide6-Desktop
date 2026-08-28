"""仅验证 Spine 二进制头部兼容性；不解码骨骼、皮肤、附件或动画。"""
from __future__ import annotations

import argparse
import json
import math
import re
import struct
from dataclasses import asdict, dataclass
from pathlib import Path

VERSION = re.compile(r"^\d+\.\d+(?:\.\d+)?$")


class SpineHeaderError(ValueError):
    pass


class Reader:
    def __init__(self, data: bytes, offset: int = 0) -> None:
        self.data = data
        self.offset = offset

    def byte(self) -> int:
        if self.offset >= len(self.data):
            raise SpineHeaderError("读取超出文件末尾")
        value = self.data[self.offset]
        self.offset += 1
        return value

    def varint_positive(self) -> int:
        value = 0
        shift = 0
        for _ in range(5):
            byte = self.byte()
            value |= (byte & 0x7F) << shift
            if not byte & 0x80:
                return value
            shift += 7
        raise SpineHeaderError("varint 超过 5 字节")

    def string(self) -> str | None:
        count = self.varint_positive()
        if count == 0:
            return None
        if count == 1:
            return ""
        size = count - 1
        if self.offset + size > len(self.data):
            raise SpineHeaderError("字符串越过文件末尾")
        raw = self.data[self.offset:self.offset + size]
        self.offset += size
        return raw.decode("utf-8", errors="strict")

    def f32be(self) -> float:
        if self.offset + 4 > len(self.data):
            raise SpineHeaderError("浮点数越过文件末尾")
        value = struct.unpack_from(">f", self.data, self.offset)[0]
        self.offset += 4
        return value

    def boolean(self) -> bool:
        value = self.byte()
        if value not in (0, 1):
            raise SpineHeaderError(f"布尔值不是 0/1：{value}")
        return bool(value)


@dataclass(frozen=True)
class HeaderProbe:
    path: str
    bytes: int
    fingerprint_hex: str
    version_offset: int
    source_hash: str | None
    version: str | None
    bounds: tuple[float, float, float, float]
    nonessential: bool
    fps: float | None
    images: str | None
    audio: str | None
    header_end: int
    compatible: bool
    issue: str | None


def parse_from(data: bytes, offset: int, has_hash: bool) -> tuple[str | None, str | None, tuple[float, float, float, float], bool, float | None, str | None, str | None, int]:
    reader = Reader(data, offset)
    source_hash = reader.string() if has_hash else None
    version = reader.string()
    if version is None or not VERSION.fullmatch(version):
        raise SpineHeaderError(f"版本字符串无效：{version!r}")
    bounds = tuple(reader.f32be() for _ in range(4))
    if not all(math.isfinite(value) and abs(value) < 1_000_000 for value in bounds):
        raise SpineHeaderError(f"边界值不可信：{bounds}")
    nonessential = reader.boolean()
    fps = reader.f32be() if nonessential else None
    images = reader.string() if nonessential else None
    audio = reader.string() if nonessential else None
    return source_hash, version, bounds, nonessential, fps, images, audio, reader.offset


def probe(path: Path, root: Path) -> HeaderProbe:
    data = path.read_bytes()
    issues: list[str] = []
    for offset, has_hash in ((0, True), (8, False)):
        try:
            source_hash, version, bounds, nonessential, fps, images, audio, header_end = parse_from(data, offset, has_hash)
            return HeaderProbe(str(path.relative_to(root)), len(data), data[:offset].hex(), offset, source_hash, version, bounds, nonessential, fps, images, audio, header_end, True, None)
        except (SpineHeaderError, UnicodeDecodeError, struct.error) as exc:
            issues.append(f"@0x{offset:X}/{('hash' if has_hash else 'no-hash')}: {exc}")
    return HeaderProbe(str(path.relative_to(root)), len(data), data[:8].hex(), -1, None, None, (float("nan"),) * 4, False, None, None, None, 0, False, "; ".join(issues))


def markdown(rows: list[HeaderProbe]) -> str:
    total = len(rows)
    passed = sum(row.compatible for row in rows)
    by_entry: dict[str, int] = {}
    by_version: dict[str, int] = {}
    for row in rows:
        if row.compatible:
            by_entry[f"0x{row.version_offset:X}"] = by_entry.get(f"0x{row.version_offset:X}", 0) + 1
            by_version[row.version or "—"] = by_version.get(row.version or "—", 0) + 1
    lines = ["# 欧7 / 征2 Spine 头部兼容性探针", "", "> 探针尝试两种实测入口：欧7候选从 `0x00` 读取官方 `string hash → string version`；征2候选从 `0x08` 读取无 hash 的 `string version`。二者随后均读取 `4×f32be bounds → boolean nonessential`。通过不代表全量二进制已解码。", "", "| 汇总 | 数值 |", "|---|---:|", f"| 文件 | {total} |", f"| 头部兼容通过 | {passed} |", f"| 入口分布 | `{json.dumps(by_entry, ensure_ascii=False)}` |", f"| 版本分布 | `{json.dumps(by_version, ensure_ascii=False)}` |", "", "| 样本 | 入口 | source hash | 版本 | 前缀指纹 | bounds | 非必要数据 | fps | images | 头部末尾 | 结果 |", "|---|---:|---|---|---|---|---|---:|---|---:|---|"]
    for row in rows:
        bounds = ", ".join(f"{value:.2f}" for value in row.bounds) if row.compatible else "—"
        lines.append(f"| `{row.path}` | `0x{row.version_offset:X}` | `{row.source_hash or '—'}` | `{row.version or '—'}` | `{row.fingerprint_hex or '—'}` | `{bounds}` | {row.nonessential if row.compatible else '—'} | {row.fps if row.fps is not None else '—'} | `{row.images or '—'}` | {row.header_end} | {'PASS' if row.compatible else 'REJECT: ' + (row.issue or '')} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--recursive", action="store_true", help="将传入目录递归展开为 BIN 文件")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    files = []
    for path in args.files:
        if args.recursive and path.is_dir():
            files.extend(sorted(path.rglob("*.bin")))
        else:
            files.append(path)
    rows = [probe(path, args.root) for path in files]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"schema": "spine-header-compatibility/v1", "rows": [asdict(row) for row in rows]}, ensure_ascii=False, indent=2, allow_nan=True) + "\n", encoding="utf-8")
    args.output.with_suffix(".md").write_text(markdown(rows), encoding="utf-8")
    print(f"已写入：{args.output}")
    print(f"已写入：{args.output.with_suffix('.md')}")


if __name__ == "__main__":
    main()
