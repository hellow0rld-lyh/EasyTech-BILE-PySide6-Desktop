"""欧7 Spine 3.8 的 animations 段入口探针；不解析或修改时间线。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from bile_workbench.spine38_format import Spine38FormatError, _Reader, parse_file


def probe(path: Path) -> dict:
    static = parse_file(path)
    data = path.read_bytes()
    reader = _Reader(data)
    reader.offset = static.static_end
    event_count = reader.varint("events.count")
    events = []
    for index in range(event_count):
        name = reader.ref_string(static.shared_strings, f"events[{index}].name")
        value = reader.varint(f"events[{index}].int", positive=False)
        number = reader.f32(f"events[{index}].float")
        text = reader.string(f"events[{index}].string")
        audio = reader.string(f"events[{index}].audio")
        if audio is not None:
            reader.f32(f"events[{index}].volume")
            reader.f32(f"events[{index}].balance")
        events.append({"name": name, "int": value, "float": number, "string": text, "audio": audio})
    animation_count = reader.varint("animations.count")
    return {
        "file": str(path),
        "static_end": static.static_end,
        "events_end": reader.offset,
        "event_count": event_count,
        "events": events,
        "animation_count": animation_count,
        "animation_start": reader.offset,
        "tail_bytes": len(data) - reader.offset,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("file", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = probe(args.file)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
