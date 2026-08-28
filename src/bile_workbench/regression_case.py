"""候选动画的游戏内回归案例与外部证据登记。"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from .assets import sha256_file

CaseStatus = Literal["pending", "pass", "fail", "inconclusive"]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _case_file(case_dir: str | Path) -> Path:
    return Path(case_dir) / "case.json"


def _load(case_dir: str | Path) -> dict:
    path = _case_file(case_dir)
    if not path.exists():
        raise FileNotFoundError(f"未找到回归案例：{path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _write(case_dir: str | Path, payload: dict) -> Path:
    path = _case_file(case_dir)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def create_regression_case(
    case_dir: str | Path,
    original_bin: str | Path,
    candidate_bin: str | Path,
    animation: str,
    diff_report: str | Path | None = None,
    target_slots: list[int] | None = None,
    experiment_package: str | Path | None = None,
    experiment_context: dict | None = None,
) -> Path:
    """创建待游戏内验证的案例目录；不复制 BIN，报告引用明确的源文件与哈希。"""
    destination = Path(case_dir)
    destination.mkdir(parents=True, exist_ok=True)
    original = Path(original_bin)
    candidate = Path(candidate_bin)
    if not original.is_file() or not candidate.is_file():
        raise FileNotFoundError("创建案例前需要原始 BIN 与候选 BIN")
    candidate_copy = destination / "candidate.bin"
    shutil.copy2(candidate, candidate_copy)
    if target_slots is None:
        target_slots = []
    composition_steps = [
        {"id": "backup", "label": "备份目标游戏目录中的同名 BIN、XML、图集与 def_motion.xml", "done": False},
        {"id": "baseline", "label": "在固定 Army/地图/方向/阵列/镜头条件下记录基线截图或录屏", "done": False},
        {"id": "replace", "label": "替换组合实验包中的目标基名三件套", "done": False},
        {"id": "binding", "label": "仅按绑定配方修改指定 Motion.name，并登记修改后配置哈希", "done": False},
        {"id": "treatment", "label": "在与基线相同条件下记录处理组截图或录屏", "done": False},
        {"id": "restore", "label": "结束后恢复原始三件套与配置备份", "done": False},
    ]
    payload = {
        "schema": "bile-workbench.game-regression/v2" if experiment_context else "bile-workbench.game-regression/v1",
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
        "status": "pending",
        "animation": animation,
        "target_slots": sorted(set(int(slot) for slot in target_slots if int(slot) >= 0)),
        "original": {"file": str(original), "sha256": sha256_file(original)},
        "candidate": {"file": str(candidate_copy.relative_to(destination)), "source": str(candidate), "sha256": sha256_file(candidate_copy)},
        "diff_report": str(diff_report) if diff_report else None,
        "experiment_package": str(experiment_package) if experiment_package else None,
        "device": {"model": "", "os": "", "game_version": "", "resource_path": ""},
        "steps": composition_steps if experiment_context else [
            {"id": "backup", "label": "备份目标游戏目录中的同名 BIN、XML 和图集", "done": False},
            {"id": "replace", "label": "替换实验包中的同名三件套", "done": False},
            {"id": "trigger", "label": "在游戏内触发目标动作或效果", "done": False},
            {"id": "capture", "label": "在目标槽位附近截图或录屏，并登记证据", "done": False},
            {"id": "restore", "label": "结束后恢复原始资源", "done": False},
        ],
        "experiment_context": experiment_context,
        "evidence": [],
        "notes": "",
    }
    _write(destination, payload)
    write_markdown_report(destination)
    return destination


def add_evidence(case_dir: str | Path, source_file: str | Path, kind: Literal["screenshot", "video", "log", "other"] = "screenshot", note: str = "") -> Path:
    """复制外部证据进入案例目录，并保存哈希和用户说明；不分析或改写原始媒体。"""
    case_path = Path(case_dir)
    source = Path(source_file)
    if not source.exists() or not source.is_file():
        raise FileNotFoundError(f"未找到证据文件：{source}")
    payload = _load(case_path)
    evidence_dir = case_path / "evidence"
    evidence_dir.mkdir(exist_ok=True)
    index = len(payload["evidence"]) + 1
    destination = evidence_dir / f"{index:03d}_{source.name}"
    shutil.copy2(source, destination)
    payload["evidence"].append({
        "id": index,
        "kind": kind,
        "file": str(destination.relative_to(case_path)),
        "sha256": sha256_file(destination),
        "bytes": destination.stat().st_size,
        "registered_at": _utc_now(),
        "note": note,
    })
    payload["updated_at"] = _utc_now()
    _write(case_path, payload)
    write_markdown_report(case_path)
    return destination


def update_case(case_dir: str | Path, status: CaseStatus, notes: str = "", device: dict[str, str] | None = None, completed_steps: list[str] | None = None) -> Path:
    if status not in {"pending", "pass", "fail", "inconclusive"}:
        raise ValueError(f"不支持的案例状态：{status}")
    payload = _load(case_dir)
    payload["status"] = status
    if notes:
        payload["notes"] = notes
    if device:
        for key in payload["device"]:
            if key in device:
                payload["device"][key] = str(device[key])
    if completed_steps:
        done = set(completed_steps)
        for step in payload["steps"]:
            if step["id"] in done:
                step["done"] = True
    payload["updated_at"] = _utc_now()
    _write(case_dir, payload)
    return write_markdown_report(case_dir)


def write_markdown_report(case_dir: str | Path) -> Path:
    case_path = Path(case_dir)
    payload = _load(case_path)
    lines = [
        f"# 游戏内回归案例：{payload['animation']}",
        "",
        f"**状态：{payload['status']}**  ",
        f"创建：{payload['created_at']}  ",
        f"更新：{payload['updated_at']}",
        "",
        "| 项目 | 值 |",
        "|---|---|",
        f"| 原始 BIN | `{payload['original']['file']}` |",
        f"| 原始 SHA-256 | `{payload['original']['sha256']}` |",
        f"| 候选 BIN | `{payload['candidate']['file']}` |",
        f"| 候选 SHA-256 | `{payload['candidate']['sha256']}` |",
        f"| 目标槽位 | {', '.join(str(slot) for slot in payload['target_slots']) or '未指定'} |",
        f"| 差异报告 | `{payload['diff_report'] or '未关联'}` |",
        f"| 实验包 | `{payload['experiment_package'] or '未关联'}` |",
        "",
        "## 设备与版本",
        "",
        "| 字段 | 值 |",
        "|---|---|",
    ]
    for key, value in payload["device"].items():
        lines.append(f"| {key} | {value or '待填写'} |")
    lines.extend(["", "## 回归清单", "", "| 完成 | 步骤 |", "|---|---|"])
    for step in payload["steps"]:
        lines.append(f"| {'是' if step['done'] else '否'} | {step['label']} |")
    lines.extend(["", "## 外部证据", "", "| 编号 | 类型 | 文件 | SHA-256 | 说明 |", "|---:|---|---|---|---|"])
    if payload["evidence"]:
        for evidence in payload["evidence"]:
            lines.append(f"| {evidence['id']} | {evidence['kind']} | [{evidence['file']}]({evidence['file']}) | `{evidence['sha256']}` | {evidence['note']} |")
    else:
        lines.append("| — | — | 尚未登记 | — | 请导入截图、录屏或日志。 |")
    context = payload.get("experiment_context")
    if context:
        lines.extend(["", "## 组合实验条件", "", "| 项目 | 值 |", "|---|---|"])
        lines.append(f"| 实验类型 | {context.get('kind', '未标注')} |")
        lines.append(f"| 清单 | `{context.get('manifest', '未关联')}` |")
        lines.append(f"| 绑定配方 | `{context.get('binding_recipe', '未关联')}` |")
        lines.append(f"| 目标根动作 | `{context.get('target_root_animation', '未标注')}` |")
        lines.append(f"| 候选根动作 | `{context.get('candidate_root_animation', '未标注')}` |")
        fixed = context.get('fixed_variables', [])
        lines.append(f"| 必须固定 | {'；'.join(str(item) for item in fixed) if fixed else '待填写'} |")
        lines.append(f"| 阵列配置快照 | `{context.get('formation_snapshot', '未提供')}` |")
    lines.extend(["", "## 结论与备注", "", payload["notes"] or "待游戏内验证。", ""])
    path = case_path / "README_回归案例.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
