"""待提交 BILE 编辑的无 Qt 工作流。

该服务只协调已验证的领域模块；文件选择、消息框和状态栏提示仍由 UI 层负责。
"""
from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from .assets import create_triplet
from .diff_analysis import AnimationDifferenceResult, compare_animation
from .edit_session import EditSession
from .experiment_package import ExperimentPackageResult, create_experiment_package
from .preflight import PreflightReport, run_preflight
from .bile_format import parse_file
from .track_evidence import TrackImpactEvidence, write_track_impact_evidence
from .preview_renderer import Atlas
from .regression_case import create_regression_case


class CandidateWorkflowError(ValueError):
    """候选工作流不满足脏会话或预检条件。"""


@dataclass(frozen=True)
class CandidateRegressionResult:
    case_dir: Path
    diff: AnimationDifferenceResult
    package: ExperimentPackageResult


class CandidateWorkflow:
    """将一个 EditSession 与它的目标三件套绑定，形成可测试的候选交付流程。"""

    def __init__(self, original_bin: str | Path, xml: str | Path, image: str | Path, atlas: Atlas, session: EditSession) -> None:
        self.original_bin = Path(original_bin)
        self.triplet = create_triplet(self.original_bin, xml, image)
        self.atlas = atlas
        self.session = session
        if self.session.source_path != self.original_bin:
            raise CandidateWorkflowError("编辑会话的源 BIN 与工作流目标 BIN 不一致")

    def require_preflight(self) -> PreflightReport:
        if not self.session.dirty:
            raise CandidateWorkflowError("没有待验证编辑")
        result = run_preflight(self.session, self.atlas)
        if result.has_errors:
            raise CandidateWorkflowError(result.text)
        return result

    def create_diff(self, animation_name: str, output_dir: str | Path, canvas_size: tuple[int, int] = (512, 384)) -> AnimationDifferenceResult:
        self.require_preflight()
        with tempfile.TemporaryDirectory(prefix="bile-workbench-diff-") as temp_dir:
            candidate = Path(temp_dir) / "candidate.bin"
            self.session.write_candidate(candidate)
            return compare_animation(self.original_bin, candidate, self.atlas, animation_name, Path(output_dir), canvas_size)

    def create_track_impact_evidence(self, output_dir: str | Path) -> TrackImpactEvidence:
        """为当前待提交的 BELE 编辑输出静态轨道引用范围，不替代游戏内验证。"""
        self.require_preflight()
        changed_keyframes = [int(change["index"]) for change in self.session.patch_payload()["keyframes"]]
        document = parse_file(self.original_bin)
        return write_track_impact_evidence(document, changed_keyframes, output_dir)

    def create_experiment_package(self, archive_path: str | Path) -> ExperimentPackageResult:
        self.require_preflight()
        with tempfile.TemporaryDirectory(prefix="bile-workbench-export-") as temp_dir:
            temp = Path(temp_dir)
            patch_path = temp / "source_patch.json"
            candidate_path = temp / "candidate.bin"
            self.session.write_patch(patch_path)
            self.session.write_candidate(candidate_path)
            return create_experiment_package(
                self.original_bin, candidate_path, self.triplet.xml_path, self.triplet.image_path, archive_path, patch_path
            )

    def create_regression_case(
        self,
        case_dir: str | Path,
        animation_name: str,
        target_slots: list[int] | None = None,
        canvas_size: tuple[int, int] = (512, 384),
    ) -> CandidateRegressionResult:
        self.require_preflight()
        destination = Path(case_dir)
        with tempfile.TemporaryDirectory(prefix="bile-workbench-case-") as temp_dir:
            temp = Path(temp_dir)
            candidate = temp / "candidate.bin"
            patch = temp / "source_patch.json"
            self.session.write_candidate(candidate)
            self.session.write_patch(patch)
            diff = compare_animation(self.original_bin, candidate, self.atlas, animation_name, destination / "candidate_diff", canvas_size)
            package = create_experiment_package(
                self.original_bin, candidate, self.triplet.xml_path, self.triplet.image_path, destination / "game_experiment.zip", patch
            )
            create_regression_case(destination, self.original_bin, candidate, animation_name, diff.markdown_path, target_slots, package.archive_path)
        return CandidateRegressionResult(destination, diff, package)
