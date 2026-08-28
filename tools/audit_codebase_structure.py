#!/usr/bin/env python3
"""无副作用的 BILE Workbench 静态结构审计。"""
from __future__ import annotations

import ast
import json
import sys
from collections import Counter
from dataclasses import dataclass, asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "bile_workbench"
OUTPUT = ROOT / "research"


@dataclass
class FunctionMetric:
    name: str
    line_start: int
    line_end: int
    lines: int
    branches: int
    nesting: int


@dataclass
class ModuleMetric:
    module: str
    lines: int
    classes: int
    functions: int
    imports_internal: list[str]
    incoming_internal: int
    functions_over_30_lines: list[FunctionMetric]
    largest_functions: list[FunctionMetric]
    class_methods: dict[str, int]
    risk_score: int


def _function_metric(node: ast.FunctionDef | ast.AsyncFunctionDef) -> FunctionMetric:
    branches = 0
    max_nesting = 0

    def visit(current: ast.AST, depth: int = 0) -> None:
        nonlocal branches, max_nesting
        if isinstance(current, (ast.If, ast.For, ast.While, ast.Try, ast.Match, ast.With, ast.BoolOp, ast.comprehension)):
            branches += 1
            depth += 1
            max_nesting = max(max_nesting, depth)
        for child in ast.iter_child_nodes(current):
            visit(child, depth)

    visit(node)
    end = getattr(node, "end_lineno", node.lineno)
    return FunctionMetric(node.name, node.lineno, end, end - node.lineno + 1, branches, max_nesting)


def _internal_imports(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module:
            names.add(node.module.split(".")[0])
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("bile_workbench."):
                    names.add(alias.name.split(".")[1])
    return names


def analyze() -> list[ModuleMetric]:
    raw: dict[str, tuple[Path, ast.Module, list[str]]] = {}
    imports: dict[str, set[str]] = {}
    for path in sorted(SRC.glob("*.py")):
        if path.name == "__init__.py":
            continue
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        name = path.stem
        raw[name] = (path, tree, source.splitlines())
        imports[name] = _internal_imports(tree)
    incoming = Counter(target for targets in imports.values() for target in targets)
    metrics: list[ModuleMetric] = []
    for name, (_path, tree, lines) in raw.items():
        functions: list[FunctionMetric] = []
        class_methods: dict[str, int] = {}
        class_count = 0
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(_function_metric(node))
            elif isinstance(node, ast.ClassDef):
                class_count += 1
                methods = [_function_metric(child) for child in node.body if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))]
                functions.extend(methods)
                class_methods[node.name] = len(methods)
        largest = sorted(functions, key=lambda item: (-item.lines, item.name))[:8]
        long = sorted((item for item in functions if item.lines > 30), key=lambda item: (-item.lines, item.name))
        risk = len(lines) // 100 + len(long) * 2 + max(0, len(imports[name]) - 4) + max(0, incoming[name] - 4)
        metrics.append(ModuleMetric(name, len(lines), class_count, len(functions), sorted(imports[name]), incoming[name], long, largest, class_methods, risk))
    return sorted(metrics, key=lambda item: (-item.risk_score, -item.lines, item.module))


def report(metrics: list[ModuleMetric]) -> str:
    total_lines = sum(item.lines for item in metrics)
    long_functions = sum(len(item.functions_over_30_lines) for item in metrics)
    lines = [
        "# BILE Workbench 静态结构审计",
        "",
        f"- 源模块：{len(metrics)} 个",
        f"- 源代码行：{total_lines}",
        f"- 超过 30 行的函数/方法：{long_functions}",
        "",
        "> 该审计使用 Python AST，指标用于确定重构优先级，并不把‘行数多’直接等同于缺陷。优先处理同时具备高耦合、长方法和多职责的模块。",
        "",
        "| 模块 | 行数 | 类 | 函数/方法 | 内部传出依赖 | 内部传入依赖 | >30 行函数 | 风险分 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in metrics:
        lines.append(f"| `{item.module}` | {item.lines} | {item.classes} | {item.functions} | {len(item.imports_internal)} | {item.incoming_internal} | {len(item.functions_over_30_lines)} | {item.risk_score} |")
    lines.extend(["", "## 候选拆分点", ""])
    for item in metrics[:8]:
        candidates = ", ".join(f"`{function.name}` {function.lines} 行" for function in item.largest_functions[:4]) or "无"
        dependencies = ", ".join(f"`{name}`" for name in item.imports_internal) or "无"
        lines.extend([
            f"### `{item.module}`",
            "",
            f"该模块的内部依赖：{dependencies}。最长职责块：{candidates}。建议先以兼容外观接口为边界抽取协作对象，再迁移调用点；避免在同一变更中同时改变格式语义和 UI 行为。",
            "",
        ])
    return "\n".join(lines)


def main() -> int:
    OUTPUT.mkdir(exist_ok=True)
    metrics = analyze()
    (OUTPUT / "codebase_structure_audit.json").write_text(json.dumps([asdict(item) for item in metrics], ensure_ascii=False, indent=2), encoding="utf-8")
    (OUTPUT / "codebase_structure_audit.md").write_text(report(metrics), encoding="utf-8")
    print(OUTPUT / "codebase_structure_audit.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
