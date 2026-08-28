"""征2与欧7动画资源的只读格式审计；不尝试写入或解码未知容器。"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

VERSION_RE = re.compile(rb"(?:spine[-_ ]?)?(\d+\.\d+(?:\.\d+)?)", re.IGNORECASE)
PRINTABLE_RE = re.compile(rb"[ -~]{4,}")


def compact_signature(data: bytes) -> str:
    prefix = data[:16]
    printable = "".join(chr(byte) if 32 <= byte < 127 else "." for byte in prefix)
    return f"{prefix.hex()} | {printable}"


def strings(data: bytes, limit: int = 20) -> list[str]:
    decoded = []
    for match in PRINTABLE_RE.finditer(data):
        text = match.group().decode("ascii", errors="replace")
        if any(token in text.lower() for token in ("spine", "images/", ".png", ".webp", "skeleton", "animation")) or re.fullmatch(r"\d+\.\d+(?:\.\d+)?", text):
            decoded.append(text)
        if len(decoded) >= limit:
            break
    return decoded


def atlas_profile(path: Path) -> dict:
    raw = path.read_bytes()
    text = raw.decode("utf-8", errors="replace").replace("\r\n", "\n")
    lines = [line.rstrip() for line in text.split("\n") if line.strip()]
    keys = Counter(line.split(":", 1)[0].strip() for line in lines if ":" in line)
    return {
        "path": str(path),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "first_lines": lines[:16],
        "keys": dict(sorted(keys.items())),
        "contains_pma": any(line.startswith("pma:") for line in lines),
        "contains_bounds": any(line.startswith("bounds:") for line in lines),
    }


def bin_profile(path: Path, root: Path) -> dict:
    data = path.read_bytes()
    versions = sorted({match.group(1).decode("ascii") for match in VERSION_RE.finditer(data)})
    atlas = path.with_suffix(".atlas")
    image = next((path.with_suffix(ext) for ext in (".png", ".webp") if path.with_suffix(ext).exists()), None)
    return {
        "path": str(path.relative_to(root)),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "signature": compact_signature(data),
        "spine_versions": versions,
        "string_clues": strings(data),
        "has_atlas": atlas.exists(),
        "image": str(image.relative_to(root)) if image else None,
        "atlas_profile": atlas_profile(atlas) if atlas.exists() else None,
    }


def summarize(name: str, folder: Path, root: Path) -> dict:
    profiles = [bin_profile(path, root) for path in sorted(folder.rglob("*.bin"))]
    signatures = Counter(profile["signature"] for profile in profiles)
    versions = Counter(version for profile in profiles for version in profile["spine_versions"])
    with_atlas = sum(profile["has_atlas"] for profile in profiles)
    with_triplet = sum(profile["has_atlas"] and profile["image"] is not None for profile in profiles)
    groups: dict[str, list[str]] = defaultdict(list)
    for profile in profiles:
        groups[profile["signature"]].append(profile["path"])
    return {
        "name": name,
        "root": str(folder.relative_to(root)),
        "bin_count": len(profiles),
        "with_atlas": with_atlas,
        "with_complete_triplet": with_triplet,
        "spine_versions": dict(versions),
        "signature_groups": [{"signature": signature, "count": count, "examples": groups[signature][:8]} for signature, count in signatures.most_common()],
        "profiles": profiles,
    }


def markdown(report: dict) -> str:
    lines = ["# 征2 / 欧7新引擎候选：只读资源审计", "", "> 本报告只记录外层签名、可见字符串与 ATLAS 元数据。版本字符串或 Spine 路径仅作为研究线索，不证明整份 BIN 已经是标准 Spine 二进制。", ""]
    for dataset in report["datasets"]:
        lines.extend([f"## {dataset['name']}", "", "| 指标 | 值 |", "|---|---:|", f"| BIN | {dataset['bin_count']} |", f"| 同名 ATLAS | {dataset['with_atlas']} |", f"| 完整 BIN + ATLAS + 图像 | {dataset['with_complete_triplet']} |", f"| 检出的版本字符串 | `{json.dumps(dataset['spine_versions'], ensure_ascii=False)}` |", "", "### 外层签名组", "", "| 签名 | 数量 | 示例 |", "|---|---:|---|"])
        for group in dataset["signature_groups"]:
            examples = "<br>".join(f"`{entry}`" for entry in group["examples"][:3])
            lines.append(f"| `{group['signature']}` | {group['count']} | {examples} |")
        lines.extend(["", "### 含 ATLAS 的代表候选", "", "| BIN | 版本线索 | 图像 | ATLAS 键 |", "|---|---|---|---|"])
        for profile in (item for item in dataset["profiles"] if item["has_atlas"]):
            atlas_keys = ", ".join(profile["atlas_profile"]["keys"].keys())
            lines.append(f"| `{profile['path']}` | `{', '.join(profile['spine_versions']) or '—'}` | `{profile['image'] or '缺失'}` | `{atlas_keys}` |")
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--zheng2", type=Path, required=True)
    parser.add_argument("--eu7", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = {
        "schema": "easytech-new-engine-audit/v1",
        "datasets": [summarize("征2", args.zheng2, args.root), summarize("欧7", args.eu7, args.root)],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.output.with_suffix(".md").write_text(markdown(report), encoding="utf-8")
    print(f"已写入：{args.output}")
    print(f"已写入：{args.output.with_suffix('.md')}")


if __name__ == "__main__":
    main()
