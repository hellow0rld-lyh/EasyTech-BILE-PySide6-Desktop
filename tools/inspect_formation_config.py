#!/usr/bin/env python3
"""只读审计 def_array 风格阵列 XML；可选比较基线与候选配置。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bile_workbench.formation_config import diff_formation_configs, parse_def_array, summarize_formation_config


def markdown_summary(summary: dict, diff: dict | None) -> str:
    lines = [
        "# 上层阵列配置只读审计",
        "",
        f"- 文件：`{summary['source']['file']}`",
        f"- SHA-256：`{summary['source']['sha256']}`",
        f"- Array 数：{len(summary['arrays'])}",
        "",
        "| Array | 声明数 | 行 | primary 坐标数（各行） | special 坐标数（各行） |",
        "|---|---:|---:|---|---|",
    ]
    for array in summary["arrays"]:
        rows = array["rows"]
        primary = ", ".join(str(row["primary_count"]) for row in rows) or "—"
        special = ", ".join(str(row["special_count"]) for row in rows) or "—"
        lines.append(f"| `{array['name']}` | {array['declared_count'] if array['declared_count'] is not None else '—'} | {len(rows)} | {primary} | {special} |")
    lines.extend(["", "## 读取边界", "", "> 本报告只描述 Array/Pos 坐标表结构，不推断 Army/Unit 到 Array 的运行时选择关系，也不修改 XML。"])
    if summary["warnings"]:
        lines.extend(["", "## 结构警告", ""])
        lines.extend(f"- {warning}" for warning in summary["warnings"])
    if diff is not None:
        lines.extend(["", "## 与候选配置的差异", "", "| Array | 行 | 变量 | 基线 | 候选 |", "|---|---:|---|---|---|"])
        if diff["changes"]:
            for change in diff["changes"]:
                lines.append(f"| `{change['array']}` | {change.get('row', '—')} | {change['kind']} | {change.get('before', '—')} | {change.get('after', '—')} |")
        else:
            lines.append("| — | — | 无结构差异 | — | — |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="只读审计 def_array 风格阵列配置")
    parser.add_argument("baseline", type=Path, help="基线 def_array XML")
    parser.add_argument("--candidate", type=Path, help="可选候选 def_array XML；仅生成差异，不写回")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "research", help="输出目录")
    arguments = parser.parse_args()
    baseline = parse_def_array(arguments.baseline)
    summary = summarize_formation_config(baseline)
    candidate = parse_def_array(arguments.candidate) if arguments.candidate else None
    diff = diff_formation_configs(baseline, candidate) if candidate else None
    arguments.output_dir.mkdir(parents=True, exist_ok=True)
    stem = arguments.baseline.stem
    json_path = arguments.output_dir / f"{stem}_formation_audit.json"
    markdown_path = arguments.output_dir / f"{stem}_formation_audit.md"
    json_path.write_text(json.dumps({"summary": summary, "diff": diff}, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(markdown_summary(summary, diff), encoding="utf-8")
    print(json_path)
    print(markdown_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
