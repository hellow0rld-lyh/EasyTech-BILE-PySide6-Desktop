"""批量验证征2 Spine 4.1.x animations 段；严格只读且要求全文件消费。"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from bile_workbench.spine38_format import Spine38FormatError
from bile_workbench.spine41_timeline import parse_spine41_animations


def inspect(path: Path, root: Path) -> dict:
    try:
        archive = parse_spine41_animations(path)
        kinds = Counter(f"{timeline.group}:{timeline.kind}" for animation in archive.animations for timeline in animation.timelines)
        return {
            "path": str(path.relative_to(root)), "status": "PASS", "version": archive.static.header.version,
            "animation_start": archive.animation_start, "animation_end": archive.animation_end,
            "animations": [asdict(item) for item in archive.animations], "timeline_type_counts": dict(kinds),
            "event_definition_count": len(archive.event_names),
        }
    except (Spine38FormatError, OSError) as exc:
        return {"path": str(path.relative_to(root)), "status": "REJECT", "detail": str(exc)}


def markdown(rows: list[dict]) -> str:
    passed = [row for row in rows if row["status"] == "PASS"]
    versions = Counter(row["version"] for row in passed)
    kinds = Counter(item for row in passed for item, count in row["timeline_type_counts"].items() for _ in range(count))
    lines = [
        "# 征2 Spine 4.1 animations 段：批量严格验证", "",
        "> `PASS` 表示每份 BIN 都从 skins 结束后的 event definitions 继续，按其 4.1 版本的 slot、bone、constraint、attachment、draw-order 和 event 顺序读到文件末尾。未知类型、索引越界、时间倒退和尾部残留均会被拒绝；工具不写回任何 BIN。", "",
        "| 指标 | 数值 |", "|---|---:|", f"| BIN | {len(rows)} |", f"| 全动画段严格通过 | {len(passed)} |", f"| 拒绝 | {len(rows) - len(passed)} |", f"| 版本 | `{json.dumps(dict(versions), ensure_ascii=False)}` |", f"| 动画根总数 | {sum(len(row['animations']) for row in passed)} |", f"| 时间线总数 | {sum(sum(row['timeline_type_counts'].values()) for row in passed)} |", f"| 时间线类型 | `{json.dumps(dict(kinds), ensure_ascii=False, sort_keys=True)}` |", "",
        "| 文件 | 版本 | 动画根 | 时间线 | 事件定义 | 动画段起点 | 动画段终点 | 结果 |", "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        if row["status"] == "PASS":
            lines.append(f"| `{row['path']}` | {row['version']} | {len(row['animations'])} | {sum(row['timeline_type_counts'].values())} | {row['event_definition_count']} | {row['animation_start']} | {row['animation_end']} | PASS |")
        else:
            lines.append(f"| `{row['path']}` | — | — | — | — | — | — | REJECT: {row['detail']} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("zheng2_dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = [inspect(path, args.root) for path in sorted(args.zheng2_dir.rglob("*.bin"))]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"schema": "easytech-zheng2-spine41-animation/v1", "samples": rows}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.output.with_suffix(".md").write_text(markdown(rows), encoding="utf-8")
    print(f"已写入：{args.output}")
    print(f"已写入：{args.output.with_suffix('.md')}")


if __name__ == "__main__":
    main()
