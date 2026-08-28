"""与实验相关的 Qt 对话框编排。

这里仅负责用户输入收集；格式解析、实验 ZIP、回归案例与阵列语义继续留在无 Qt 领域服务中。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox, QWidget

from .assets import discover_triplet
from .bile_format import BileFormatError, Element, parse_file
from .composition_experiment import CompositionExperimentResult, create_composition_experiment_package
from .formation_config import FormationConfig, parse_def_array, summarize_formation_config
from .regression_case import create_regression_case
from .workbench_state import Workspace


@dataclass(frozen=True)
class CompositionDialogResult:
    result: CompositionExperimentResult
    case_dir: Path


@dataclass(frozen=True)
class FormationSummaryResult:
    config: FormationConfig
    text: str


def format_formation_summary(config: FormationConfig) -> str:
    summary = summarize_formation_config(config)
    rows = [
        "=== 可选 def_array 阵列配置（只读） ===",
        f"文件：{summary['source']['file']}",
        f"SHA-256：{summary['source']['sha256']}",
        "注意：这里只描述 Array/Pos 坐标表；不推断 Army/Unit 的运行时选择关系。",
        "",
    ]
    for array in summary["arrays"]:
        primary = ", ".join(str(row["primary_count"]) for row in array["rows"]) or "—"
        special = ", ".join(str(row["special_count"]) for row in array["rows"]) or "—"
        rows.append(f"Array {array['name']} · declared n={array['declared_count']} · 行={len(array['rows'])} · primary=[{primary}] · special=[{special}]")
    if summary["warnings"]:
        rows.extend(["", "结构警告："] + [f"- {warning}" for warning in summary["warnings"]])
    return "\n".join(rows)


def select_formation_config(parent: QWidget, start_dir: Path) -> FormationSummaryResult | None:
    path, _ = QFileDialog.getOpenFileName(parent, "加载 def_array 阵列配置（只读）", str(start_dir), "XML (*.xml)")
    if not path:
        return None
    config = parse_def_array(path)
    return FormationSummaryResult(config, format_formation_summary(config))


def create_composition_experiment_from_dialog(
    parent: QWidget,
    workspace: Workspace,
    target_element: Element,
    target_slot: int,
) -> CompositionDialogResult | None:
    candidate_bin_path, _ = QFileDialog.getOpenFileName(
        parent, "选择候选 BILE BIN（三件套需位于同目录）", str(workspace.bin_path.parent), "BILE BIN (*.bin)"
    )
    if not candidate_bin_path:
        return None
    candidate_triplet = discover_triplet(candidate_bin_path)
    candidate_document = parse_file(candidate_triplet.bin_path)
    candidate_names = [element.name for element in candidate_document.animations]
    if not candidate_names:
        raise BileFormatError("候选 BIN 中没有可绑定的动画元素")
    candidate_root, ok = QInputDialog.getItem(parent, "选择候选根动作", "候选 def_motion 应绑定的根动作：", candidate_names, 0, False)
    if not ok or not candidate_root:
        return None
    unit_name, ok = QInputDialog.getText(parent, "实验元数据", "目标 def_motion 的 Unit name（可留空）：")
    if not ok:
        return None
    motion_type, ok = QInputDialog.getText(parent, "实验元数据", "目标 Motion type：", text="standby")
    if not ok:
        return None
    formation_config: Path | None = None
    if QMessageBox.question(parent, "可选阵列快照", "是否将当前目标游戏的 def_array.xml 只读副本加入实验包，用于固定上层阵列条件？") == QMessageBox.StandardButton.Yes:
        formation_path, _ = QFileDialog.getOpenFileName(parent, "选择 def_array.xml（仅登记哈希和副本）", str(workspace.bin_path.parent), "XML (*.xml)")
        if not formation_path:
            return None
        formation_config = Path(formation_path)
    default_archive = workspace.bin_path.with_name(
        f"{workspace.bin_path.stem}_from_{candidate_triplet.stem}_composition_experiment.zip"
    )
    archive_path, _ = QFileDialog.getSaveFileName(parent, "保存跨游戏组合实验包", str(default_archive), "ZIP archive (*.zip)")
    if not archive_path:
        return None
    result = create_composition_experiment_package(
        workspace.bin_path, workspace.xml_path, workspace.image_path,
        candidate_triplet.bin_path, candidate_triplet.xml_path, candidate_triplet.image_path,
        target_element.name, candidate_root, archive_path,
        target_unit_name=unit_name, target_motion_type=motion_type or "standby", target_resource=workspace.bin_path.stem,
        optional_target_formation_config=formation_config,
    )
    case_dir = Path(archive_path).with_name(Path(archive_path).stem + "_regression")
    if not case_dir.exists():
        context = {
            "kind": "cross-game-root-composition",
            "manifest": str(result.manifest_path),
            "binding_recipe": str(result.binding_recipe_path),
            "target_root_animation": target_element.name,
            "candidate_root_animation": candidate_root,
            "fixed_variables": ["游戏版本", "目标资源路径", "Army/Unit 类型", "地图与关卡", "单位方向", "阵列/Formation 选择", "镜头缩放"],
            "formation_snapshot": str(formation_config) if formation_config else "",
        }
        create_regression_case(
            case_dir, workspace.bin_path, candidate_triplet.bin_path, candidate_root,
            target_slots=[target_slot], experiment_package=result.archive_path, experiment_context=context,
        )
    return CompositionDialogResult(result, case_dir)
