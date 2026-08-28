"""批量验证欧7 Spine 3.8.99 animations 段；严格只读且要求全文件消费。"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from bile_workbench.spine38_format import Spine38FormatError
from bile_workbench.spine38_timeline import parse_spine38_animations


def inspect(path: Path, root: Path) -> dict:
    try:
        archive = parse_spine38_animations(path)
        kinds = Counter(f"{timeline.group}:{timeline.kind}" for animation in archive.animations for timeline in animation.timelines)
        return {
            "path": str(path.relative_to(root)), "status": "PASS", "animation_start": archive.animation_start,
            "animation_end": archive.animation_end, "animations": [asdict(item) for item in archive.animations],
            "timeline_type_counts": dict(kinds), "event_definition_count": len(archive.event_names),
        }
    except (Spine38FormatError, OSError) as exc:
        return {"path": str(path.relative_to(root)), "status": "REJECT", "detail": str(exc)}


def markdown(rows: list[dict]) -> str:
    passed = [row for row in rows if row["status"] == "PASS"]
    aggregate = Counter(item for row in passed for item, count in row["timeline_type_counts"].items() for _ in range(count))
    animations = sum(len(row["animations"]) for row in passed)
    timelines = sum(sum(row["timeline_type_counts"].values()) for row in passed)
    lines = [
        "# 欧7 Spine 3.8 animations 段：批量严格验证", "",
        "> `PASS` 表示文件从静态区边界后的 event definitions 开始，到 animations 尾端全部累计消费完成；未知 timeline 类型、索引越界、帧时间倒退或尾部残留均会拒绝。此工具不产生写回物。", "",
        "| 指标 | 数值 |", "|---|---:|", f"| BIN | {len(rows)} |", f"| 全动画段严格通过 | {len(passed)} |", f"| 拒绝 | {len(rows) - len(passed)} |", f"| 动画根总数 | {animations} |", f"| 时间线总数 | {timelines} |", f"| 时间线类型 | `{json.dumps(dict(aggregate), ensure_ascii=False, sort_keys=True)}` |", "",
        "| 文件 | 动画根 | 时间线 | 事件定义 | 动画段起点 | 动画段终点 | 结果 |", "|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        if row["status"] == "PASS":
            lines.append(f"| `{row['path']}` | {len(row['animations'])} | {sum(row['timeline_type_counts'].values())} | {row['event_definition_count']} | {row['animation_start']} | {row['animation_end']} | PASS |")
        else:
            lines.append(f"| `{row['path']}` | — | — | — | — | — | REJECT: {row['detail']} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("eu7_dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = [inspect(path, args.root) for path in sorted(args.eu7_dir.rglob("*.bin"))]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"schema": "easytech-eu7-spine38-animation/v1", "samples": rows}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.output.with_suffix(".md").write_text(markdown(rows), encoding="utf-8")
    print(f"已写入：{args.output}")
    print(f"已写入：{args.output.with_suffix('.md')}")


if __name__ == "__main__":
    main()
