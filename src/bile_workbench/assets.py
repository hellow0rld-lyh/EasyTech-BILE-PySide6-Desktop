"""BILE 三件套的文件身份与无副作用暂存工具。

所有函数只读取源资源，或向调用者明确给出的临时/输出目录写入副本；从不写入游戏目录。
"""
from __future__ import annotations

import hashlib
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path


class AssetTripletError(ValueError):
    """BIN/XML/图集三件套不完整或目标命名不安全。"""


@dataclass(frozen=True)
class AssetTriplet:
    bin_path: Path
    xml_path: Path
    image_path: Path

    def require_files(self) -> None:
        missing = [str(path) for path in (self.bin_path, self.xml_path, self.image_path) if not path.is_file()]
        if missing:
            raise FileNotFoundError("三件套文件不完整：" + "；".join(missing))

    @property
    def stem(self) -> str:
        return self.bin_path.stem

    @property
    def bin_sha256(self) -> str:
        return sha256_file(self.bin_path)

    @property
    def xml_sha256(self) -> str:
        return sha256_file(self.xml_path)

    @property
    def image_sha256(self) -> str:
        return sha256_file(self.image_path)


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def discover_triplet(bin_path: str | Path) -> AssetTriplet:
    """按 BIN 同名基名发现 XML 和 WebP/PNG 图集；WebP 优先以保持现有行为。"""
    binary = Path(bin_path)
    stem = binary.with_suffix("")
    xml = stem.with_suffix(".xml")
    image = next((candidate for candidate in (stem.with_suffix(".webp"), stem.with_suffix(".png")) if candidate.is_file()), None)
    if image is None:
        raise AssetTripletError(f"未找到与 {binary.name} 同名的 WebP/PNG 图集")
    triplet = AssetTriplet(binary, xml, image)
    triplet.require_files()
    return triplet


def create_triplet(bin_path: str | Path, xml_path: str | Path, image_path: str | Path) -> AssetTriplet:
    triplet = AssetTriplet(Path(bin_path), Path(xml_path), Path(image_path))
    triplet.require_files()
    return triplet


def _safe_name(name: str, kind: str) -> str:
    candidate = Path(name)
    if not name or candidate.name != name or name in {".", ".."}:
        raise AssetTripletError(f"{kind} 目标文件名必须是单个安全文件名")
    return name


def stage_triplet(
    source: AssetTriplet,
    destination_dir: str | Path,
    *,
    bin_name: str | None = None,
    xml_name: str | None = None,
    image_name: str | None = None,
    xml_bytes: bytes | None = None,
) -> AssetTriplet:
    """将三件套复制到明确目录；可替换 XML 副本字节，其余内容保持按元数据复制。"""
    source.require_files()
    destination = Path(destination_dir)
    destination.mkdir(parents=True, exist_ok=True)
    target = AssetTriplet(
        destination / _safe_name(bin_name or source.bin_path.name, "BIN"),
        destination / _safe_name(xml_name or source.xml_path.name, "XML"),
        destination / _safe_name(image_name or source.image_path.name, "图集"),
    )
    shutil.copy2(source.bin_path, target.bin_path)
    if xml_bytes is None:
        shutil.copy2(source.xml_path, target.xml_path)
    else:
        target.xml_path.write_bytes(xml_bytes)
    shutil.copy2(source.image_path, target.image_path)
    return target


def archive_tree(source_root: str | Path, archive_path: str | Path) -> Path:
    """将目录按父目录相对路径压缩；调用方决定根目录名，函数不读取目录外文件。"""
    root = Path(source_root)
    output = Path(archive_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(root.rglob("*")):
            if file.is_file():
                archive.write(file, file.relative_to(root.parent))
    return output
