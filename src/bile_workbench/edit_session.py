"""工作台内直接编辑的保守会话层。

会话始终以原 BIN 为基线；每次预览都会将完整待提交补丁应用到临时副本并重新解析。
新生成的补丁同时携带 expected-old 字段值，防止索引或编辑意图错位。
"""
from __future__ import annotations

import hashlib
import json
import math
import tempfile
from pathlib import Path
from typing import Any

from .bile_format import BileDocument, parse_bytes
from .interchange import SCHEMA, apply_patch


class EditSession:
    def __init__(self, source_path: str | Path) -> None:
        self.source_path = Path(source_path)
        source_bytes = self.source_path.read_bytes()
        self.source_sha256 = hashlib.sha256(source_bytes).hexdigest()
        self._source_document = parse_bytes(source_bytes)
        self._keyframes: dict[int, dict[str, Any]] = {}
        self._elements: dict[int, dict[str, Any]] = {}
        self._undo: list[tuple[dict[int, dict[str, Any]], dict[int, dict[str, Any]]]] = []
        self._redo: list[tuple[dict[int, dict[str, Any]], dict[int, dict[str, Any]]]] = []
        self._tempdir = tempfile.TemporaryDirectory(prefix="bile-workbench-")

    @property
    def dirty(self) -> bool:
        return bool(self._keyframes or self._elements)

    @property
    def change_count(self) -> int:
        return len(self._keyframes) + len(self._elements)

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def _snapshot(self) -> tuple[dict[int, dict[str, Any]], dict[int, dict[str, Any]]]:
        return (
            {index: dict(value) for index, value in self._keyframes.items()},
            {index: dict(value) for index, value in self._elements.items()},
        )

    def _restore(self, snapshot: tuple[dict[int, dict[str, Any]], dict[int, dict[str, Any]]]) -> None:
        self._keyframes = {index: dict(value) for index, value in snapshot[0].items()}
        self._elements = {index: dict(value) for index, value in snapshot[1].items()}

    def _record_change(self) -> None:
        self._undo.append(self._snapshot())
        self._redo.clear()

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(self._snapshot())
        self._restore(self._undo.pop())
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(self._snapshot())
        self._restore(self._redo.pop())
        return True

    def patch_payload(self) -> dict[str, Any]:
        keyframes: list[dict[str, Any]] = []
        for index, change in sorted(self._keyframes.items()):
            keyframe = self._source_document.keyframes[index]
            expected: dict[str, Any] = {}
            if "transform" in change:
                expected["transform"] = {
                    field: getattr(keyframe, field)
                    for field in change["transform"]
                }
            if "argb" in change:
                expected["argb"] = f"0x{keyframe.argb:08X}"
            if "initial_phase" in change:
                expected["initial_phase"] = keyframe.initial_phase
            keyframes.append({
                **{"index": index},
                **change,
                "expected": expected,
            })

        elements: list[dict[str, Any]] = []
        for index, change in sorted(self._elements.items()):
            element = self._source_document.elements[index]
            expected: dict[str, Any] = {}
            if "anchor" in change:
                expected["anchor"] = [element.x, element.y]
            if "name" in change:
                expected["name"] = element.name
            elements.append({
                **{"index": index},
                **change,
                "expected": expected,
            })

        return {
            "schema": SCHEMA,
            "kind": "patch",
            "source_sha256": self.source_sha256,
            "keyframes": keyframes,
            "elements": elements,
        }

    def set_keyframe(self, index: int, transform: dict[str, float], argb: int, initial_phase: int) -> None:
        if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(self._source_document.keyframes):
            raise ValueError(f"keyframe index 无效：{index}")
        if not isinstance(transform, dict):
            raise ValueError("transform 必须是对象")
        unknown_transform = set(transform) - {"xx", "xy", "yx", "yy", "x", "y"}
        if unknown_transform:
            raise ValueError(f"transform 包含不允许的字段：{sorted(unknown_transform)}")
        if not isinstance(argb, int) or isinstance(argb, bool) or not 0 <= argb <= 0xFFFFFFFF:
            raise ValueError("argb 必须是 u32 整数")
        if not isinstance(initial_phase, int) or isinstance(initial_phase, bool) or not 0 <= initial_phase <= 0xFFFFFFFF:
            raise ValueError("initial_phase 必须是 u32 整数")
        self._record_change()
        self._keyframes[index] = {
            "transform": dict(transform),
            "argb": f"0x{argb:08X}",
            "initial_phase": initial_phase,
        }

    def set_anchor(self, index: int, x: float, y: float) -> None:
        if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(self._source_document.elements):
            raise ValueError(f"element index 无效：{index}")
        if (
            not isinstance(x, (int, float)) or isinstance(x, bool)
            or not isinstance(y, (int, float)) or isinstance(y, bool)
        ):
            raise ValueError("anchor x/y 必须是有限数字")
        try:
            x_value, y_value = float(x), float(y)
        except (OverflowError, ValueError) as exc:
            raise ValueError("anchor x/y 必须是有限数字") from exc
        if not math.isfinite(x_value) or not math.isfinite(y_value):
            raise ValueError("anchor x/y 必须是有限数字")
        self._record_change()
        self._elements[index] = {"anchor": [x_value, y_value]}

    def clear(self) -> None:
        if self.dirty:
            self._record_change()
        self._keyframes.clear()
        self._elements.clear()

    def write_patch(self, output_path: str | Path) -> None:
        Path(output_path).write_text(
            json.dumps(self.patch_payload(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def write_candidate(
        self,
        output_path: str | Path,
        *,
        overwrite: bool = False,
    ) -> BileDocument:
        """将当前暂存补丁另存为候选 BIN；默认拒绝覆盖既有文件。"""
        patch_path = Path(self._tempdir.name) / "pending_patch.json"
        self.write_patch(patch_path)
        return apply_patch(
            self.source_path, patch_path, output_path, overwrite=overwrite
        )

    def preview_document(self) -> BileDocument:
        output_path = Path(self._tempdir.name) / "preview.bin"
        return self.write_candidate(output_path, overwrite=True)

    def close(self) -> None:
        self._tempdir.cleanup()
