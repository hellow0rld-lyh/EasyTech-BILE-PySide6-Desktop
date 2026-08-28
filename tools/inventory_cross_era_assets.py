"""只读清点跨代 EasyTech 资源，绝不解析或修改未验证的二进制容器。"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class ContainerSample:
    path: str
    size: int
    magic_hex: str
    magic_text: str
    contains_spilt: bool


def printable(data: bytes) -> str:
    return "".join(chr(value) if 32 <= value <= 126 else "." for value in data)


def inventory_package(package: Path) -> dict:
    files = sorted(path for path in package.rglob("*") if path.is_file())
    by_extension: Counter[str] = Counter(path.suffix.lower() or "[none]" for path in files)
    by_stem: dict[str, set[str]] = defaultdict(set)
    for path in files:
        by_stem[str(path.with_suffix("").relative_to(package))].add(path.suffix.lower())
    bins = [path for path in files if path.suffix.lower() == ".bin"]
    samples: list[ContainerSample] = []
    for path in bins:
        prefix = path.read_bytes()[:64]
        samples.append(
            ContainerSample(
                path=str(path.relative_to(package)),
                size=path.stat().st_size,
                magic_hex=prefix[:16].hex(" "),
                magic_text=printable(prefix[:16]),
                contains_spilt=(b"SPILT" in prefix or b"SPLIT" in prefix),
            )
        )
    magic_counts = Counter(sample.magic_hex for sample in samples)
    bile_count = sum(sample.magic_text.startswith("BILE") for sample in samples)
    atlas_bin_pairs = sum(1 for suffixes in by_stem.values() if ".bin" in suffixes and ".atlas" in suffixes)
    xml_bin_pairs = sum(1 for suffixes in by_stem.values() if ".bin" in suffixes and ".xml" in suffixes)
    image_bin_pairs = sum(1 for suffixes in by_stem.values() if ".bin" in suffixes and suffixes.intersection({".png", ".webp"}))
    complete_legacy_triplets = sum(
        1 for suffixes in by_stem.values()
        if ".bin" in suffixes and ".xml" in suffixes and suffixes.intersection({".png", ".webp"})
    )
    return {
        "package": package.name,
        "file_count": len(files),
        "extension_counts": dict(sorted(by_extension.items())),
        "bin_count": len(bins),
        "bile_magic_count": bile_count,
        "xml_bin_pairs": xml_bin_pairs,
        "image_bin_pairs": image_bin_pairs,
        "complete_legacy_triplets": complete_legacy_triplets,
        "atlas_bin_pairs": atlas_bin_pairs,
        "magic_counts": dict(magic_counts.most_common()),
        "samples": [asdict(sample) for sample in samples],
    }


def markdown(payload: dict) -> str:
    lines = [
        "# EasyTech 跨代资源只读清点",
        "",
        "> 本报告仅基于文件名、扩展名、同名关联与 BIN 前 64 字节的魔数扫描。它不将同厂商资源自动判为 BILE，也不对新容器进行未经验证的解析。",
        "",
        "## 包概览",
        "",
        "| 资源包 | 文件 | BIN | `BILE` 魔数 | BIN+XML | BIN+图像 | 完整传统三件套 | BIN+ATLAS |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for package in payload["packages"]:
        lines.append(
            f"| {package['package']} | {package['file_count']} | {package['bin_count']} | {package['bile_magic_count']} | "
            f"{package['xml_bin_pairs']} | {package['image_bin_pairs']} | {package['complete_legacy_triplets']} | {package['atlas_bin_pairs']} |"
        )
    lines.extend(["", "## BIN 容器签名", ""])
    for package in payload["packages"]:
        lines.extend([f"### {package['package']}", "", "| 前 16 字节（十六进制） | 数量 |", "|---|---:|"])
        for magic, count in package["magic_counts"].items():
            lines.append(f"| `{magic}` | {count} |")
        if not package["magic_counts"]:
            lines.append("| — | 0 |")
        non_bile = [sample for sample in package["samples"] if not sample["magic_text"].startswith("BILE")]
        if non_bile:
            lines.extend(["", "非 BILE 示例（仅供后续格式分流，不代表已解析）：", ""])
            for sample in non_bile[:12]:
                lines.append(f"- `{sample['path']}` · {sample['size']} bytes · `{sample['magic_text']}`")
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    packages = [path for path in sorted(args.root.iterdir()) if path.is_dir()]
    payload = {
        "schema": "bile-workbench.cross-era-inventory/v1",
        "scope": "read-only filenames, file associations, extensions, and first-64-byte BIN signatures",
        "packages": [inventory_package(package) for package in packages],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.output.with_suffix(".md").write_text(markdown(payload), encoding="utf-8")
    print(f"已写入：{args.output}")
    print(f"已写入：{args.output.with_suffix('.md')}")


if __name__ == "__main__":
    main()
