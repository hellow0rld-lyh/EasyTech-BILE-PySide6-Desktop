"""批量验证征2封装内 Spine 4.1.x 静态载荷读取；严格只读。"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from bile_workbench.spine38_format import Spine38FormatError
from bile_workbench.spine41_format import parse_file


def inspect(path: Path, root: Path) -> dict:
    try:
        document = parse_file(path)
        return {
            "path": str(path.relative_to(root)), "status": "PASS", "version": document.header.version,
            "bones": len(document.bones), "slots": len(document.slots), "skins": len(document.skin_names),
            "regions": len(document.region_attachments), "ik": document.ik_constraint_count,
            "transform": document.transform_constraint_count, "path_constraints": document.path_constraint_count,
            "static_end": document.static_end, "undecoded_tail": document.undecoded_tail_bytes,
        }
    except (Spine38FormatError, OSError) as exc:
        return {"path": str(path.relative_to(root)), "status": "REJECT", "detail": str(exc)}


def markdown(rows: list[dict]) -> str:
    passed = [row for row in rows if row["status"] == "PASS"]
    versions = Counter(row["version"] for row in passed)
    lines = [
        "# 征2封装内 Spine 4.1 静态载荷：批量严格验证", "",
        "> 每份 BIN 均先按 8 字节 `long hash` 前缀读取，再按官方 4.1 静态骨架顺序读取到 skins 结束。`PASS` 不表示 events/animations 已解码或文件可写回。",
        "", "| 指标 | 数值 |", "|---|---:|", f"| BIN | {len(rows)} |", f"| 静态区严格通过 | {len(passed)} |", f"| 拒绝 | {len(rows) - len(passed)} |", f"| 版本 | `{json.dumps(dict(versions), ensure_ascii=False)}` |", "",
        "| 文件 | 版本 | 骨骼 | 插槽 | 皮肤 | 区域附件 | IK / Transform / Path | 静态区末尾 | 未解码尾部 | 结果 |", "|---|---|---:|---:|---:|---:|---|---:|---:|---|",
    ]
    for row in rows:
        if row["status"] == "PASS":
            lines.append(f"| `{row['path']}` | {row['version']} | {row['bones']} | {row['slots']} | {row['skins']} | {row['regions']} | {row['ik']} / {row['transform']} / {row['path_constraints']} | {row['static_end']} | {row['undecoded_tail']} | PASS |")
        else:
            lines.append(f"| `{row['path']}` | — | — | — | — | — | — | — | — | REJECT: {row['detail']} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("zheng2_dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = [inspect(path, args.root) for path in sorted(args.zheng2_dir.rglob("*.bin"))]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"schema": "easytech-zheng2-spine41-static/v1", "samples": rows}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.output.with_suffix(".md").write_text(markdown(rows), encoding="utf-8")
    print(f"已写入：{args.output}")
    print(f"已写入：{args.output.with_suffix('.md')}")


if __name__ == "__main__":
    main()
