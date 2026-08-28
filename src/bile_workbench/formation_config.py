"""可选上层阵列配置（def_array 风格 XML）的只读解析与差异摘要。

该模块不推断任何游戏必然采用某个阵列，也不写回配置文件；它只把用户提供的 Array/Pos 坐标表
转换为可审计结构。实际 Army/Unit 到 Array 的选择关系仍需游戏内或二进制证据确认。
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .xml_safety import SafeXmlError, parse_untrusted_xml


class FormationConfigError(ValueError):
    """上层阵列 XML 不满足最小只读结构约束。"""


@dataclass(frozen=True)
class FormationPoint:
    x: float
    y: float


@dataclass(frozen=True)
class FormationRow:
    index: int
    primary: tuple[FormationPoint, ...]
    special: tuple[FormationPoint, ...]
    raw_attributes: tuple[tuple[str, str], ...]

    @property
    def special_has_unique_child_shape(self) -> bool | None:
        """special 缺失时返回 None；否则只报告“primary + 一个坐标”的形状，不赋运行时语义。"""
        if not self.special:
            return None
        return len(self.special) == len(self.primary) + 1


@dataclass(frozen=True)
class FormationArray:
    index: int
    name: str
    declared_count: int | None
    rows: tuple[FormationRow, ...]
    raw_attributes: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class FormationConfig:
    source_name: str
    source_sha256: str
    arrays: tuple[FormationArray, ...]
    warnings: tuple[str, ...]

    @property
    def by_name(self) -> dict[str, FormationArray]:
        return {item.name: item for item in self.arrays}


def _parse_coordinate_pairs(raw: str | None, label: str) -> tuple[FormationPoint, ...]:
    if raw is None or not raw.strip():
        return ()
    values = [part.strip() for part in raw.split(",")]
    if any(not part for part in values) or len(values) % 2:
        raise FormationConfigError(f"{label} 必须是偶数个逗号分隔坐标值")
    try:
        numeric = [float(part) for part in values]
    except ValueError as exc:
        raise FormationConfigError(f"{label} 包含无法读取的浮点坐标") from exc
    return tuple(FormationPoint(numeric[index], numeric[index + 1]) for index in range(0, len(numeric), 2))


def _parse_declared_count(raw: str | None, name: str) -> int | None:
    if raw is None or not raw.strip():
        return None
    try:
        value = int(raw, 10)
    except ValueError as exc:
        raise FormationConfigError(f"Array '{name}' 的 n 属性不是整数") from exc
    if value < 0:
        raise FormationConfigError(f"Array '{name}' 的 n 属性不能为负数")
    return value


def parse_def_array_bytes(data: bytes, source_name: str = "def_array.xml") -> FormationConfig:
    """解析 def_array 风格 XML；只接受 Array 下的 Pos 坐标表，不修改输入字节。"""
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise FormationConfigError("阵列配置必须是 UTF-8 文本") from exc
    try:
        root = parse_untrusted_xml(text, source_name)
    except SafeXmlError as exc:
        raise FormationConfigError(f"阵列配置 XML 无法解析：{exc}") from exc

    arrays: list[FormationArray] = []
    warnings: list[str] = []
    seen_names: set[str] = set()
    for array_index, element in enumerate(root.findall("Array")):
        name = (element.get("name") or "").strip()
        if not name:
            raise FormationConfigError(f"Array[{array_index}] 缺少 name")
        if name in seen_names:
            raise FormationConfigError(f"Array 名称重复：{name}")
        seen_names.add(name)
        declared_count = _parse_declared_count(element.get("n"), name)
        rows: list[FormationRow] = []
        for row_index, position in enumerate(element.findall("Pos")):
            primary = _parse_coordinate_pairs(position.get("soldier"), f"Array '{name}' Pos[{row_index}].soldier")
            special = _parse_coordinate_pairs(position.get("special"), f"Array '{name}' Pos[{row_index}].special")
            if special and len(special) != len(primary) + 1:
                warnings.append(
                    f"Array '{name}' Pos[{row_index}] 的 special 坐标数为 {len(special)}，不是 primary 坐标数 {len(primary)} 加一；只保留结构，不推断 special 规则。"
                )
            rows.append(FormationRow(row_index, primary, special, tuple(sorted(position.attrib.items()))))
        if not rows:
            warnings.append(f"Array '{name}' 不含 Pos 行。")
        arrays.append(FormationArray(array_index, name, declared_count, tuple(rows), tuple(sorted(element.attrib.items()))))
    if not arrays:
        raise FormationConfigError("未发现任何直接 Array 节点；这不是当前支持的 def_array 风格配置")
    return FormationConfig(source_name, hashlib.sha256(data).hexdigest(), tuple(arrays), tuple(warnings))


def parse_def_array(path: str | Path) -> FormationConfig:
    source = Path(path)
    return parse_def_array_bytes(source.read_bytes(), source.name)


def _point_text(points: tuple[FormationPoint, ...]) -> str:
    return ";".join(f"{point.x:g},{point.y:g}" for point in points)


def summarize_formation_config(config: FormationConfig) -> dict:
    return {
        "schema": "bile-workbench.formation-config/v1",
        "source": {"file": config.source_name, "sha256": config.source_sha256},
        "arrays": [
            {
                "index": array.index,
                "name": array.name,
                "declared_count": array.declared_count,
                "rows": [
                    {
                        "index": row.index,
                        "primary_count": len(row.primary),
                        "special_count": len(row.special),
                        "special_has_unique_child_shape": row.special_has_unique_child_shape,
                        "primary_coordinates": _point_text(row.primary),
                        "special_coordinates": _point_text(row.special),
                    }
                    for row in array.rows
                ],
            }
            for array in config.arrays
        ],
        "warnings": list(config.warnings),
        "contract": "只读阵列结构摘要；不推断 Army/Unit 到 Array 的运行时选择关系，不修改源 XML。",
    }


def diff_formation_configs(baseline: FormationConfig, candidate: FormationConfig) -> dict:
    """比较两份配置的 Array 与 Pos 坐标，不生成或应用任何补丁。"""
    baseline_by_name = baseline.by_name
    candidate_by_name = candidate.by_name
    changes: list[dict] = []
    for name in sorted(set(baseline_by_name) | set(candidate_by_name)):
        before = baseline_by_name.get(name)
        after = candidate_by_name.get(name)
        if before is None:
            changes.append({"array": name, "kind": "added_array"})
            continue
        if after is None:
            changes.append({"array": name, "kind": "removed_array"})
            continue
        if before.declared_count != after.declared_count:
            changes.append({"array": name, "kind": "declared_count", "before": before.declared_count, "after": after.declared_count})
        max_rows = max(len(before.rows), len(after.rows))
        for index in range(max_rows):
            old_row = before.rows[index] if index < len(before.rows) else None
            new_row = after.rows[index] if index < len(after.rows) else None
            if old_row is None or new_row is None:
                changes.append({"array": name, "row": index, "kind": "added_row" if old_row is None else "removed_row"})
                continue
            if old_row.primary != new_row.primary:
                changes.append({"array": name, "row": index, "kind": "primary_coordinates", "before": _point_text(old_row.primary), "after": _point_text(new_row.primary)})
            if old_row.special != new_row.special:
                changes.append({"array": name, "row": index, "kind": "special_coordinates", "before": _point_text(old_row.special), "after": _point_text(new_row.special)})
    return {
        "schema": "bile-workbench.formation-config-diff/v1",
        "baseline": {"file": baseline.source_name, "sha256": baseline.source_sha256},
        "candidate": {"file": candidate.source_name, "sha256": candidate.source_sha256},
        "changes": changes,
        "contract": "只读差异；生成实验前变量清单，不写入候选配置。",
    }
