"""输出少量 BILE v2 样本的 BMRF/BELE 原始记录对照；严格只读。"""
from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path

from bile_workbench.bile_format import _parse_header_and_sections


def parse_records(path: Path, limit: int) -> dict:
    data = path.read_bytes()
    header, sections = _parse_header_and_sections(data)
    if header.version != 2:
        raise ValueError(f"不是 BILE v2：{path}")
    bmrf = sections["BMRF"]
    bele = sections["BELE"]
    bmrf_rows = [
        {
            "index": index,
            "slot": struct.unpack_from("<I", bmrf.payload, index * 12)[0],
            "target": struct.unpack_from("<i", bmrf.payload, index * 12 + 4)[0],
            "constant": struct.unpack_from("<I", bmrf.payload, index * 12 + 8)[0],
        }
        for index in range(min(limit, bmrf.count))
    ]
    bele_rows = [
        {
            "index": index,
            "alpha": round(struct.unpack_from("<f", bele.payload, index * 48 + 24)[0], 5),
            "u28": struct.unpack_from("<I", bele.payload, index * 48 + 28)[0],
            "u32": struct.unpack_from("<I", bele.payload, index * 48 + 32)[0],
            "u36": struct.unpack_from("<I", bele.payload, index * 48 + 36)[0],
            "u40": struct.unpack_from("<I", bele.payload, index * 48 + 40)[0],
            "u44": struct.unpack_from("<i", bele.payload, index * 48 + 44)[0],
        }
        for index in range(min(limit, bele.count))
    ]
    return {"path": str(path), "bmrf_count": bmrf.count, "bele_count": bele.count, "bmrf": bmrf_rows, "bele": bele_rows}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = {"schema": "bile-workbench.v2-alignment-examples/v1", "examples": [parse_records(path, args.limit) for path in args.files]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# v2 BMRF / BELE 逐记录对照", "", "> 本文件显示原始记录，并不为字段命名或赋予写回语义。", ""]
    for example in payload["examples"]:
        lines.extend([f"## `{Path(example['path']).name}`", "", f"BMRF：{example['bmrf_count']}；BELE：{example['bele_count']}。", "", "| 序号 | BMRF slot | BMRF target | BELE u28 | BELE u44 | alpha |", "|---:|---:|---:|---:|---:|---:|"])
        rows = max(len(example["bmrf"]), len(example["bele"]))
        for index in range(rows):
            bmrf = example["bmrf"][index] if index < len(example["bmrf"]) else None
            bele = example["bele"][index] if index < len(example["bele"]) else None
            lines.append(f"| {index} | {bmrf['slot'] if bmrf else '—'} | {bmrf['target'] if bmrf else '—'} | {bele['u28'] if bele else '—'} | {bele['u44'] if bele else '—'} | {bele['alpha'] if bele else '—'} |")
        lines.append("")
    args.output.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"已写入：{args.output}")
    print(f"已写入：{args.output.with_suffix('.md')}")


if __name__ == "__main__":
    main()
