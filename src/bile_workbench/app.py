"""BILE Workbench：高 DPI、深色 PySide6 动画读取与预览工作台。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw
from PySide6.QtCore import QEvent, QModelIndex, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QKeySequence, QPixmap, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSlider,
    QSpinBox,
    QStatusBar,
    QSizePolicy,
    QToolBar,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from .bile_format import BileDocument, BileFormatError, Element, parse_file
from .candidate_workflow import CandidateWorkflow, CandidateWorkflowError
from .document_session import (
    AnimationDocumentSession,
    DocumentSessionError,
    SessionSnapshot,
    SetAnchorCommand,
    SetKeyframeCommand,
)
from .diagnostics import format_diagnostics
from .edit_session import EditSession
from .interchange import apply_patch_report, export_interchange
from .bile_scene_interchange import export_scene_interchange
from .bile_scene_proposal import BileSceneProposalError, export_proposal_evidence as export_bile_scene_proposal_evidence, load_proposal, proposal_template as bile_scene_proposal_template
from .bile_scene_proposal_apply import apply_scene_proposal
from .preview_renderer import Atlas, load_atlas, render_frame, render_sprite
from .spine_atlas import render_region
from .spine_workspace import SpinePoseSession, SpineStaticWorkspace, create_pose_session, diagnostics_text as spine_diagnostics_text, export_static_manifest, load_spine_static_workspace
from .spine_sequence_export import export_spine_pose_sequence
from .spine_deform_audit import deform_audit_text
from .spine_deform_evidence_export import export_deform_audit_evidence
from .spine_sequence_timeline_time_evidence_export import export_sequence_time_audit_evidence
from .spine_two_color_evidence_export import export_two_color_timeline_evidence
from .motion_dsl import MotionDslError, MotionProposalSession, export_proposal_evidence, load_motion_proposal, proposal_template
from .preflight import run_preflight
from .regression_case import add_evidence
from .sequence_export import export_sequence
from .theme import apply_dark_theme, apply_theme, configure_high_dpi
from .theme_plugins import ThemePluginError, ThemePluginLoader, ThemePluginRepository
from .glass_effects import GlassBackdropController, GlassSpec, glass_overlay_qss
from .animation_evidence import write_animation_evidence
from .ui_animation_navigator import AnimationNavigator
from .ui_experiment_dialogs import create_composition_experiment_from_dialog, select_formation_config
from .ui_track_inspector import TrackInspector
from .ui_change_ledger import ChangeLedger
from .ui_ribbon import RibbonGroupSpec, TaskRibbon
from .ui_spine_timeline import SpineTimelineInspector
from .ui_widgets import PreviewView, TimelineWidget
from .track_context import TrackContext, active_tracks_at_slot, keyframe_contexts
from .workbench_state import Workspace

ROLE_KIND = int(Qt.ItemDataRole.UserRole) + 1
ROLE_INDEX = ROLE_KIND + 1

class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("MainWindow")
        self.setWindowTitle("BILE Workbench — 动画资源工作台")
        # 只保留合理的恢复窗口下限；首次真实桌面启动由延迟策略最大化，
        # 不用固定 resize 冒充最大化，也不妨碍用户之后恢复并自由调整窗口。
        self.resize(1280, 800)
        self.setMinimumSize(1040, 640)
        self._canvas_focus_active = False
        self._focus_dock_visibility: dict[str, bool] = {}
        self._focus_ribbon_visible = True
        self.workspace: Workspace | None = None
        self.spine_workspace: SpineStaticWorkspace | None = None
        self.spine_selected_region: str | None = None
        self.spine_selected_animation: str | None = None
        self.spine_pose_session: SpinePoseSession | None = None
        self.motion_proposal_session: MotionProposalSession | None = None
        self.active_bile_scene_proposal = None
        self.spine_pose_time = 0.0
        self.document_session: AnimationDocumentSession | None = None
        self.edit_session: EditSession | None = None  # 兼容既有候选工作流；编辑入口由 document_session.execute 驱动。
        self._unsubscribe_document_session = None
        self.selected_element: Element | None = None
        self._preview_element_index: int | None = None
        self._sprite_reference: tuple[float, float] = (0.0, 0.0)
        self._anchor_drag_active = False
        self.formation_config_text = ""
        self.play_timer = QTimer(self)
        self.play_timer.timeout.connect(self._advance_playhead)
        self.theme_plugins = ThemePluginRepository(self._bundled_plugin_dir())
        self.theme_plugins.discover()
        self.glass_controller = GlassBackdropController(self)
        self.glass_spec = GlassSpec(material="auto", tint="#202731", opacity=0.84, blur=20, border="#506070", glow="#8CC8FF")
        self._plugin_actions: dict[str, QAction] = {}
        self._build_actions()
        self._build_shell()
        self._rebuild_plugin_actions()
        self._apply_current_theme()
        self._set_empty_state()
        # 放到事件循环后，确保 Windows 上窗口已完成真实创建；offscreen 测试不会被强行 show。
        QTimer.singleShot(0, self._apply_initial_window_state)

    @staticmethod
    def _bundled_plugin_dir() -> Path:
        """源码和 PyInstaller one-folder 两种运行方式都能找到随程序分发的插件。"""
        if getattr(sys, "frozen", False):
            return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "plugins"
        return Path(__file__).resolve().parents[2] / "plugins"

    @property
    def display_document(self) -> BileDocument:
        if self.document_session is not None:
            return self.document_session.snapshot.document
        if self.workspace is not None:
            return self.workspace.document
        raise RuntimeError("尚未加载 BILE 文档")

    def _on_document_snapshot(self, snapshot: SessionSnapshot) -> None:
        """文档会话是选择和显示文档的唯一事实来源；控件刷新由现有方法按需完成。"""
        self.selected_element = snapshot.selected_element
        if hasattr(self, "animation_navigator"):
            self.animation_navigator.set_document(snapshot.document, snapshot.selection.element_index)
        if hasattr(self, "document_status_label"):
            mode = "只读兼容" if not snapshot.editable else "保守编辑"
            changes = f"暂存 {snapshot.change_count} 项变更" if snapshot.dirty else "原始基线未修改"
            selected = snapshot.selected_element.name if snapshot.selected_element is not None else "未选择动画"
            self.document_status_label.setText(f"文档状态 · BILE v{snapshot.bile_version} · {mode} · {changes} · {selected}")
        self._refresh_productivity_context(snapshot)
        self._refresh_command_availability(snapshot)
        self._update_change_ledger()
        if hasattr(self, "status_document_label"):
            boundary = "只读" if not snapshot.editable else "保守写回"
            self.status_document_label.setText(f"BILE v{snapshot.bile_version} · {boundary} · 变更 {snapshot.change_count}")
            selection = snapshot.selection
            if selection.keyframe_index is not None:
                self.status_context_label.setText(
                    f"Track · 通道 {selection.channel_index + 1 if selection.channel_index is not None else '—'} · "
                    f"槽位 {selection.frame_slot if selection.frame_slot is not None else selection.slot} · BELE[{selection.keyframe_index}]"
                )
            elif snapshot.selected_element is not None:
                self.status_context_label.setText(f"元素 · {snapshot.selected_element.name} · 槽位 {selection.slot}")
            else:
                self.status_context_label.setText("未选择动画")

    def _build_actions(self) -> None:
        self.open_action = QAction("打开 BILE…", self, shortcut=QKeySequence.StandardKey.Open, triggered=self.open_bin_dialog)
        self.open_spine_action = QAction("打开 Spine 静态资源…", self, triggered=self.open_spine_dialog)
        self.export_spine_static_action = QAction("导出 Spine 结构与动画档案…", self, triggered=self.export_spine_static_dialog)
        self.export_spine_pose_sequence_action = QAction("导出 Spine 只读 pose 序列…", self, triggered=self.export_spine_pose_sequence_dialog)
        self.export_spine_deform_evidence_action = QAction("导出 Spine deform 审计证据…", self, triggered=self.export_spine_deform_evidence_dialog)
        self.export_spine_two_color_evidence_action = QAction("导出 Spine dark/two-color 审计证据…", self, triggered=self.export_spine_two_color_evidence_dialog)
        self.export_spine_sequence_time_audit_evidence_action = QAction("导出 Spine sequence 时间审计证据…", self, triggered=self.export_spine_sequence_time_audit_evidence_dialog)
        self.export_motion_template_action = QAction("导出 AI Motion DSL 模板…", self, triggered=self.export_motion_template_dialog)
        self.load_motion_proposal_action = QAction("加载 AI Motion DSL 提案（只读）…", self, triggered=self.load_motion_proposal_dialog)
        self.undo_motion_proposal_action = QAction("撤销 pose 提案", self, triggered=self.undo_motion_proposal)
        self.redo_motion_proposal_action = QAction("重做 pose 提案", self, triggered=self.redo_motion_proposal)
        self.export_motion_evidence_action = QAction("导出 pose 提案证据…", self, triggered=self.export_motion_evidence_dialog)
        self.open_sample_action = QAction("加载原包示例", self, triggered=self.open_sample)
        self.open_cross_game_sample_action = QAction("加载跨游戏验证样本…", self, triggered=self.open_cross_game_sample)
        self.export_json_action = QAction("导出 AI 中转 JSON…", self, shortcut="Ctrl+E", triggered=self.export_json_dialog)
        self.export_scene_interchange_action = QAction("导出 BILE 场景 JSON + 渲染见证（只读）…", self, triggered=self.export_scene_interchange_dialog)
        self.export_bile_scene_proposal_template_action = QAction("导出 BILE AI 场景提案模板…", self, triggered=self.export_bile_scene_proposal_template_dialog)
        self.load_bile_scene_proposal_action = QAction("加载 BILE AI 场景提案（暂存）…", self, triggered=self.load_bile_scene_proposal_dialog)
        self.export_bile_scene_proposal_evidence_action = QAction("导出 BILE AI 场景提案证据…", self, triggered=self.export_bile_scene_proposal_evidence_dialog)
        self.apply_patch_action = QAction("应用安全补丁 JSON…", self, shortcut="Ctrl+P", triggered=self.apply_patch_dialog)
        self.save_pending_action = QAction("导出待提交补丁…", self, shortcut="Ctrl+S", triggered=self.save_pending_patch_dialog)
        self.clear_pending_action = QAction("撤销全部待提交编辑", self, shortcut="Ctrl+Shift+Z", triggered=self.clear_pending_edits)
        self.undo_action = QAction("撤销", self, shortcut=QKeySequence.StandardKey.Undo, triggered=self.undo_pending_edit)
        self.redo_action = QAction("重做", self, shortcut=QKeySequence.StandardKey.Redo, triggered=self.redo_pending_edit)
        self.compare_action = QAction("导出当前槽位对比图…", self, shortcut="Ctrl+Shift+C", triggered=self.export_frame_comparison_dialog)
        self.export_sequence_action = QAction("导出完整动画序列…", self, shortcut="Ctrl+Shift+E", triggered=self.export_sequence_dialog)
        self.experiment_package_action = QAction("生成游戏内实验包…", self, shortcut="Ctrl+Shift+G", triggered=self.create_experiment_package_dialog)
        self.candidate_diff_action = QAction("生成候选动画差异报告…", self, shortcut="Ctrl+Shift+R", triggered=self.create_candidate_diff_dialog)
        self.track_impact_action = QAction("导出 BELE 轨道影响范围…", self, shortcut="Ctrl+Shift+I", triggered=self.export_track_impact_dialog)
        self.create_regression_case_action = QAction("创建游戏内回归案例…", self, triggered=self.create_regression_case_dialog)
        self.composition_experiment_action = QAction("生成跨游戏组合实验…", self, shortcut="Ctrl+Shift+M", triggered=self.create_composition_experiment_dialog)
        self.open_formation_config_action = QAction("加载 def_array 阵列摘要…", self, triggered=self.open_formation_config_dialog)
        self.add_evidence_action = QAction("登记游戏内截图/录屏证据…", self, triggered=self.add_regression_evidence_dialog)
        self.export_diagnostics_action = QAction("导出资源诊断报告…", self, shortcut="Ctrl+Shift+D", triggered=self.export_diagnostics_dialog)
        self.export_animation_evidence_action = QAction("导出单动画静态档案…", self, shortcut="Ctrl+Shift+A", triggered=self.export_animation_evidence_dialog)
        self.exit_action = QAction("退出", self, shortcut=QKeySequence.StandardKey.Quit, triggered=self.close)
        self.fit_action = QAction("适配内容", self, shortcut="F", triggered=self.fit_preview)
        self.zoom_in_action = QAction("放大画布", self, shortcut="+", triggered=self.zoom_preview_in)
        self.zoom_out_action = QAction("缩小画布", self, shortcut="-", triggered=self.zoom_preview_out)
        self.play_action = QAction("播放", self, checkable=True, shortcut="Space", triggered=self.toggle_playback)
        self.prev_action = QAction("上一槽位", self, shortcut="Left", triggered=lambda: self.set_slot(self.slot_slider.value() - 1))
        self.next_action = QAction("下一槽位", self, shortcut="Right", triggered=lambda: self.set_slot(self.slot_slider.value() + 1))
        self.about_action = QAction("关于格式验证", self, triggered=self.show_about)
        self.light_theme_action = QAction("基础浅色", self, checkable=True, triggered=lambda: self._set_base_theme("light"))
        self.dark_theme_action = QAction("基础深色", self, checkable=True, triggered=lambda: self._set_base_theme("dark"))
        self.base_theme_group = QActionGroup(self)
        self.base_theme_group.setExclusive(True)
        self.base_theme_group.addAction(self.light_theme_action)
        self.base_theme_group.addAction(self.dark_theme_action)
        self.no_plugin_theme_action = QAction("不使用插件主题", self, checkable=True, triggered=lambda: self._set_plugin_theme(None))
        self.plugin_theme_group = QActionGroup(self)
        self.plugin_theme_group.setExclusive(True)
        self.plugin_theme_group.addAction(self.no_plugin_theme_action)
        self.import_plugin_file_action = QAction("导入插件文件…", self, triggered=self.import_plugin_file)
        self.import_plugin_folder_action = QAction("导入插件文件夹…", self, triggered=self.import_plugin_folder)
        self.refresh_plugins_action = QAction("刷新已发现插件", self, triggered=self.refresh_theme_plugins)
        self.focus_track_action = QAction("聚焦当前轨道", self, triggered=self.focus_current_track)
        self.clear_track_selection_action = QAction("清除轨道选择", self, triggered=self.clear_track_selection)
        self.focus_canvas_action = QAction("聚焦画布", self, shortcut=QKeySequence("F11"), triggered=self.toggle_canvas_focus)
        self.focus_canvas_action.setCheckable(True)
        self.restore_layout_action = QAction("恢复默认工作区", self, shortcut=QKeySequence("Ctrl+Shift+F"), triggered=self.restore_default_layout)

    def _build_shell(self) -> None:
        file_menu = self.menuBar().addMenu("文件")
        file_menu.addAction(self.open_action)
        file_menu.addAction(self.open_sample_action)
        file_menu.addAction(self.open_cross_game_sample_action)
        file_menu.addAction(self.open_spine_action)
        file_menu.addSeparator()
        file_menu.addAction(self.export_spine_static_action)
        file_menu.addAction(self.export_spine_pose_sequence_action)
        file_menu.addAction(self.export_spine_deform_evidence_action)
        file_menu.addAction(self.export_spine_two_color_evidence_action)
        file_menu.addAction(self.export_spine_sequence_time_audit_evidence_action)
        file_menu.addAction(self.export_json_action)
        file_menu.addAction(self.export_scene_interchange_action)
        file_menu.addAction(self.export_bile_scene_proposal_template_action)
        file_menu.addAction(self.load_bile_scene_proposal_action)
        file_menu.addAction(self.export_bile_scene_proposal_evidence_action)
        file_menu.addAction(self.apply_patch_action)
        file_menu.addAction(self.save_pending_action)
        file_menu.addAction(self.experiment_package_action)
        file_menu.addAction(self.clear_pending_action)
        file_menu.addAction(self.export_diagnostics_action)
        file_menu.addSeparator()
        file_menu.addAction(self.exit_action)
        edit_menu = self.menuBar().addMenu("编辑")
        edit_menu.addAction(self.undo_action)
        edit_menu.addAction(self.redo_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.compare_action)
        edit_menu.addAction(self.export_sequence_action)
        regression_menu = self.menuBar().addMenu("回归")
        regression_menu.addAction(self.candidate_diff_action)
        regression_menu.addAction(self.track_impact_action)
        regression_menu.addAction(self.create_regression_case_action)
        regression_menu.addSeparator()
        regression_menu.addAction(self.composition_experiment_action)
        regression_menu.addAction(self.open_formation_config_action)
        regression_menu.addAction(self.add_evidence_action)
        self.view_menu = self.menuBar().addMenu("视图")
        self.view_menu.addAction(self.fit_action)
        self.view_menu.addAction(self.zoom_in_action)
        self.view_menu.addAction(self.zoom_out_action)
        self.view_menu.addAction(self.focus_canvas_action)
        self.view_menu.addSeparator()
        self.view_menu.addAction(self.restore_layout_action)
        self.theme_menu = self.view_menu.addMenu("主题")
        self.base_theme_menu = self.theme_menu.addMenu("宿主基础主题")
        self.base_theme_menu.addAction(self.light_theme_action)
        self.base_theme_menu.addAction(self.dark_theme_action)
        self.plugin_theme_menu = self.theme_menu.addMenu("外部插件主题")
        self.plugin_theme_menu.addAction(self.no_plugin_theme_action)
        self.theme_menu.addSeparator()
        self.theme_menu.addAction(self.import_plugin_file_action)
        self.theme_menu.addAction(self.import_plugin_folder_action)
        self.theme_menu.addAction(self.refresh_plugins_action)
        help_menu = self.menuBar().addMenu("帮助")
        help_menu.addAction(self.about_action)
        central = QWidget()
        central.setObjectName("MainSurface")
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(14, 14, 14, 10)
        central_layout.setSpacing(9)
        self.title_label = QLabel("未加载动画资源")
        self.title_label.setStyleSheet("font-size: 16pt; font-weight: 700;")
        self.subtitle_label = QLabel("打开一个 .bin 文件；工作台会自动寻找同名 XML 与 WebP/PNG 图集。")
        self.subtitle_label.setProperty("muted", True)
        central_layout.addWidget(self.title_label)
        central_layout.addWidget(self.subtitle_label)
        self.document_status_label = QLabel("文档状态 · 等待加载三件套")
        self.document_status_label.setProperty("muted", True)
        self.document_status_label.setObjectName("DocumentStatusLabel")
        central_layout.addWidget(self.document_status_label)
        self.plugin_badge = QFrame()
        self.plugin_badge.setObjectName("PluginBadge")
        self.plugin_badge.setMaximumHeight(66)
        plugin_badge_layout = QHBoxLayout(self.plugin_badge)
        plugin_badge_layout.setContentsMargins(8, 6, 10, 6)
        plugin_badge_layout.setSpacing(9)
        self.plugin_badge_avatar = QLabel("BILE")
        self.plugin_badge_avatar.setObjectName("PluginBadgeAvatar")
        self.plugin_badge_avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.plugin_badge_avatar.setFixedSize(48, 48)
        plugin_badge_layout.addWidget(self.plugin_badge_avatar)
        plugin_text = QVBoxLayout()
        plugin_text.setContentsMargins(0, 0, 0, 0)
        plugin_text.setSpacing(0)
        self.plugin_badge_title = QLabel("宿主基础主题")
        self.plugin_badge_title.setObjectName("PluginBadgeTitle")
        self.plugin_badge_meta = QLabel("深色 · 未启用外部主题插件")
        self.plugin_badge_meta.setObjectName("PluginBadgeMeta")
        self.plugin_badge_meta.setProperty("muted", True)
        plugin_text.addWidget(self.plugin_badge_title)
        plugin_text.addWidget(self.plugin_badge_meta)
        plugin_badge_layout.addLayout(plugin_text, 1)
        central_layout.addWidget(self.plugin_badge)
        self.preview = PreviewView()
        self.preview.setObjectName("PreviewView")
        self.preview.hotspot_changed.connect(self._on_hotspot_preview_changed)
        self.preview.hotspot_drag_finished.connect(self._on_hotspot_preview_drag_finished)
        self.preview.setFrameStyle(QFrame.Shape.StyledPanel)
        self.preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        # 中央预览是工作台的主区，即使多个 Dock 同时打开也不能退化成细缝。
        self.preview.setMinimumSize(260, 280)
        central_layout.addWidget(self.preview, 1)
        control = QFrame()
        control.setProperty("card", True)
        control_layout = QHBoxLayout(control)
        control_layout.setContentsMargins(10, 8, 10, 8)
        self.slot_label = QLabel("槽位 — / —")
        self.slot_slider = QSlider(Qt.Orientation.Horizontal)
        self.slot_slider.valueChanged.connect(self.set_slot)
        self.slot_spin = QSpinBox()
        self.slot_spin.valueChanged.connect(self.set_slot)
        self.slot_slider.setEnabled(False)
        self.slot_spin.setEnabled(False)
        control_layout.addWidget(self.slot_label)
        control_layout.addWidget(self.slot_slider, 1)
        control_layout.addWidget(self.slot_spin)
        control.setMaximumHeight(74)
        central_layout.addWidget(control)
        central_layout.setStretch(0, 0)
        central_layout.setStretch(1, 0)
        central_layout.setStretch(2, 0)
        central_layout.setStretch(3, 1)
        central_layout.setStretch(4, 0)
        self.setCentralWidget(central)

        self._build_resource_dock()
        self._build_animation_navigator_dock()
        self._build_inspector_dock()
        self._build_track_inspector_dock()
        self._build_timeline_dock()
        self._build_spine_timeline_dock()
        self._build_diagnostics_dock()
        self._build_change_ledger_dock()
        self.setDockNestingEnabled(True)
        self._build_productivity_chrome()
        self._configure_default_dock_sizes()
        self._default_layout_state = self.saveState()
        status = QStatusBar()
        self.setStatusBar(status)
        self.status_document_label = QLabel("BILE：未加载")
        self.status_document_label.setProperty("muted", True)
        self.status_context_label = QLabel("未选择动画")
        self.status_context_label.setProperty("muted", True)
        status.addPermanentWidget(self.status_document_label)
        status.addPermanentWidget(self.status_context_label)
        self.statusBar().showMessage("就绪：等待加载 BILE 三件套")

    def _build_productivity_chrome(self) -> None:
        """用任务 Ribbon 取代全部命令平铺的主工具栏；QAction 仍是唯一命令源。"""
        self.ribbon = TaskRibbon()
        self.ribbon.add_quick_actions((self.open_action, self.save_pending_action, self.undo_action, self.redo_action, self.play_action))
        self.ribbon.add_tab(
            "file",
            "文件",
            (
                RibbonGroupSpec("资源", (self.open_action, self.open_sample_action, self.open_cross_game_sample_action, self.open_spine_action), 2),
                RibbonGroupSpec("中转与交付", (self.export_json_action, self.export_scene_interchange_action, self.export_bile_scene_proposal_template_action, self.load_bile_scene_proposal_action, self.export_bile_scene_proposal_evidence_action, self.export_spine_static_action, self.apply_patch_action, self.save_pending_action), 2),
            ),
        )
        self.ribbon.add_tab(
            "edit",
            "编辑",
            (
                RibbonGroupSpec("历史", (self.undo_action, self.redo_action, self.clear_pending_action), 1),
                RibbonGroupSpec("审阅", (self.compare_action, self.export_diagnostics_action), 1),
            ),
        )
        self.ribbon.add_tab(
            "animation",
            "动画工具",
            (
                RibbonGroupSpec("播放与定位", (self.prev_action, self.play_action, self.next_action), 1),
                RibbonGroupSpec("输出与档案", (self.export_sequence_action, self.export_animation_evidence_action, self.fit_action), 1),
            ),
            contextual=True,
        )
        self.ribbon.add_tab(
            "spine",
            "Spine 动画",
            (
                RibbonGroupSpec("动画档案", (self.export_spine_static_action, self.export_spine_pose_sequence_action, self.export_spine_deform_evidence_action, self.export_spine_two_color_evidence_action, self.export_spine_sequence_time_audit_evidence_action, self.fit_action), 1),
                RibbonGroupSpec("AI 只读提案", (self.export_motion_template_action, self.load_motion_proposal_action, self.undo_motion_proposal_action, self.redo_motion_proposal_action, self.export_motion_evidence_action), 2),
                RibbonGroupSpec("静态资源", (self.open_spine_action,), 1),
            ),
            contextual=True,
        )
        self.ribbon.add_tab(
            "track",
            "轨道工具",
            (
                RibbonGroupSpec("当前 Track", (self.focus_track_action, self.clear_track_selection_action), 1),
                RibbonGroupSpec("影响范围", (self.track_impact_action, self.candidate_diff_action), 1),
            ),
            contextual=True,
        )
        self.ribbon.add_tab(
            "validation",
            "验证",
            (
                RibbonGroupSpec("候选与取证", (self.candidate_diff_action, self.experiment_package_action, self.track_impact_action, self.export_animation_evidence_action), 2),
                RibbonGroupSpec("游戏内回归", (self.create_regression_case_action, self.add_evidence_action), 1),
            ),
        )
        self.ribbon.add_tab(
            "experiment",
            "实验",
            (
                RibbonGroupSpec("跨游戏组合", (self.composition_experiment_action, self.open_formation_config_action), 1),
                RibbonGroupSpec("诊断", (self.export_diagnostics_action, self.about_action), 1),
            ),
        )
        dock_actions = tuple(
            self.findChild(QDockWidget, object_name).toggleViewAction()
            for object_name in (
                "ResourceBrowserDock",
                "AnimationNavigatorDock",
                "InspectorDock",
                "TrackInspectorDock",
                "TimelineDock",
                "SpineTimelineDock",
                "DiagnosticsDock",
                "ChangeLedgerDock",
            )
        )
        for action in dock_actions:
            self.view_menu.addAction(action)
        self.view_menu.addSeparator()
        self.view_menu.addAction(self.focus_canvas_action)
        self.ribbon.add_tab(
            "view",
            "视图",
            (
                RibbonGroupSpec("专业面板", dock_actions[:3], 1),
                RibbonGroupSpec("时间与取证", dock_actions[3:], 2),
                RibbonGroupSpec("工作区", (self.focus_canvas_action, self.restore_layout_action, self.fit_action, self.zoom_in_action, self.zoom_out_action), 1),
                RibbonGroupSpec("主题", (self.light_theme_action, self.dark_theme_action, self.no_plugin_theme_action, self.refresh_plugins_action), 1),
            ),
        )
        ribbon_toolbar = QToolBar("功能区", self)
        ribbon_toolbar.setObjectName("TaskRibbonToolBar")
        ribbon_toolbar.setMovable(False)
        ribbon_toolbar.setFloatable(False)
        ribbon_toolbar.setAllowedAreas(Qt.ToolBarArea.TopToolBarArea)
        ribbon_toolbar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        ribbon_toolbar.addWidget(self.ribbon)
        self._ribbon_toolbar = ribbon_toolbar
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, ribbon_toolbar)

    def _rebuild_plugin_actions(self) -> None:
        """根据外部发现结果重建插件菜单；宿主不硬编码具体插件名称。"""
        for action in self._plugin_actions.values():
            self.plugin_theme_menu.removeAction(action)
            self.plugin_theme_group.removeAction(action)
            action.deleteLater()
        self._plugin_actions = {}
        for plugin in sorted(self.theme_plugins.plugins.values(), key=lambda item: item.name.casefold()):
            action = QAction(plugin.name, self, checkable=True)
            source_text = str(plugin.source)
            action.setToolTip(f"{plugin.description}\n版本 {plugin.version} · 来源：{source_text}")
            action.triggered.connect(lambda checked, plugin_id=plugin.plugin_id: self._set_plugin_theme(plugin_id))
            self.plugin_theme_group.addAction(action)
            self.plugin_theme_menu.addAction(action)
            self._plugin_actions[plugin.plugin_id] = action
        if self.theme_plugins.errors:
            self.refresh_plugins_action.setToolTip("发现问题：\n" + "\n".join(self.theme_plugins.errors))
        else:
            self.refresh_plugins_action.setToolTip("重新扫描内置和已记住的外部插件来源")
        self._sync_theme_actions()

    def _sync_theme_actions(self) -> None:
        if not hasattr(self, "light_theme_action"):
            return
        self.light_theme_action.setChecked(self.theme_plugins.base_mode == "light")
        self.dark_theme_action.setChecked(self.theme_plugins.base_mode == "dark")
        self.no_plugin_theme_action.setChecked(self.theme_plugins.active_plugin_id is None)
        for plugin_id, action in self._plugin_actions.items():
            action.setChecked(plugin_id == self.theme_plugins.active_plugin_id)

    def _apply_current_theme(self) -> None:
        app = QApplication.instance()
        if app is None:
            return
        plugin = self.theme_plugins.active_plugin()
        self.glass_spec = plugin.glass if plugin is not None else GlassSpec(material="auto", tint="#202731", opacity=0.84, blur=20, border="#506070", glow="#8CC8FF")
        glass_result = self.glass_controller.apply(self.glass_spec)
        plugin_qss = plugin.qss_for(self.theme_plugins.base_mode) if plugin is not None else ""
        glass_qss = glass_overlay_qss(self.glass_spec, native=glass_result.native) if self.glass_spec.material != "none" else ""
        apply_theme(app, self.theme_plugins.base_mode, plugin_qss + glass_qss)
        if plugin is None:
            mode_label = "浅色" if self.theme_plugins.base_mode == "light" else "深色"
            self.plugin_badge_avatar.setPixmap(QPixmap())
            self.plugin_badge_avatar.setText("BILE")
            self.plugin_badge_title.setText("宿主基础主题")
            self.plugin_badge_meta.setText(f"{mode_label} · 宿主玻璃：{glass_result.label} · 未启用外部主题插件")
        else:
            pixmap = QPixmap()
            if plugin.avatar_data:
                pixmap.loadFromData(plugin.avatar_data)
            self.plugin_badge_avatar.setText("" if not pixmap.isNull() else "AI")
            if not pixmap.isNull():
                self.plugin_badge_avatar.setPixmap(pixmap.scaled(48, 48, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            else:
                self.plugin_badge_avatar.setPixmap(QPixmap())
            mode_label = "浅色" if self.theme_plugins.base_mode == "light" else "深色"
            self.plugin_badge_title.setText(plugin.name)
            self.plugin_badge_meta.setText(f"{mode_label} · {glass_result.label} · 插件 v{plugin.version} · 外部资源")
        self._sync_theme_actions()

    def _set_base_theme(self, mode: str) -> None:
        try:
            self.theme_plugins.set_base_mode(mode)
            self._apply_current_theme()
            self.statusBar().showMessage(f"已切换宿主基础主题：{'浅色' if mode == 'light' else '深色'}。")
        except ThemePluginError as exc:
            QMessageBox.warning(self, "基础主题切换失败", str(exc))
            self._sync_theme_actions()

    def _set_plugin_theme(self, plugin_id: str | None) -> None:
        try:
            self.theme_plugins.set_active_plugin(plugin_id)
            self._apply_current_theme()
            if plugin_id is None:
                self.statusBar().showMessage("已关闭外部主题插件，当前使用宿主基础主题。")
            else:
                plugin = self.theme_plugins.plugins[plugin_id]
                self.statusBar().showMessage(f"已启用外部主题插件：{plugin.name}；插件随当前浅色/深色基础模式切换。")
        except ThemePluginError as exc:
            QMessageBox.warning(self, "插件主题切换失败", str(exc))
            self._sync_theme_actions()

    def refresh_theme_plugins(self) -> None:
        self.theme_plugins.discover()
        self._rebuild_plugin_actions()
        self._apply_current_theme()
        issue_text = f"；{len(self.theme_plugins.errors)} 个来源被拒绝" if self.theme_plugins.errors else ""
        self.statusBar().showMessage(f"已刷新主题插件：发现 {len(self.theme_plugins.plugins)} 个可用插件{issue_text}。")

    def _remember_and_refresh_plugin(self, source: Path) -> None:
        try:
            # 先验证一次，导入失败不会污染持久化来源列表。
            ThemePluginLoader.load(source)
            self.theme_plugins.remember_source(source)
            self.refresh_theme_plugins()
            plugin = next((item for item in self.theme_plugins.plugins.values() if item.source == Path(source).expanduser().resolve()), None)
            if plugin is not None:
                self._set_plugin_theme(plugin.plugin_id)
        except ThemePluginError as exc:
            QMessageBox.warning(self, "插件导入失败", str(exc))

    def import_plugin_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "导入主题插件文件", str(Path.home()), "BILE Theme Plugin (*.bileplugin *.zip)")
        if path:
            self._remember_and_refresh_plugin(Path(path))

    def import_plugin_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "导入主题插件文件夹", str(Path.home()))
        if path:
            self._remember_and_refresh_plugin(Path(path))

    def _configure_default_dock_sizes(self) -> None:
        """给 Qt 一个稳健起点，之后仍由用户拖拽调整；状态会被保存到默认布局。"""
        left = [self.findChild(QDockWidget, name) for name in ("ResourceBrowserDock", "AnimationNavigatorDock")]
        right = [self.findChild(QDockWidget, name) for name in ("InspectorDock", "TrackInspectorDock", "DiagnosticsDock", "ChangeLedgerDock")]
        bottom = [self.findChild(QDockWidget, name) for name in ("TimelineDock", "SpineTimelineDock")]
        self.resizeDocks([dock for dock in left if dock is not None], [300, 300], Qt.Orientation.Horizontal)
        self.resizeDocks([dock for dock in right if dock is not None], [350, 350, 350, 350], Qt.Orientation.Horizontal)
        self.resizeDocks([dock for dock in bottom if dock is not None], [205, 205], Qt.Orientation.Vertical)

    def _apply_initial_window_state(self) -> None:
        """真实桌面首次显示时最大化；离屏测试未 show 时不改变测试窗口状态。"""
        if self.isVisible() and not self.isMaximized() and not self.isFullScreen():
            self.showMaximized()
        self._configure_default_dock_sizes()
        self._schedule_preview_fit()

    def _schedule_preview_fit(self) -> None:
        if hasattr(self, "preview"):
            QTimer.singleShot(0, self.fit_preview)

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        self._schedule_preview_fit()

    def _workbench_docks(self) -> tuple[QDockWidget, ...]:
        return tuple(
            dock
            for object_name in (
                "ResourceBrowserDock",
                "AnimationNavigatorDock",
                "InspectorDock",
                "TrackInspectorDock",
                "TimelineDock",
                "SpineTimelineDock",
                "DiagnosticsDock",
                "ChangeLedgerDock",
            )
            if (dock := self.findChild(QDockWidget, object_name)) is not None
        )

    def toggle_canvas_focus(self) -> None:
        """在完整工作区与画布优先视图之间切换，不丢失用户原来的 Dock 可见性。"""
        if self._canvas_focus_active:
            for dock in self._workbench_docks():
                dock.setVisible(self._focus_dock_visibility.get(dock.objectName(), True))
            self._ribbon_toolbar.setVisible(self._focus_ribbon_visible)
            self._canvas_focus_active = False
            self.focus_canvas_action.setChecked(False)
            self.statusBar().showMessage("已恢复进入聚焦前的工作区；可继续拖拽调整面板比例。")
        else:
            self._focus_dock_visibility = {dock.objectName(): dock.isVisible() for dock in self._workbench_docks()}
            self._focus_ribbon_visible = self._ribbon_toolbar.isVisible()
            for dock in self._workbench_docks():
                dock.hide()
            self._ribbon_toolbar.hide()
            self._canvas_focus_active = True
            self.focus_canvas_action.setChecked(True)
            self.statusBar().showMessage("已聚焦画布；按 F11 或点击“聚焦画布”可恢复工作区。")
        self.preview.setFocus(Qt.FocusReason.OtherFocusReason)
        self._schedule_preview_fit()

    def _refresh_command_availability(self, snapshot: SessionSnapshot | None = None) -> None:
        """使所有入口的可用性一致；拒绝扩大既有 BILE 编辑白名单。"""
        loaded = snapshot is not None
        selected = snapshot.selected_element if snapshot is not None else None
        animation_selected = selected is not None and not selected.has_texture
        editable = bool(snapshot and snapshot.editable)
        dirty = bool(snapshot and snapshot.dirty)
        can_undo = bool(self.edit_session and self.edit_session.can_undo)
        can_redo = bool(self.edit_session and self.edit_session.can_redo)
        for action in (self.export_json_action, self.export_scene_interchange_action, self.apply_patch_action, self.export_diagnostics_action, self.open_formation_config_action):
            action.setEnabled(loaded)
        self.export_bile_scene_proposal_template_action.setEnabled(editable)
        self.load_bile_scene_proposal_action.setEnabled(editable)
        self.export_bile_scene_proposal_evidence_action.setEnabled(bool(editable and self.active_bile_scene_proposal is not None))
        self.export_spine_static_action.setEnabled(self.spine_workspace is not None)
        spine_pose_ready = self.spine_pose_session is not None
        self.export_spine_pose_sequence_action.setEnabled(spine_pose_ready)
        self.export_spine_deform_evidence_action.setEnabled(spine_pose_ready)
        self.export_spine_two_color_evidence_action.setEnabled(spine_pose_ready)
        self.export_spine_sequence_time_audit_evidence_action.setEnabled(bool(spine_pose_ready and self.spine_pose_session and self.spine_pose_session.workspace.engine == "spine41"))
        for action in (self.export_motion_template_action, self.load_motion_proposal_action, self.export_motion_evidence_action):
            action.setEnabled(spine_pose_ready)
        self.undo_motion_proposal_action.setEnabled(bool(self.motion_proposal_session and self.motion_proposal_session.can_undo))
        self.redo_motion_proposal_action.setEnabled(bool(self.motion_proposal_session and self.motion_proposal_session.can_redo))
        for action in (self.compare_action, self.export_sequence_action, self.export_animation_evidence_action):
            action.setEnabled(animation_selected)
        for action in (self.prev_action, self.next_action, self.play_action):
            action.setEnabled(animation_selected or spine_pose_ready)
        for action in (self.save_pending_action, self.clear_pending_action, self.candidate_diff_action, self.track_impact_action, self.experiment_package_action, self.create_regression_case_action):
            action.setEnabled(editable and dirty)
        self.undo_action.setEnabled(editable and can_undo)
        self.redo_action.setEnabled(editable and can_redo)
        self.composition_experiment_action.setEnabled(animation_selected)
        track_selected = animation_selected and snapshot is not None and snapshot.selection.keyframe_index is not None
        self.focus_track_action.setEnabled(track_selected)
        self.clear_track_selection_action.setEnabled(track_selected)

    def _refresh_productivity_context(self, snapshot: SessionSnapshot | None = None) -> None:
        """以会话选择状态驱动上下文工具页，不增加任何格式写回能力。"""
        if not hasattr(self, "ribbon"):
            return
        snapshot = snapshot or (self.document_session.snapshot if self.document_session is not None else None)
        selected = snapshot.selected_element if snapshot is not None else None
        animation_selected = selected is not None and not selected.has_texture
        track_selected = animation_selected and snapshot is not None and snapshot.selection.keyframe_index is not None
        self.ribbon.set_context_visible("animation", animation_selected)
        self.ribbon.set_context_visible("track", track_selected)
        spine_timeline_visible = self.spine_workspace is not None and self.spine_workspace.timeline_archive is not None
        self.ribbon.set_context_visible("spine", spine_timeline_visible)
        self.focus_track_action.setEnabled(track_selected)
        self.clear_track_selection_action.setEnabled(track_selected)

    def focus_current_track(self) -> None:
        if self.document_session is None or self.document_session.snapshot.selection.keyframe_index is None:
            self.statusBar().showMessage("尚未选择 Track；请在时间线高亮区或“轨道检查器”中选择。")
            return
        dock = self.findChild(QDockWidget, "TrackInspectorDock")
        dock.show()
        dock.raise_()
        self.track_inspector.setFocus()
        self.statusBar().showMessage("已聚焦轨道检查器；当前轨道与时间线高亮保持同步。")

    def clear_track_selection(self) -> None:
        if self.document_session is None:
            return
        element_index = self.document_session.snapshot.selection.element_index
        if element_index is None:
            return
        self.document_session.select_element(element_index)
        self.statusBar().showMessage("已清除轨道选择；时间线仍保留当前动画与槽位。")

    def restore_default_layout(self) -> None:
        if hasattr(self, "_default_layout_state"):
            self._canvas_focus_active = False
            self._ribbon_toolbar.setVisible(True)
            self.focus_canvas_action.setChecked(False)
            self.restoreState(self._default_layout_state)
            self._configure_default_dock_sizes()
            self.statusBar().showMessage("已恢复默认专业工作区布局；画布已重新获得主区域。")
            self._schedule_preview_fit()

    def _build_resource_dock(self) -> None:
        dock = QDockWidget("资源浏览器", self)
        dock.setObjectName("ResourceBrowserDock")
        holder = QWidget()
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(8, 8, 8, 8)
        self.resource_tree = QTreeView()
        self.resource_model = QStandardItemModel()
        self.resource_model.setHorizontalHeaderLabels(["动画三件套"])
        self.resource_tree.setModel(self.resource_model)
        self.resource_tree.setHeaderHidden(False)
        self.resource_tree.clicked.connect(self.on_resource_selected)
        layout.addWidget(self.resource_tree)
        dock.setWidget(holder)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)

    def _build_animation_navigator_dock(self) -> None:
        dock = QDockWidget("动画", self)
        dock.setObjectName("AnimationNavigatorDock")
        self.animation_navigator = AnimationNavigator()
        self.animation_navigator.on_animation_selected = self._select_animation_from_navigator
        dock.setWidget(self.animation_navigator)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        self.tabifyDockWidget(self.findChild(QDockWidget, "ResourceBrowserDock"), dock)

    def _select_animation_from_navigator(self, element_index: int) -> None:
        if self.workspace is None:
            return
        self.select_element(self.display_document.elements[element_index])

    def _build_inspector_dock(self) -> None:
        dock = QDockWidget("检查器", self)
        dock.setObjectName("InspectorDock")
        holder = QWidget()
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(10, 10, 10, 10)
        self.inspector_name = QLabel("未选择元素")
        self.inspector_name.setStyleSheet("font-size: 12pt; font-weight: 700;")
        self.inspector_type = QLabel("")
        self.inspector_type.setProperty("muted", True)
        layout.addWidget(self.inspector_name)
        layout.addWidget(self.inspector_type)
        form_holder = QWidget()
        self.inspector_form = QFormLayout(form_holder)
        self.inspector_form.setContentsMargins(0, 14, 0, 0)
        self.inspector_form.setSpacing(9)
        layout.addWidget(form_holder)
        self.edit_panel = QFrame()
        self.edit_panel.setProperty("card", True)
        edit_layout = QFormLayout(self.edit_panel)
        edit_layout.setContentsMargins(9, 9, 9, 9)
        edit_layout.setSpacing(6)
        self.edit_target_label = QLabel("选择动画后，槽位中的首个活动关键帧会加载到此处。")
        self.edit_target_label.setWordWrap(True)
        self.edit_target_label.setProperty("muted", True)
        edit_layout.addRow(self.edit_target_label)
        self.keyframe_spin = QSpinBox()
        self.keyframe_spin.valueChanged.connect(self._load_keyframe_into_editor)
        edit_layout.addRow("BELE 关键帧", self.keyframe_spin)
        self.xform_controls: dict[str, QDoubleSpinBox] = {}
        for field in ("xx", "xy", "yx", "yy", "x", "y"):
            control = QDoubleSpinBox()
            control.setRange(-100000.0, 100000.0)
            control.setDecimals(5)
            control.setSingleStep(0.25 if field in ("x", "y") else 0.05)
            self.xform_controls[field] = control
            edit_layout.addRow(field, control)
        self.alpha_spin = QSpinBox()
        self.alpha_spin.setRange(0, 255)
        edit_layout.addRow("Alpha (ARGB)", self.alpha_spin)
        self.initial_phase_spin = QSpinBox()
        self.initial_phase_spin.setRange(0, 1_000_000)
        self.initial_phase_spin.setToolTip("BELE +0x1C。对嵌套子动画的初始槽位具有强支持证据；保存前会重解析。")
        edit_layout.addRow("初始相位 initial_phase", self.initial_phase_spin)
        self.playback_mode_label = QLabel("playback_mode：读取后显示")
        self.playback_mode_label.setProperty("muted", True)
        self.playback_mode_label.setWordWrap(True)
        edit_layout.addRow(self.playback_mode_label)
        self.keyframe_scope_label = QLabel("静态复用范围：等待选择 BELE。")
        self.keyframe_scope_label.setProperty("muted", True)
        self.keyframe_scope_label.setWordWrap(True)
        edit_layout.addRow("静态复用警戒", self.keyframe_scope_label)
        self.apply_keyframe_button = QPushButton("应用关键帧到暂存预览")
        self.apply_keyframe_button.setProperty("primary", True)
        self.apply_keyframe_button.clicked.connect(self._apply_keyframe_edit)
        edit_layout.addRow(self.apply_keyframe_button)
        self.anchor_x_spin = QDoubleSpinBox()
        self.anchor_y_spin = QDoubleSpinBox()
        for control in (self.anchor_x_spin, self.anchor_y_spin):
            control.setRange(-100000.0, 100000.0)
            control.setDecimals(3)
            control.setSingleStep(0.5)
        self.anchor_x_spin.valueChanged.connect(lambda _value: self._sync_preview_hotspot_from_inspector())
        self.anchor_y_spin.valueChanged.connect(lambda _value: self._sync_preview_hotspot_from_inspector())
        edit_layout.addRow("精灵锚点 X", self.anchor_x_spin)
        edit_layout.addRow("精灵锚点 Y", self.anchor_y_spin)
        self.apply_anchor_button = QPushButton("应用锚点到暂存预览")
        self.apply_anchor_button.clicked.connect(self._apply_anchor_edit)
        edit_layout.addRow(self.apply_anchor_button)
        self.anchor_live_label = QLabel("可直接拖动画布上的热点；拖动过程中只更新坐标，松开鼠标后才提交一次暂存编辑。")
        self.anchor_live_label.setWordWrap(True)
        self.anchor_live_label.setProperty("muted", True)
        edit_layout.addRow(self.anchor_live_label)
        layout.addWidget(self.edit_panel)
        layout.addStretch(1)
        self.edit_hint = QLabel("所有编辑在内存暂存中通过完整 BILE 重解析后才预览；“导出待提交补丁”还会检查源 SHA-256、引用图和 initial_phase 对应的子动画帧范围。")
        self.edit_hint.setWordWrap(True)
        self.edit_hint.setProperty("muted", True)
        layout.addWidget(self.edit_hint)
        dock.setWidget(holder)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

    def _build_track_inspector_dock(self) -> None:
        dock = QDockWidget("轨道检查器", self)
        dock.setObjectName("TrackInspectorDock")
        self.track_inspector = TrackInspector()
        self.track_inspector.on_track_selected = self._select_track_context
        dock.setWidget(self.track_inspector)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        self.tabifyDockWidget(self.findChild(QDockWidget, "InspectorDock"), dock)

    def _build_timeline_dock(self) -> None:
        dock = QDockWidget("时间线", self)
        dock.setObjectName("TimelineDock")
        self.timeline = TimelineWidget()
        self.timeline.slot_clicked = self.set_slot
        self.timeline.track_region_clicked = self._select_track_region
        dock.setWidget(self.timeline)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)

    def _build_spine_timeline_dock(self) -> None:
        dock = QDockWidget("Spine 动画档案", self)
        dock.setObjectName("SpineTimelineDock")
        self.spine_timeline_inspector = SpineTimelineInspector()
        self.spine_timeline_inspector.on_animation_selected = self.select_spine_animation
        dock.setWidget(self.spine_timeline_inspector)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)
        self.tabifyDockWidget(self.findChild(QDockWidget, "TimelineDock"), dock)

    def _build_diagnostics_dock(self) -> None:
        dock = QDockWidget("资源诊断", self)
        dock.setObjectName("DiagnosticsDock")
        self.diagnostic_view = QPlainTextEdit()
        self.diagnostic_view.setReadOnly(True)
        self.diagnostic_view.setPlainText("打开 BILE 三件套后显示结构、图集和播放字段诊断。")
        dock.setWidget(self.diagnostic_view)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        self.tabifyDockWidget(self.findChild(QDockWidget, "InspectorDock"), dock)

    def _build_change_ledger_dock(self) -> None:
        dock = QDockWidget("变更账本与预检", self)
        dock.setObjectName("ChangeLedgerDock")
        self.change_ledger = ChangeLedger()
        dock.setWidget(self.change_ledger)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        self.tabifyDockWidget(self.findChild(QDockWidget, "InspectorDock"), dock)

    def _update_change_ledger(self) -> None:
        if not hasattr(self, "change_ledger"):
            return
        if self.workspace is None or self.edit_session is None:
            self.change_ledger.clear()
            return
        proposal_source = self.active_bile_scene_proposal.source_bin_sha256 if self.active_bile_scene_proposal is not None else None
        self.change_ledger.refresh(self.display_document, self.edit_session, self.workspace.atlas, proposal_source=proposal_source)

    def _diagnostic_text(self) -> str:
        if self.workspace is None:
            return "打开 BILE 三件套后显示结构、图集和播放字段诊断。"
        text = format_diagnostics(self.display_document, self.workspace.atlas)
        return text + ("\n\n" + self.formation_config_text if self.formation_config_text else "")

    def _update_diagnostics(self) -> None:
        self.diagnostic_view.setPlainText(self._diagnostic_text())

    def export_diagnostics_dialog(self) -> None:
        if self.workspace is None:
            QMessageBox.information(self, "尚未加载资源", "请先打开一个 BILE 三件套。")
            return
        path, _ = QFileDialog.getSaveFileName(self, "导出资源诊断", str(self.workspace.bin_path.with_suffix(".diagnostics.txt")), "Text (*.txt)")
        if not path:
            return
        Path(path).write_text(self._diagnostic_text() + "\n", encoding="utf-8")
        self.statusBar().showMessage(f"已导出资源诊断：{Path(path).name}")

    def _set_empty_state(self) -> None:
        self.formation_config_text = ""
        self.resource_model.removeRows(0, self.resource_model.rowCount())
        self.timeline.set_element(None)
        self.preview.clear_hotspot()
        self._preview_element_index = None
        self._populate_inspector(None)
        self._refresh_command_availability()

    def _set_editor_enabled(self, keyframe: bool, anchor: bool) -> None:
        self.keyframe_spin.setEnabled(keyframe)
        for control in self.xform_controls.values():
            control.setEnabled(keyframe)
        self.alpha_spin.setEnabled(keyframe)
        self.initial_phase_spin.setEnabled(keyframe)
        self.apply_keyframe_button.setEnabled(keyframe)
        self.anchor_x_spin.setEnabled(anchor)
        self.anchor_y_spin.setEnabled(anchor)
        self.apply_anchor_button.setEnabled(anchor)

    def save_pending_patch_dialog(self) -> None:
        if self.edit_session is None or not self.edit_session.dirty:
            QMessageBox.information(self, "没有待提交编辑", "请先在检查器中应用关键帧或锚点编辑。")
            return
        path, _ = QFileDialog.getSaveFileName(self, "导出待提交补丁", str(self.workspace.bin_path.with_suffix(".patch.json")), "JSON (*.json)")
        if not path:
            return
        try:
            report = run_preflight(self.edit_session, self.workspace.atlas)
            if report.has_errors:
                QMessageBox.critical(self, "保存前检查未通过", report.text)
                return
            self.edit_session.write_patch(path)
            warnings = sum(item.severity == "WARNING" for item in report.items)
            suffix = f"，{warnings} 项警告" if warnings else ""
            self.statusBar().showMessage(f"保存前检查通过{suffix}；已导出 {self.edit_session.change_count} 项待提交编辑：{Path(path).name}")
        except (OSError, BileFormatError, ValueError) as exc:
            QMessageBox.critical(self, "保存前检查失败", str(exc))

    def clear_pending_edits(self) -> None:
        if self.edit_session is None or self.workspace is None:
            return
        if self.document_session is not None:
            self.document_session.clear_edits()
        else:
            self.edit_session.clear()
        self._update_diagnostics()
        if self.selected_element is not None:
            index = self.selected_element.index
            self.selected_element = self.display_document.elements[index]
            self.timeline.set_element(self.selected_element if not self.selected_element.has_texture else None)
            self._populate_inspector(self.selected_element)
            self.set_slot(self.slot_slider.value())
        self.statusBar().showMessage("已撤销所有待提交编辑并恢复原始 BIN。")

    def _restore_session_preview(self, status: str) -> None:
        if self.workspace is None or self.edit_session is None or self.selected_element is None:
            return
        try:
            if self.document_session is not None:
                # 命令会话已在执行、撤销或重做时重解析；这里只消费统一快照。
                _ = self.document_session.snapshot
            else:
                raise DocumentSessionError("缺少动画文档会话")
            self._update_diagnostics()
            selected_index = self.selected_element.index
            self.selected_element = self.display_document.elements[selected_index]
            self.timeline.set_element(self.selected_element if not self.selected_element.has_texture else None)
            self._populate_inspector(self.selected_element)
            self.set_slot(self.slot_slider.value())
            self.statusBar().showMessage(status)
        except (OSError, BileFormatError, ValueError) as exc:
            QMessageBox.critical(self, "无法恢复暂存编辑", str(exc))

    def undo_pending_edit(self) -> None:
        if self.document_session is not None and self.document_session.undo():
            self._restore_session_preview(f"已撤销；待提交变更 {self.document_session.snapshot.change_count} 项。")

    def redo_pending_edit(self) -> None:
        if self.document_session is not None and self.document_session.redo():
            self._restore_session_preview(f"已重做；待提交变更 {self.document_session.snapshot.change_count} 项。")

    def _candidate_workflow(self) -> CandidateWorkflow:
        if self.workspace is None or self.edit_session is None:
            raise CandidateWorkflowError("尚未加载可编辑的 BILE 三件套")
        return CandidateWorkflow(
            self.workspace.bin_path,
            self.workspace.xml_path,
            self.workspace.image_path,
            self.workspace.atlas,
            self.edit_session,
        )

    def create_candidate_diff_dialog(self) -> None:
        if self.workspace is None or self.edit_session is None or not self.edit_session.dirty or self.selected_element is None or self.selected_element.has_texture:
            QMessageBox.information(self, "无法生成候选差异", "请选择一个动画元素，并先完成至少一项暂存编辑。")
            return
        output_dir = QFileDialog.getExistingDirectory(self, "选择候选差异报告目录", str(self.workspace.bin_path.parent))
        if not output_dir:
            return
        try:
            result = self._candidate_workflow().create_diff(self.selected_element.name, output_dir)
            self.statusBar().showMessage(f"候选差异已生成：{result.changed_slots} 个可见变化槽位，{result.binary_change_count} 个保守字段变化。")
            QMessageBox.information(self, "候选差异已生成", f"JSON：{result.report_path}\nMarkdown：{result.markdown_path}\n\n可见变化槽位：{result.changed_slots}\n保守字段变化：{result.binary_change_count}")
        except (OSError, CandidateWorkflowError, ValueError, KeyError, BileFormatError) as exc:
            QMessageBox.critical(self, "候选差异生成失败", str(exc))

    def export_track_impact_dialog(self) -> None:
        if self.workspace is None or self.edit_session is None or not self.edit_session.dirty:
            QMessageBox.information(self, "没有待取证的关键帧编辑", "请先应用至少一项 BELE 关键帧编辑。锚点编辑不使用轨道引用范围表。")
            return
        output_dir = QFileDialog.getExistingDirectory(self, "选择轨道影响范围报告目录", str(self.workspace.bin_path.parent))
        if not output_dir:
            return
        try:
            evidence = self._candidate_workflow().create_track_impact_evidence(output_dir)
            self.statusBar().showMessage(f"已导出 {len(evidence.impacts)} 个 BELE 的静态轨道影响范围：{evidence.markdown_path.name}")
            QMessageBox.information(
                self,
                "轨道影响范围已导出",
                f"JSON：{evidence.json_path}\nMarkdown：{evidence.markdown_path}\n\n"
                "报告只描述原始文档的静态引用范围。请与候选像素差异和游戏内回归证据结合判断。",
            )
        except (OSError, CandidateWorkflowError, ValueError, BileFormatError) as exc:
            QMessageBox.critical(self, "轨道影响范围导出失败", str(exc))

    def create_regression_case_dialog(self) -> None:
        if self.workspace is None or self.edit_session is None or not self.edit_session.dirty or self.selected_element is None or self.selected_element.has_texture:
            QMessageBox.information(self, "无法创建回归案例", "请选择一个动画元素，并先完成至少一项暂存编辑。")
            return
        root = QFileDialog.getExistingDirectory(self, "选择回归案例保存目录", str(self.workspace.bin_path.parent))
        if not root:
            return
        case_dir = Path(root) / f"{self.workspace.bin_path.stem}_{self.selected_element.name}_regression"
        if case_dir.exists() and any(case_dir.iterdir()):
            QMessageBox.warning(self, "案例目录已存在", f"为避免覆盖已有证据，请选择其他目录或先移动：{case_dir}")
            return
        try:
            result = self._candidate_workflow().create_regression_case(
                case_dir, self.selected_element.name, [self.slot_slider.value()]
            )
            self.statusBar().showMessage(f"已创建待验证回归案例：{result.case_dir.name}")
            QMessageBox.information(self, "回归案例已创建", f"目录：{result.case_dir}\n\n其中包含候选 BIN 副本、差异报告、实验包和待填写的回归清单。游戏内截图或录屏可通过“回归”菜单登记。")
        except (OSError, CandidateWorkflowError, ValueError, KeyError, BileFormatError) as exc:
            QMessageBox.critical(self, "回归案例创建失败", str(exc))

    def open_formation_config_dialog(self) -> None:
        if self.workspace is None:
            QMessageBox.information(self, "尚未加载资源", "请先加载目标 BILE 三件套，再为该实验上下文附加可选 def_array.xml。")
            return
        try:
            result = select_formation_config(self, self.workspace.bin_path.parent)
            if result is None:
                return
            self.formation_config_text = result.text
            self._update_diagnostics()
            self.statusBar().showMessage(f"已加载只读阵列摘要：{result.config.source_name}")
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "无法读取阵列配置", str(exc))

    def create_composition_experiment_dialog(self) -> None:
        if self.workspace is None or self.selected_element is None or self.selected_element.has_texture:
            QMessageBox.information(self, "无法创建组合实验", "请先选择当前目标三件套中的一个动画元素。该元素将作为目标 def_motion 根动作。")
            return
        try:
            dialog_result = create_composition_experiment_from_dialog(
                self, self.workspace, self.selected_element, self.slot_slider.value()
            )
            if dialog_result is None:
                return
            result = dialog_result.result
            self.statusBar().showMessage(f"跨游戏组合实验包已生成：{result.archive_path.name}")
            QMessageBox.information(
                self,
                "组合实验已生成",
                f"ZIP：{result.archive_path}\n清单：{result.manifest_path}\n绑定配方：{result.binding_recipe_path}\n回归案例：{dialog_result.case_dir}\n\n"
                "候选 XML 仅在存在 Texture.name 时改为目标图像名；其余运行时配置不自动修改。请固定实验条件并按配方手工绑定候选根动作。",
            )
        except (OSError, ValueError, KeyError, BileFormatError) as exc:
            QMessageBox.critical(self, "组合实验生成失败", str(exc))

    def add_regression_evidence_dialog(self) -> None:
        case_dir = QFileDialog.getExistingDirectory(self, "选择已有回归案例目录")
        if not case_dir:
            return
        evidence_path, _ = QFileDialog.getOpenFileName(self, "选择游戏内截图、录屏或日志", "", "Media and logs (*.png *.jpg *.jpeg *.webp *.gif *.mp4 *.webm *.txt *.log);;All files (*)")
        if not evidence_path:
            return
        kind, ok = QInputDialog.getItem(self, "证据类型", "请选择证据类型：", ["screenshot", "video", "log", "other"], 0, False)
        if not ok:
            return
        note, ok = QInputDialog.getText(self, "证据说明", "说明（可留空）：")
        if not ok:
            return
        try:
            copied = add_evidence(case_dir, evidence_path, kind, note)
            self.statusBar().showMessage(f"已登记游戏内证据：{copied.name}")
            QMessageBox.information(self, "证据已登记", f"证据副本：{copied}\n案例 README 已更新。")
        except (OSError, ValueError, FileNotFoundError) as exc:
            QMessageBox.critical(self, "证据登记失败", str(exc))

    def export_animation_evidence_dialog(self) -> None:
        if self.workspace is None or self.selected_element is None or self.selected_element.has_texture:
            QMessageBox.information(self, "无法导出动画档案", "请选择一个动画元素。档案只描述已解析的静态 Track 引用，不推断游戏内实例数量。")
            return
        output_dir = QFileDialog.getExistingDirectory(self, "选择动画静态档案目录", str(self.workspace.bin_path.parent))
        if not output_dir:
            return
        try:
            evidence = write_animation_evidence(self.display_document, self.selected_element.index, output_dir)
            self.statusBar().showMessage(f"已导出 {evidence.animation_name} 的静态档案：{evidence.markdown_path.name}")
            QMessageBox.information(
                self,
                "动画静态档案已导出",
                f"JSON：{evidence.json_path}\nMarkdown：{evidence.markdown_path}\n\n"
                "档案记录槽位覆盖、BELE 复用与静态 Track 引用；它不等同于游戏内单位人数或引擎实例数。",
            )
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "动画档案导出失败", str(exc))

    def export_sequence_dialog(self) -> None:
        if self.workspace is None or self.selected_element is None or self.selected_element.has_texture:
            QMessageBox.information(self, "无法导出动画序列", "请选择一个动画元素。")
            return
        default = self.workspace.bin_path.with_name(f"{self.workspace.bin_path.stem}_{self.selected_element.name}_animation.gif")
        path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "导出完整动画序列",
            str(default),
            "Animated GIF (*.gif);;Animated PNG / APNG (*.png);;PNG frame sequence directory (*.frames)",
        )
        if not path:
            return
        kind = "gif" if selected_filter.startswith("Animated GIF") else "apng" if selected_filter.startswith("Animated PNG") else "png-sequence"
        try:
            result = export_sequence(
                self.display_document,
                self.workspace.atlas,
                self.selected_element.name,
                path,
                kind,
                canvas_size=(512, 384),
                transparent=(kind == "apng"),
            )
            self.statusBar().showMessage(f"已导出 {result.frame_count} 帧 {kind}：{result.output_paths[0].name}")
        except (OSError, ValueError, KeyError) as exc:
            QMessageBox.critical(self, "动画序列导出失败", str(exc))

    def create_experiment_package_dialog(self) -> None:
        if self.workspace is None or self.edit_session is None or not self.edit_session.dirty:
            QMessageBox.information(self, "没有待验证编辑", "请先完成暂存编辑；实验包只会包含通过预检的候选 BIN。")
            return
        archive_path, _ = QFileDialog.getSaveFileName(
            self,
            "生成游戏内实验包",
            str(self.workspace.bin_path.with_name(self.workspace.bin_path.stem + "_game_experiment.zip")),
            "ZIP archive (*.zip)",
        )
        if not archive_path:
            return
        try:
            result = self._candidate_workflow().create_experiment_package(archive_path)
            warning_text = f"；{len(result.warnings)} 项警告" if result.warnings else ""
            self.statusBar().showMessage(f"实验包已生成：{result.archive_path.name}；已回读验证 {result.checked_animations} 个动画{warning_text}")
            QMessageBox.information(self, "实验包已生成", f"ZIP：{result.archive_path}\n验证报告：{result.report_path}\n\n请备份游戏内同名三件套后再手工替换。")
        except (OSError, CandidateWorkflowError, ValueError, KeyError, BileFormatError) as exc:
            QMessageBox.critical(self, "实验包生成失败", str(exc))

    def export_frame_comparison_dialog(self) -> None:
        if self.workspace is None or self.selected_element is None or self.selected_element.has_texture:
            QMessageBox.information(self, "无法导出对比", "请选择一个动画元素。")
            return
        default = self.workspace.bin_path.with_name(f"{self.workspace.bin_path.stem}_slot{self.slot_slider.value()}_compare.png")
        path, _ = QFileDialog.getSaveFileName(self, "导出原始/暂存对比图", str(default), "PNG Image (*.png)")
        if not path:
            return
        try:
            original = parse_file(self.workspace.bin_path)
            slot = self.slot_slider.value()
            before = render_frame(original, self.workspace.atlas, self.selected_element.name, slot)
            after = render_frame(self.display_document, self.workspace.atlas, self.selected_element.name, slot)
            header = 28
            comparison = Image.new("RGBA", (before.width * 2, before.height + header), (24, 27, 32, 255))
            comparison.alpha_composite(before, (0, header))
            comparison.alpha_composite(after, (before.width, header))
            drawing = ImageDraw.Draw(comparison)
            drawing.text((10, 8), "Original", fill=(231, 234, 240, 255))
            drawing.text((before.width + 10, 8), "Staged preview", fill=(231, 234, 240, 255))
            comparison.save(path)
            self.statusBar().showMessage(f"已导出槽位 {slot} 的原始/暂存对比：{Path(path).name}")
        except (OSError, BileFormatError, KeyError, ValueError) as exc:
            QMessageBox.critical(self, "对比导出失败", str(exc))

    def export_json_dialog(self) -> None:
        if self.workspace is None:
            QMessageBox.information(self, "尚未加载资源", "请先打开一个 BILE 三件套。")
            return
        path, _ = QFileDialog.getSaveFileName(self, "导出 AI 中转 JSON", str(self.workspace.bin_path.with_suffix(".bile.json")), "JSON (*.json)")
        if not path:
            return
        try:
            export_interchange(self.workspace.bin_path, path)
            self.statusBar().showMessage(f"已导出中转 JSON：{Path(path).name}")
        except (OSError, BileFormatError, ValueError) as exc:
            QMessageBox.critical(self, "导出失败", str(exc))

    def export_scene_interchange_dialog(self) -> None:
        if self.workspace is None:
            QMessageBox.information(self, "尚未加载资源", "请先打开一个 BILE 三件套。")
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出 BILE Scene Interchange v1（只读）",
            str(self.workspace.bin_path.with_suffix(".bile.scene.json")),
            "JSON (*.json)",
        )
        if not path:
            return
        try:
            payload = export_scene_interchange(
                self.workspace.bin_path,
                self.workspace.xml_path,
                self.workspace.image_path,
                path,
                include_render_witnesses=True,
            )
            coverage = payload.get("render_witnesses", {}).get("animation_coverage", {})
            selected = coverage.get("selected_animation_count", 0)
            total = coverage.get("candidate_animation_count", 0)
            self.statusBar().showMessage(
                f"已导出 BILE Scene Interchange v1（只读）：{Path(path).name}；渲染见证覆盖 {selected}/{total} 个代表动画。"
            )
            QMessageBox.information(
                self,
                "场景中转已导出",
                "已从原始 BILE 三件套导出哈希绑定场景 JSON 和关键槽位渲染见证。\n\n"
                "该文件不包含 BIN 写回权限，也不会应用当前暂存编辑；实验性重建必须走独立、后续验证流程。",
            )
        except (OSError, BileFormatError, ValueError) as exc:
            QMessageBox.critical(self, "场景中转导出失败", str(exc))

    def export_bile_scene_proposal_template_dialog(self) -> None:
        if self.document_session is None or not self.document_session.snapshot.editable:
            QMessageBox.information(self, "BILE 场景提案不可用", "请先加载一个可保守编辑的 BILE v3/v4 三件套；v2 和 Spine 工作区严格只读。")
            return
        default = self.workspace.bin_path.with_suffix(".bile.scene-proposal.json") if self.workspace is not None else Path("bile.scene-proposal.json")
        path, _ = QFileDialog.getSaveFileName(self, "导出 BILE AI 场景安全提案模板", str(default), "JSON (*.json)")
        if not path:
            return
        try:
            payload = bile_scene_proposal_template(self.document_session)
            Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self.statusBar().showMessage(f"已导出哈希绑定的 BILE AI 场景候选模板：{Path(path).name}；它没有直接写回权限。")
        except (OSError, BileSceneProposalError) as exc:
            QMessageBox.critical(self, "BILE 场景提案模板导出失败", str(exc))

    def load_bile_scene_proposal_dialog(self) -> None:
        if self.document_session is None or not self.document_session.snapshot.editable or self.workspace is None:
            QMessageBox.information(self, "BILE 场景提案不可用", "请先加载一个可保守编辑的 BILE v3/v4 三件套；v2 和 Spine 工作区严格只读。")
            return
        path, _ = QFileDialog.getOpenFileName(self, "加载 BILE AI 场景安全提案（仅暂存）", str(self.workspace.bin_path.parent), "JSON (*.json)")
        if not path:
            return
        try:
            proposal = load_proposal(path)
            applied = apply_scene_proposal(self.document_session, proposal)
            self.active_bile_scene_proposal = proposal
            self.set_slot(self.slot_slider.value())
            self._refresh_command_availability(self.document_session.snapshot)
            self.statusBar().showMessage(f"已暂存 BILE AI 场景提案：{applied} 项白名单变更；原始 BIN 始终未修改。")
            QMessageBox.information(self, "候选提案已暂存", f"已接受 {applied} 项白名单变更。\n\n变更仅存在于当前编辑会话；请通过差异、预检和实验包链路继续验证。源 BIN 未被写入。")
        except BileSceneProposalError as exc:
            QMessageBox.warning(self, "BILE AI 场景提案被拒绝", str(exc))
        except OSError as exc:
            QMessageBox.critical(self, "无法加载 BILE AI 场景提案", str(exc))

    def export_bile_scene_proposal_evidence_dialog(self) -> None:
        if self.document_session is None or self.workspace is None or self.active_bile_scene_proposal is None:
            QMessageBox.information(self, "没有可导出的 BILE 场景提案证据", "请先在当前 BILE v3/v4 会话中加载并暂存一个已验证的场景提案。")
            return
        default = self.workspace.bin_path.with_suffix(".bile.scene-proposal-evidence.json")
        path, _ = QFileDialog.getSaveFileName(self, "导出 BILE AI 场景提案证据", str(default), "JSON (*.json)")
        if not path:
            return
        try:
            export_bile_scene_proposal_evidence(path, self.document_session, self.active_bile_scene_proposal)
            self.statusBar().showMessage(f"已导出 BILE AI 场景提案证据：{Path(path).name}；不包含 BIN 写回。")
        except BileSceneProposalError as exc:
            QMessageBox.warning(self, "BILE 场景提案证据被拒绝", str(exc))

    def apply_patch_dialog(self) -> None:
        if self.workspace is None:
            QMessageBox.information(self, "尚未加载资源", "请先打开一个 BILE 三件套。")
            return
        patch_path, _ = QFileDialog.getOpenFileName(self, "选择安全补丁 JSON", str(self.workspace.bin_path.parent), "JSON (*.json)")
        if not patch_path:
            return
        output_path, _ = QFileDialog.getSaveFileName(self, "另存修改后的 BIN", str(self.workspace.bin_path.with_stem(self.workspace.bin_path.stem + "_edited")), "BILE Animation (*.bin)")
        if not output_path:
            return
        overwrite = False
        if Path(output_path).exists():
            answer = QMessageBox.question(
                self,
                "确认覆盖候选文件",
                f"文件已存在：\n{output_path}\n\n是否原子替换？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
            overwrite = True
        try:
            report = apply_patch_report(
                self.workspace.bin_path,
                patch_path,
                output_path,
                overwrite=overwrite,
            )
            changed_count = len(report.changed_byte_offsets)
            self.statusBar().showMessage(
                f"补丁已验证并写入：{Path(output_path).name}；变化字节 {changed_count}"
            )
            QMessageBox.information(
                self,
                "补丁已写入",
                f"已完成 expected-old、精确 changed-byte set 与结构重解析验证。\n"
                f"变化字节：{changed_count}\n"
                f"候选 SHA-256：{report.output_sha256}\n\n"
                "请在原游戏中继续回归该实验文件。",
            )
        except (OSError, BileFormatError, ValueError) as exc:
            QMessageBox.critical(self, "补丁被拒绝", str(exc))

    def fit_preview(self) -> None:
        """在预览视图已构造后按实际内容适配当前图像。"""
        self.preview.fit_content()

    def zoom_preview_in(self) -> None:
        self.preview.zoom_in()

    def zoom_preview_out(self) -> None:
        self.preview.zoom_out()

    def open_sample(self) -> None:
        sample = Path(__file__).resolve().parents[2] / "sample_assets" / "anim_failure.bin"
        if not sample.exists():
            QMessageBox.warning(self, "示例不可用", "未找到 sample_assets/anim_failure.bin。")
            return
        self.load_workspace(sample)

    def open_cross_game_sample(self) -> None:
        root = Path(__file__).resolve().parents[2] / "cross_game_assets"
        choices = {
            "将军的荣耀3 · anim_fire（BILE v4 / WebP）": root / "general3" / "anim_fire.bin",
            "欧洲战争6 · anim_newui（BILE v4 / PNG / 小数几何）": root / "eu6" / "anim_newui.bin",
            "世界征服者3 · anim_gameover（BILE v3 / PNG）": root / "wc3" / "anim_gameover.bin",
        }
        available = {label: path for label, path in choices.items() if path.exists()}
        if not available:
            QMessageBox.information(self, "验证样本不可用", "未找到 cross_game_assets；仍可通过“打开 BILE”加载任意同名三件套。")
            return
        label, accepted = QInputDialog.getItem(self, "加载跨游戏验证样本", "选择样本：", list(available), 0, False)
        if accepted:
            self.load_workspace(available[label])

    def open_bin_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "打开 BILE 动画", str(Path.home()), "BILE Animation (*.bin)")
        if path:
            self.load_workspace(Path(path))

    def open_spine_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "打开 Spine 静态资源", str(Path.home()), "Spine skeleton (*.bin)")
        if path:
            self.load_spine_workspace(Path(path))

    def export_spine_static_dialog(self) -> None:
        if self.spine_workspace is None:
            QMessageBox.information(self, "尚未加载 Spine 资源", "请先打开欧7或征2的同名 BIN + ATLAS 资源。")
            return
        default = self.spine_workspace.bin_path.with_suffix(".spine-workbench.json")
        path, _ = QFileDialog.getSaveFileName(self, "导出 Spine 结构与动画档案", str(default), "JSON (*.json)")
        if not path:
            return
        try:
            export_static_manifest(self.spine_workspace, Path(path))
            self.statusBar().showMessage(f"已导出 Spine 结构与动画档案：{Path(path).name}")
        except OSError as exc:
            QMessageBox.critical(self, "无法导出 Spine 静态档案", str(exc))

    def _detach_bile_session(self) -> None:
        if self._unsubscribe_document_session is not None:
            self._unsubscribe_document_session()
            self._unsubscribe_document_session = None
        if self.document_session is not None:
            self.document_session.close()
        self.workspace = None
        self.document_session = None
        self.edit_session = None
        self.selected_element = None
        self.active_bile_scene_proposal = None

    def load_spine_workspace(self, bin_path: Path) -> None:
        try:
            spine = load_spine_static_workspace(bin_path)
            self._detach_bile_session()
            self.spine_workspace = spine
            self.spine_pose_session = None
            self.motion_proposal_session = None
            self.spine_pose_time = 0.0
            self.spine_selected_region = spine.atlas.regions[0].name
            self.spine_selected_animation = spine.timeline_archive.animations[0].name if spine.timeline_archive and spine.timeline_archive.animations else None
            self.formation_config_text = ""
            self.play_timer.stop()
            self.play_action.setChecked(False)
            self.resource_model.removeRows(0, self.resource_model.rowCount())
            self._populate_spine_resources()
            self.spine_timeline_inspector.set_archive(spine.timeline_archive, self.spine_selected_animation)
            self.timeline.set_element(None)
            self.animation_navigator.set_document(None, None)
            self._set_editor_enabled(False, False)
            self.edit_panel.setEnabled(False)
            self.keyframe_scope_label.setText("Spine 动画工作区：已完整读取结构与 timeline；不提供任何 BILE BELE 或 Spine 写回编辑。")
            self.inspector_name.setText("Spine 动画资源")
            self.inspector_type.setText("严格只读 · skeleton / animations / ATLAS regions")
            self.diagnostic_view.setPlainText(spine_diagnostics_text(spine))
            self.title_label.setText(bin_path.stem)
            timeline_note = f"{len(spine.timeline_archive.animations)} 动画根 · {spine.timeline_count} 条 timeline" if spine.timeline_archive else "动画段未通过严格读取"
            self.subtitle_label.setText(f"{spine.engine} · Spine {spine.document.header.version} · {len(spine.document.bones)} 骨骼 · {len(spine.document.slots)} 插槽 · {timeline_note} · {len(spine.atlas.regions)} 图集区域")
            self.document_status_label.setText(f"文档状态 · Spine {spine.document.header.version} · 完整结构与时间线严格只读 · {timeline_note}")
            self.status_document_label.setText(f"Spine {spine.document.header.version} · 只读结构与动画档案")
            self.status_context_label.setText(f"ATLAS · {spine.atlas.dialect} · 区域 {self.spine_selected_region}")
            self.select_spine_region(self.spine_selected_region)
            self.select_spine_animation(self.spine_selected_animation)
            self._refresh_productivity_context()
            self.ribbon.select_tab("spine")
            self._refresh_command_availability()
            self.statusBar().showMessage(f"已加载 {spine.engine} Spine 工作区：{bin_path.name}；可审阅首批 bone/slot pose，未支持 runtime 特性会明确降级。")
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "无法打开 Spine 静态资源", str(exc))
            self.statusBar().showMessage("Spine 加载失败：文件未被修改")

    def _populate_spine_resources(self) -> None:
        assert self.spine_workspace is not None
        root = QStandardItem(self.spine_workspace.bin_path.name)
        root.setEditable(False)
        skeleton = QStandardItem(f"静态骨架（{len(self.spine_workspace.document.bones)} 骨骼 / {len(self.spine_workspace.document.slots)} 插槽）")
        animation_group = QStandardItem(f"动画档案（{len(self.spine_workspace.timeline_archive.animations) if self.spine_workspace.timeline_archive else 0}）")
        atlas_group = QStandardItem(f"ATLAS 区域（{len(self.spine_workspace.atlas.regions)}）")
        for bone in self.spine_workspace.document.bones:
            item = QStandardItem(f"骨骼 · {bone.index:02d} · {bone.name}")
            item.setEditable(False)
            skeleton.appendRow(item)
        for slot in self.spine_workspace.document.slots:
            item = QStandardItem(f"插槽 · {slot.index:02d} · {slot.name}")
            item.setEditable(False)
            skeleton.appendRow(item)
        if self.spine_workspace.timeline_archive is not None:
            for animation in self.spine_workspace.timeline_archive.animations:
                item = QStandardItem(f"{animation.name} · {animation.duration:.3f}s · {len(animation.timelines)} 条 timeline")
                item.setEditable(False)
                item.setData("spine_animation", ROLE_KIND)
                item.setData(animation.name, ROLE_INDEX)
                animation_group.appendRow(item)
        for region in self.spine_workspace.atlas.regions:
            item = QStandardItem(region.name)
            item.setEditable(False)
            item.setData("spine_region", ROLE_KIND)
            item.setData(region.name, ROLE_INDEX)
            atlas_group.appendRow(item)
        root.appendRow(skeleton)
        if animation_group.rowCount():
            root.appendRow(animation_group)
        root.appendRow(atlas_group)
        self.resource_model.appendRow(root)
        self.resource_tree.expandAll()

    def select_spine_animation(self, name: str | None) -> None:
        if self.spine_workspace is None or self.spine_workspace.timeline_archive is None or not name:
            return
        animation = next((item for item in self.spine_workspace.timeline_archive.animations if item.name == name), None)
        if animation is None:
            return
        try:
            self.spine_pose_session = create_pose_session(self.spine_workspace, name)
            self.motion_proposal_session = MotionProposalSession(self.spine_pose_session)
        except ValueError as exc:
            self.spine_pose_session = None
            self.motion_proposal_session = None
            self.statusBar().showMessage(f"Spine pose 审阅不可用：{exc}")
            return
        self.spine_selected_animation = name
        self.spine_pose_time = 0.0
        self.spine_timeline_inspector.set_archive(self.spine_workspace.timeline_archive, name)
        for control in (self.slot_slider, self.slot_spin):
            control.blockSignals(True)
            control.setRange(0, 1000)
            control.setValue(0)
            control.setEnabled(True)
            control.blockSignals(False)
        self.inspector_name.setText(name)
        self.inspector_type.setText(f"Spine animation · {animation.duration:.3f} s · {len(animation.timelines)} 条 timeline · pose 严格只读")
        self._render_spine_pose_time(0.0)
        self._refresh_command_availability()

    def _render_spine_pose_time(self, time: float) -> None:
        if self.spine_pose_session is None:
            return
        try:
            proposal_diagnostics: tuple[str, ...] = ()
            if self.motion_proposal_session is not None and self.motion_proposal_session.active_proposals:
                proposal_preview = self.motion_proposal_session.preview(time)
                projection, rendered = proposal_preview.projection, proposal_preview.rendered
                proposal_diagnostics = proposal_preview.proposal_diagnostics
            else:
                projection, rendered = self.spine_pose_session.preview(time)
            self.spine_pose_time = projection.effective_time
            self.preview.set_image(rendered.image, fit=not self.preview._has_content)
            self.slot_label.setText(f"Spine 时间 {projection.effective_time:.3f} / {projection.duration:.3f} s")
            coverage = "完整子集" if projection.coverage_complete else f"部分预览 · {len(rendered.diagnostics)} 项降级"
            self.inspector_name.setText(projection.animation_name)
            self.inspector_type.setText(f"Spine pose · {rendered.rendered_layer_count} layer · {coverage} · 严格只读")
            self.status_context_label.setText(f"Spine pose · {projection.animation_name} · {projection.effective_time:.3f}s · {rendered.rendered_layer_count} layer · {coverage}")
            all_diagnostics = tuple(dict.fromkeys(proposal_diagnostics + rendered.diagnostics))
            deform_audit = deform_audit_text(self.spine_pose_session.workspace.document, self.spine_pose_session.animation)
            if all_diagnostics:
                pose_note = "Pose 预览降级诊断：\n" + "\n".join(f"- {item}" for item in all_diagnostics)
            else:
                pose_note = "Pose 预览覆盖：当前 animation/time 已覆盖首批支持子集。"
            self.diagnostic_view.setPlainText(spine_diagnostics_text(self.spine_pose_session.workspace) + "\n\n" + deform_audit + "\n\n" + pose_note)
        except (ValueError, OSError) as exc:
            self.statusBar().showMessage(f"Spine pose 预览失败：{exc}")

    def export_motion_template_dialog(self) -> None:
        if self.spine_pose_session is None:
            QMessageBox.information(self, "尚未选择可预览 Spine 动画", "请先加载 Spine 资源并选择一个已完整读取时间线的动画根。")
            return
        default = self.spine_pose_session.workspace.bin_path.with_name(f"{self.spine_pose_session.workspace.bin_path.stem}_{self.spine_pose_session.animation.name}.motion-proposal.json")
        path, _ = QFileDialog.getSaveFileName(self, "导出 AI Motion DSL 模板", str(default), "Motion Proposal JSON (*.json)")
        if not path:
            return
        try:
            Path(path).write_text(json.dumps(proposal_template(self.spine_pose_session), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self.statusBar().showMessage(f"已导出与当前 BIN SHA-256 绑定的 AI Motion DSL 模板：{Path(path).name}")
        except OSError as exc:
            QMessageBox.critical(self, "无法导出 AI Motion DSL 模板", str(exc))

    def load_motion_proposal_dialog(self) -> None:
        if self.spine_pose_session is None or self.motion_proposal_session is None:
            QMessageBox.information(self, "尚未选择可预览 Spine 动画", "请先加载 Spine 资源并选择一个已完整读取时间线的动画根。")
            return
        path, _ = QFileDialog.getOpenFileName(self, "加载 AI Motion DSL 只读提案", str(self.spine_pose_session.workspace.bin_path.parent), "Motion Proposal JSON (*.json)")
        if not path:
            return
        try:
            proposal = load_motion_proposal(Path(path), self.spine_pose_session)
            self.motion_proposal_session.apply(proposal)
            self.set_slot(self.slot_slider.value())
            self._refresh_command_availability()
            self.statusBar().showMessage(f"已在内存应用只读提案：{proposal.name}；未修改 Spine BIN。")
        except MotionDslError as exc:
            QMessageBox.warning(self, "AI Motion DSL 提案被拒绝", str(exc))

    def undo_motion_proposal(self) -> None:
        if self.motion_proposal_session is None:
            return
        proposal = self.motion_proposal_session.undo()
        if proposal is not None:
            self.set_slot(self.slot_slider.value())
            self._refresh_command_availability()
            self.statusBar().showMessage(f"已撤销内存 pose 提案：{proposal.name}；Spine BIN 始终未修改。")

    def redo_motion_proposal(self) -> None:
        if self.motion_proposal_session is None:
            return
        proposal = self.motion_proposal_session.redo()
        if proposal is not None:
            self.set_slot(self.slot_slider.value())
            self._refresh_command_availability()
            self.statusBar().showMessage(f"已重做内存 pose 提案：{proposal.name}；Spine BIN 始终未修改。")

    def export_motion_evidence_dialog(self) -> None:
        if self.motion_proposal_session is None:
            QMessageBox.information(self, "尚未选择可预览 Spine 动画", "请先加载 Spine 资源并选择一个已完整读取时间线的动画根。")
            return
        pose_session = self.motion_proposal_session.pose_session
        default = pose_session.workspace.bin_path.with_name(f"{pose_session.workspace.bin_path.stem}_{pose_session.animation.name}.motion-evidence.json")
        path, _ = QFileDialog.getSaveFileName(self, "导出 AI Motion DSL pose 证据", str(default), "JSON (*.json)")
        if not path:
            return
        try:
            export_proposal_evidence(Path(path), self.motion_proposal_session)
            self.statusBar().showMessage(f"已导出只读 pose 提案证据：{Path(path).name}")
        except (OSError, MotionDslError) as exc:
            QMessageBox.critical(self, "无法导出 AI Motion DSL 证据", str(exc))

    def export_spine_deform_evidence_dialog(self) -> None:
        if self.spine_pose_session is None:
            QMessageBox.information(self, "尚未选择可预览 Spine 动画", "请先加载通过完整 timeline 读取的 Spine 资源并选择一个动画根。")
            return
        default = self.spine_pose_session.workspace.bin_path.with_name(f"{self.spine_pose_session.workspace.bin_path.stem}_{self.spine_pose_session.animation.name}.deform-audit.json")
        path, _ = QFileDialog.getSaveFileName(self, "导出 Spine deform 审计证据", str(default), "JSON (*.json)")
        if not path:
            return
        try:
            output = export_deform_audit_evidence(self.spine_pose_session, Path(path))
            self.statusBar().showMessage(f"已导出 Spine deform 只读审计证据：{output.name}")
        except OSError as exc:
            QMessageBox.critical(self, "无法导出 Spine deform 审计证据", str(exc))

    def export_spine_two_color_evidence_dialog(self) -> None:
        if self.spine_pose_session is None:
            QMessageBox.information(self, "尚未选择可审阅 Spine 动画", "请先加载通过完整 timeline 读取的 Spine 资源并选择一个动画根。该导出只记录已消费的 light/dark 通道证据，不应用像素或渲染。")
            return
        default = self.spine_pose_session.workspace.bin_path.with_name(f"{self.spine_pose_session.workspace.bin_path.stem}_{self.spine_pose_session.animation.name}.two-color-audit.json")
        path, _ = QFileDialog.getSaveFileName(self, "导出 Spine dark/two-color 审计证据", str(default), "JSON (*.json)")
        if not path:
            return
        try:
            output = export_two_color_timeline_evidence(self.spine_pose_session, Path(path))
            self.statusBar().showMessage(f"已导出 Spine dark/two-color raw evidence：{output.name}；未应用像素、未渲染、未写回 BIN。")
        except OSError as exc:
            QMessageBox.critical(self, "无法导出 Spine dark/two-color 审计证据", str(exc))

    def export_spine_sequence_time_audit_evidence_dialog(self) -> None:
        if self.spine_pose_session is None or self.spine_pose_session.workspace.engine != "spine41":
            QMessageBox.information(self, "当前资源不支持 sequence 时间审计", "请先加载通过完整时间线读取的 Spine 4.1 资源并选择一个动画根。该导出只生成 raw time 的 region-index 审计证据，不选择图像帧或渲染 sequence。")
            return
        suffix = f"_t{self.spine_pose_time:.3f}".replace(".", "_")
        default = self.spine_pose_session.workspace.bin_path.with_name(f"{self.spine_pose_session.workspace.bin_path.stem}_{self.spine_pose_session.animation.name}{suffix}.sequence-time-audit.json")
        path, _ = QFileDialog.getSaveFileName(self, "导出 Spine sequence 时间审计证据", str(default), "JSON (*.json)")
        if not path:
            return
        try:
            output = export_sequence_time_audit_evidence(
                self.spine_pose_session.workspace,
                self.spine_pose_session.animation.name,
                self.spine_pose_time,
                Path(path),
            )
            self.statusBar().showMessage(f"已导出 Spine 4.1 sequence raw time 审计证据：{output.name}；未选择图像帧、未渲染、未写回 BIN。")
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "无法导出 Spine sequence 时间审计证据", str(exc))

    def export_spine_pose_sequence_dialog(self) -> None:
        if self.spine_pose_session is None:
            QMessageBox.information(self, "尚未选择可预览 Spine 动画", "请先加载通过完整 timeline 读取的 Spine 资源并选择一个动画根。")
            return
        default = self.spine_pose_session.workspace.bin_path.with_name(f"{self.spine_pose_session.workspace.bin_path.stem}_{self.spine_pose_session.animation.name}_pose.gif")
        path, selected_filter = QFileDialog.getSaveFileName(self, "导出 Spine 只读 pose 序列", str(default), "Animated GIF (*.gif);;Animated PNG / APNG (*.png)")
        if not path:
            return
        kind = "gif" if selected_filter.startswith("Animated GIF") else "apng"
        try:
            result = export_spine_pose_sequence(self.spine_pose_session, Path(path), kind=kind)
            suffix = f"；{result.partial_frame_count} 帧含明确降级" if result.partial_frame_count else "；全部帧覆盖首批支持子集"
            self.statusBar().showMessage(f"已导出 {result.frame_count} 帧 Spine pose {kind}{suffix}：{result.output_path.name}")
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Spine pose 序列导出失败", str(exc))

    def select_spine_region(self, name: str | None) -> None:
        if self.spine_workspace is None or not name:
            return
        try:
            region = next(item for item in self.spine_workspace.atlas.regions if item.name == name)
            self.preview.set_image(render_region(self.spine_workspace.atlas, name), fit=True)
            self.spine_selected_region = name
            self.inspector_name.setText(name)
            self.inspector_type.setText(f"ATLAS region · {region.width}×{region.height} · 原始 {region.original_width}×{region.original_height} · 旋转 {region.rotation}° · 只读")
            self.status_context_label.setText(f"ATLAS 区域 · {name} · {region.width}×{region.height} · rotate {region.rotation}°")
        except (ValueError, OSError) as exc:
            self.statusBar().showMessage(f"无法预览 ATLAS 区域：{exc}")

    def load_workspace(self, bin_path: Path) -> None:
        try:
            self.active_bile_scene_proposal = None
            self.spine_workspace = None
            self.spine_selected_region = None
            self.spine_selected_animation = None
            self.spine_pose_session = None
            self.motion_proposal_session = None
            self.spine_pose_time = 0.0
            self.spine_timeline_inspector.clear()
            self.edit_panel.setEnabled(True)
            stem = bin_path.with_suffix("")
            xml_path = stem.with_suffix(".xml")
            image_path = next((candidate for candidate in (stem.with_suffix(".webp"), stem.with_suffix(".png")) if candidate.exists()), None)
            if not xml_path.exists() or image_path is None:
                raise FileNotFoundError("未找到同名 XML 或 WebP/PNG 图集")
            document = parse_file(bin_path)
            atlas = load_atlas(xml_path, image_path)
            if self._unsubscribe_document_session is not None:
                self._unsubscribe_document_session()
                self._unsubscribe_document_session = None
            if self.document_session is not None:
                self.document_session.close()
            self.workspace = Workspace.create(bin_path, xml_path, image_path, document, atlas)
            self.document_session = AnimationDocumentSession(self.workspace)
            self.edit_session = self.document_session.edit_session
            self._unsubscribe_document_session = self.document_session.subscribe(self._on_document_snapshot)
            self.formation_config_text = ""
            self._update_diagnostics()
            self._populate_resources()
            self.animation_navigator.set_document(self.display_document, None)
            self.title_label.setText(bin_path.stem)

            cycle_note = " · 检测到引用环" if document.graph_cycles else " · 引用图无环"
            xml_notes = []
            if atlas.xml_had_declaration:
                xml_notes.append("XML 声明")
            if atlas.stripped_control_chars:
                xml_notes.append(f"清理 {atlas.stripped_control_chars} 控制填充")
            if atlas.fractional_geometry_regions:
                xml_notes.append(f"{atlas.fractional_geometry_regions} 小数图集几何")
            profile = " · ".join(xml_notes) if xml_notes else "标准 XML 片段"
            self.subtitle_label.setText(f"{bin_path.name}  ·  {len(document.animations)} 个动画  ·  {len(document.sprites)} 个精灵  ·  BILE v{document.header.version} · {atlas.source_image_format.upper() or '图集'} · {profile}{cycle_note}")
            self.statusBar().showMessage(f"已通过 BILE v{document.header.version} 跨游戏结构验证：{bin_path.name}；嵌套时钟采用 reference_v4。")
            if document.animations:
                self.select_element(document.animations[0])
        except (OSError, BileFormatError, ValueError) as exc:
            QMessageBox.critical(self, "无法打开 BILE 资源", str(exc))
            self.statusBar().showMessage("加载失败：文件未被修改")

    def _populate_resources(self) -> None:
        assert self.workspace is not None
        self.resource_model.removeRows(0, self.resource_model.rowCount())
        root = QStandardItem(self.workspace.bin_path.name)
        root.setEditable(False)
        animations = QStandardItem(f"动画 ({len(self.display_document.animations)})")
        sprites = QStandardItem(f"精灵 ({len(self.display_document.sprites)})")
        for group, elements, kind in ((animations, self.display_document.animations, "animation"), (sprites, self.display_document.sprites, "sprite")):
            for element in elements:
                item = QStandardItem(element.name)
                item.setEditable(False)
                item.setData(kind, ROLE_KIND)
                item.setData(element.index, ROLE_INDEX)
                group.appendRow(item)
        root.appendRow(animations)
        root.appendRow(sprites)
        self.resource_model.appendRow(root)
        self.resource_tree.expandAll()

    def on_resource_selected(self, index: QModelIndex) -> None:
        kind = index.data(ROLE_KIND)
        element_index = index.data(ROLE_INDEX)
        if self.spine_workspace is not None:
            if kind == "spine_region" and isinstance(element_index, str):
                self.select_spine_region(element_index)
            elif kind == "spine_animation" and isinstance(element_index, str):
                self.select_spine_animation(element_index)
            return
        if self.workspace is not None and kind and isinstance(element_index, int):
            self.select_element(self.display_document.elements[element_index])

    def select_element(self, element: Element) -> None:
        if self.document_session is not None:
            self.document_session.select_element(element.index)
            current = self.document_session.snapshot.selected_element
            if current is None:
                return
            element = current
        self.selected_element = element
        self.play_timer.stop()
        self.play_action.setChecked(False)
        max_slot = max(0, element.frame_count - 1)
        for control in (self.slot_slider, self.slot_spin):
            control.blockSignals(True)
            control.setRange(0, max_slot)
            control.setValue(0)
            control.setEnabled(not element.has_texture)
            control.blockSignals(False)
        self.timeline.set_element(element if not element.has_texture else None)
        self._populate_inspector(element)
        self.set_slot(0)

    def _populate_inspector(self, element: Element | None) -> None:
        while self.inspector_form.rowCount():
            self.inspector_form.removeRow(0)
        if element is None:
            self.inspector_name.setText("未选择元素")
            self.inspector_type.setText("")
            return
        self.inspector_name.setText(element.name)
        self.inspector_type.setText("图片元素" if element.has_texture else "动画元素")
        read_only_version = self.workspace is not None and self.display_document.header.version == 2
        self._set_editor_enabled(not element.has_texture and not read_only_version, element.has_texture and not read_only_version)
        if read_only_version:
            self.edit_target_label.setText("BILE v2 已通过五节容器严格解析，但其 48 字节 BELE / 合并 BMRF 尚未获得写回实证；当前仅支持预览、导出与诊断。")
        elif element.has_texture:
            self.anchor_x_spin.setValue(element.x)
            self.anchor_y_spin.setValue(element.y)
            self.edit_target_label.setText("图片元素：可安全暂存 BMTI 锚点修改。")
        else:
            self.edit_target_label.setText("动画元素：使用当前槽位中的活动轨道关键帧，或直接输入 BELE 索引进行编辑。")
        values = {
            "BMTI 索引": str(element.index),
            "BRTS 字节偏移": f"0x{element.name_offset:X}",
            "锚点": f"({element.x:.2f}, {element.y:.2f})",
            "帧范围": str(element.frame_count),
            "通道数量": str(element.channel_count),
            "类型位": "1（图片）" if element.has_texture else "0（动画）",
            "引用图诊断": "无环" if self.workspace is None or not self.display_document.graph_cycles else f"{len(self.display_document.graph_cycles)} 个环（预览将截断）",
            "嵌套时钟": "reference_v4（相位/模式）" if not element.has_texture else "不适用",
        }
        for label, value in values.items():
            value_label = QLabel(value)
            self.inspector_form.addRow(label, value_label)

    def _sync_preview_hotspot_from_inspector(self) -> None:
        if self.selected_element is None or not self.selected_element.has_texture or self._anchor_drag_active:
            return
        refx, refy = self._sprite_reference
        self.preview.set_hotspot(refx - self.anchor_x_spin.value(), refy - self.anchor_y_spin.value(), self.apply_anchor_button.isEnabled())
        self.anchor_live_label.setText(
            f"检查器锚点：({self.anchor_x_spin.value():.2f}, {self.anchor_y_spin.value():.2f})；画布热点已同步，点击应用或直接拖动热点提交。"
        )

    def _on_hotspot_preview_changed(self, x: float, y: float) -> None:
        if self.selected_element is None or not self.selected_element.has_texture:
            return
        refx, refy = self._sprite_reference
        anchor_x = refx - x
        anchor_y = refy - y
        for control, value in ((self.anchor_x_spin, anchor_x), (self.anchor_y_spin, anchor_y)):
            control.blockSignals(True)
            control.setValue(value)
            control.blockSignals(False)
        self._anchor_drag_active = True
        self.anchor_live_label.setText(
            f"画布热点：({x:.2f}, {y:.2f}) → BMTI 锚点 ({anchor_x:.2f}, {anchor_y:.2f})；松开鼠标后提交一次编辑。"
        )

    def _on_hotspot_preview_drag_finished(self, x: float, y: float) -> None:
        if self.selected_element is None or not self.selected_element.has_texture:
            return
        self._anchor_drag_active = False
        self._on_hotspot_preview_changed(x, y)
        self._apply_anchor_edit()

    def set_slot(self, slot: int) -> None:
        if self.spine_pose_session is not None:
            normalized = max(0, min(1000, slot))
            for control in (self.slot_slider, self.slot_spin):
                if control.value() != normalized:
                    control.blockSignals(True)
                    control.setValue(normalized)
                    control.blockSignals(False)
            self._render_spine_pose_time(self.spine_pose_session.animation.duration * normalized / 1000.0)
            return
        if self.selected_element is None or self.workspace is None:
            return
        if self.selected_element.has_texture:
            self._render_selected_slot(0)
            return
        if self.document_session is not None:
            self.document_session.set_slot(slot)
            slot = self.document_session.snapshot.selection.slot
        else:
            slot = max(0, min(slot, max(0, self.selected_element.frame_count - 1)))
        self._render_selected_slot(slot)

    def _render_selected_slot(self, slot: int) -> None:
        if self.selected_element is None or self.workspace is None:
            return
        if self.selected_element.has_texture:
            try:
                image, refx, refy = render_sprite(self.workspace.atlas, self.selected_element)
                self._sprite_reference = (refx, refy)
                hotspot = (refx - self.selected_element.x, refy - self.selected_element.y)
                is_new_preview = self._preview_element_index != self.selected_element.index
                self.preview.set_image(
                    image,
                    fit=is_new_preview or not self.preview._has_content,
                    hotspot=hotspot,
                    hotspot_editable=self.apply_anchor_button.isEnabled(),
                )
                self._preview_element_index = self.selected_element.index
                self.timeline.set_element(None)
                self.slot_label.setText("图片元素 · 静态预览")
                self.anchor_live_label.setText(
                    f"画布热点：({hotspot[0]:.2f}, {hotspot[1]:.2f})；拖动热点即可修改 BMTI 锚点，释放后才提交。"
                )
            except (KeyError, ValueError) as exc:
                self.preview.clear_hotspot()
                self.statusBar().showMessage(f"图片元素预览失败：{exc}")
            return
        for control in (self.slot_slider, self.slot_spin):
            if control.value() != slot:
                control.blockSignals(True)
                control.setValue(slot)
                control.blockSignals(False)
        self.slot_label.setText(f"槽位 {slot} / {max(0, self.selected_element.frame_count - 1)}")
        self.timeline.set_slot(slot)
        selection = self.document_session.snapshot.selection if self.document_session is not None else None
        self.timeline.set_track_selection(selection.channel_index if selection is not None else None, selection.frame_slot if selection is not None else None)
        self._update_track_inspector(slot)
        self._sync_keyframe_editor(slot)
        try:
            image = render_frame(self.display_document, self.workspace.atlas, self.selected_element.name, slot)
            is_new_preview = self._preview_element_index != self.selected_element.index
            self.preview.set_image(image, fit=is_new_preview or not self.preview._has_content)
            self._preview_element_index = self.selected_element.index
        except (KeyError, ValueError) as exc:
            self.statusBar().showMessage(f"预览失败：{exc}")

    def _update_track_inspector(self, slot: int) -> None:
        if self.selected_element is None or self.selected_element.has_texture:
            self.track_inspector.set_contexts(())
            return
        contexts = active_tracks_at_slot(self.display_document, self.selected_element.index, slot)
        selected_keyframe = self.document_session.snapshot.selection.keyframe_index if self.document_session is not None else None
        self.track_inspector.set_contexts(contexts, selected_keyframe)

    def _select_track_region(self, channel_index: int, slot: int) -> None:
        self.set_slot(slot)
        if self.selected_element is None:
            return
        matching = tuple(
            context
            for context in active_tracks_at_slot(self.display_document, self.selected_element.index, slot)
            if context.channel_index == channel_index
        )
        if len(matching) == 1:
            self._select_track_context(matching[0])
        elif matching:
            self.statusBar().showMessage(f"通道 {channel_index + 1} 在槽位 {slot} 有 {len(matching)} 条活动 Track；请在“轨道检查器”中选择。")

    def _select_track_context(self, context: TrackContext) -> None:
        if self.document_session is None:
            return
        try:
            self.document_session.select_track(context)
            self._render_selected_slot(context.frame_slot)
            self.keyframe_spin.blockSignals(True)
            self.keyframe_spin.setValue(context.keyframe_index)
            self.keyframe_spin.blockSignals(False)
            self._load_keyframe_into_editor(context.keyframe_index)
            self.edit_target_label.setText(f"已选择轨道：{context.scope_label}。编辑将影响此 BELE 的全部引用位置；可先导出候选差异核验范围。")
            self.statusBar().showMessage(f"已选择 {context.scope_label}")
        except (DocumentSessionError, ValueError) as exc:
            QMessageBox.warning(self, "无法选择轨道", str(exc))

    def _active_keyframes(self, element: Element, slot: int) -> list[int]:
        found: list[int] = []
        for channel in element.channels:
            active = None
            for frame in channel.frames:
                if frame.slot <= slot:
                    active = frame
                else:
                    break
            if active is not None:
                found.extend(track.keyframe_index for track in active.tracks)
        return found

    def _sync_keyframe_editor(self, slot: int) -> None:
        if self.workspace is None or self.selected_element is None or self.selected_element.has_texture:
            return
        active = self._active_keyframes(self.selected_element, slot)
        if not active:
            return
        session_keyframe = self.document_session.snapshot.selection.keyframe_index if self.document_session is not None else None
        selected = session_keyframe if session_keyframe in active else active[0]
        self.keyframe_spin.blockSignals(True)
        self.keyframe_spin.setRange(0, len(self.display_document.keyframes) - 1)
        self.keyframe_spin.setValue(selected)
        self.keyframe_spin.blockSignals(False)
        self._load_keyframe_into_editor(selected)
        suffix = "；还有 " + str(len(active) - 1) + " 条活动轨道" if len(active) > 1 else ""
        self.edit_target_label.setText(f"当前槽位 {slot}：默认加载活动 BELE[{selected}]{suffix}。")

    def _load_keyframe_into_editor(self, index: int) -> None:
        if self.workspace is None or not 0 <= index < len(self.display_document.keyframes):
            return
        keyframe = self.display_document.keyframes[index]
        for field in ("xx", "xy", "yx", "yy", "x", "y"):
            self.xform_controls[field].setValue(getattr(keyframe, field))
        self.alpha_spin.setValue((keyframe.argb >> 24) & 0xFF)
        self.initial_phase_spin.setValue(min(keyframe.initial_phase, self.initial_phase_spin.maximum()))
        mode_text = {0: "0（当前子动画样本均为循环）", 1: "1（当前仅见于静态精灵轨道）", 2: "2（当前仅见于静态精灵轨道）"}.get(keyframe.playback_mode, f"未知({keyframe.playback_mode})")
        self.playback_mode_label.setText(f"只读 playback_mode：{mode_text}；保守补丁禁止改写该字段。")
        self._update_keyframe_scope_warning(index)
        if self.selected_element is not None and not self.selected_element.has_texture:
            self.edit_target_label.setText(f"BELE[{index}]：initial_phase={keyframe.initial_phase}，{mode_text}。")

    def _update_keyframe_scope_warning(self, keyframe_index: int) -> None:
        if self.workspace is None:
            self.keyframe_scope_label.setText("静态复用范围：尚未加载文档。")
            return
        contexts = keyframe_contexts(self.display_document, keyframe_index)
        animation_count = len({context.animation_index for context in contexts})
        current_count = sum(
            context.animation_index == self.selected_element.index
            for context in contexts
        ) if self.selected_element is not None and not self.selected_element.has_texture else 0
        targets = "、".join(sorted({context.target_element_name for context in contexts})[:4]) or "—"
        self.keyframe_scope_label.setText(
            f"BELE[{keyframe_index}] 在当前动画静态出现 {current_count} 条 Track；全文档共 {len(contexts)} 条 Track / "
            f"{animation_count} 个动画根，目标示例：{targets}。编辑前建议先导出“单动画静态档案”或轨道影响范围。"
        )

    def _apply_keyframe_edit(self) -> None:
        if self.workspace is None or self.edit_session is None or self.selected_element is None or self.selected_element.has_texture:
            return
        index = self.keyframe_spin.value()
        old = self.display_document.keyframes[index]
        transform = {field: control.value() for field, control in self.xform_controls.items()}
        argb = (self.alpha_spin.value() << 24) | (old.argb & 0x00FFFFFF)
        if self.document_session is None:
            return
        self.document_session.execute(SetKeyframeCommand(index, transform, argb, self.initial_phase_spin.value()))
        self._refresh_pending_preview(index)

    def _apply_anchor_edit(self) -> None:
        if self.workspace is None or self.edit_session is None or self.selected_element is None or not self.selected_element.has_texture:
            return
        if self.document_session is None:
            return
        self.document_session.execute(SetAnchorCommand(self.selected_element.index, self.anchor_x_spin.value(), self.anchor_y_spin.value()))
        self._refresh_pending_preview(None)

    def _refresh_pending_preview(self, keyframe_index: int | None) -> None:
        if self.workspace is None or self.edit_session is None or self.selected_element is None:
            return
        try:
            detail = f"BELE[{keyframe_index}]" if keyframe_index is not None else f"BMTI[{self.selected_element.index}] 锚点"
            self._restore_session_preview(f"已暂存并通过重解析验证：{detail}；待提交变更 {self.edit_session.change_count} 项。")
        except (OSError, BileFormatError, ValueError) as exc:
            QMessageBox.critical(self, "编辑被拒绝", f"未修改源文件。\n{exc}")

    def toggle_playback(self, enabled: bool) -> None:
        if self.spine_pose_session is not None:
            if enabled:
                # pose 预览固定以约 30 FPS 推进；它不是完整 Spine runtime 播放器。
                self.play_timer.start(33)
                self.play_action.setText("暂停")
            else:
                self.play_timer.stop()
                self.play_action.setText("播放")
            return
        if self.selected_element is None or self.selected_element.has_texture:
            self.play_action.setChecked(False)
            return
        if enabled:
            fps = max(1.0, self.display_document.header.fps if self.workspace else 24.0)
            self.play_timer.start(max(1, round(1000 / fps)))
            self.play_action.setText("暂停")
        else:
            self.play_timer.stop()
            self.play_action.setText("播放")

    def _advance_playhead(self) -> None:
        if self.spine_pose_session is not None:
            duration = max(0.001, self.spine_pose_session.animation.duration)
            step = max(1, round(1000.0 / (duration * 30.0)))
            self.set_slot(0 if self.slot_slider.value() >= 1000 else min(1000, self.slot_slider.value() + step))
            return
        if self.selected_element is None:
            return
        max_slot = max(0, self.selected_element.frame_count - 1)
        self.set_slot(0 if self.slot_slider.value() >= max_slot else self.slot_slider.value() + 1)

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if self._unsubscribe_document_session is not None:
            self._unsubscribe_document_session()
            self._unsubscribe_document_session = None
        if self.document_session is not None:
            self.document_session.close()
            self.document_session = None
        self.edit_session = None
        super().closeEvent(event)

    def show_about(self) -> None:
        QMessageBox.information(self, "关于 BILE Workbench", "此工作台使用已回归验证的 BILE 读取器。\n\n当前功能：三件套加载、结构审计、动画预览、播放与时间线定位。\n\n保存与编辑始终应先通过结构和渲染回归，避免破坏未知保留字段。")


def run() -> int:
    configure_high_dpi()
    app = QApplication(sys.argv)
    app.setApplicationName("BILE Workbench")
    app.setOrganizationName("py-workbench-evolution")
    apply_dark_theme(app)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(run())
