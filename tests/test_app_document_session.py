"""离屏验证 MainWindow 已通过 AnimationDocumentSession 驱动编辑。"""
from __future__ import annotations

import json
import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

try:
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtWidgets import QApplication, QDockWidget, QFileDialog, QMessageBox, QTabWidget, QSizePolicy
except ModuleNotFoundError as exc:
    raise unittest.SkipTest("PySide6 is required for desktop UI tests") from exc

from PIL import Image

from test_project_model import _minimal_v3_bile, _section
from bile_workbench.app import MainWindow
from bile_workbench.bile_format import parse_bytes
from bile_workbench.bile_scene_proposal import proposal_template
from bile_workbench.track_context import tracks_for_animation
from bile_workbench.project_workflow import ProjectWorkflowService


def _project_ui_bile() -> bytes:
    """提供一条动画引用 sprite 的有效 BILE v3 样本，不依赖外部原包资源。"""
    original = _minimal_v3_bile()
    document = parse_bytes(original)
    sections = bytearray()
    for section in document.sections.values():
        if section.tag == "BXDI":
            payload = bytearray(section.payload)
            struct.pack_into("<i", payload, 4, 1)
            sections.extend(_section(section.tag, bytes(payload), section.count))
        elif section.tag == "BMTI":
            sprite = bytearray(56)
            struct.pack_into("<IIff", sprite, 0, 1, 5, 0.0, 0.0)
            struct.pack_into("<I", sprite, 24, 1)
            sections.extend(_section(section.tag, section.payload + bytes(sprite), 2))
        elif section.tag == "BRTS":
            sections.extend(_section(section.tag, b"root\0sprite\0", 2))
        else:
            sections.extend(_section(section.tag, section.payload, section.count))
    return b"BILE" + struct.pack("<IIHHf", 3, len(sections), 20, 6, 30.0) + sections


class MainWindowProjectWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_open_project_from_empty_window_loads_referenced_source_and_restores_edits(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "unit.bin"
            source.write_bytes(_project_ui_bile())
            source.with_suffix(".xml").write_text(
                '<TextureAtlas><SubTexture name="sprite" x="0" y="0" width="2" height="2"/></TextureAtlas>',
                encoding="utf-8",
            )
            Image.new("RGBA", (2, 2), (0, 0, 0, 0)).save(source.with_suffix(".png"))
            project_dir = root / "unit.bileproj"
            service = ProjectWorkflowService.import_source(
                source, project_dir,
                xml_path=source.with_suffix(".xml"),
                texture_path=source.with_suffix(".png"),
            )
            service.append_edit(section="BELE", index=0, field="transform.x", after=19.5)

            window = MainWindow()
            try:
                self.assertIsNone(window.workspace)
                self.assertTrue(window.open_project_action.isEnabled())
                with patch.object(QFileDialog, "getExistingDirectory", return_value=str(project_dir)), patch.object(
                    QMessageBox, "information"
                ), patch.object(QMessageBox, "critical") as critical:
                    window.open_project_dialog()
                critical.assert_not_called()
                self.assertEqual(window.workspace.bin_path, source.resolve(strict=True))
                self.assertEqual(window.display_document.keyframes[0].x, 19.5)
                self.assertTrue(window.edit_session.dirty)
                self.assertEqual(window.project_service.inspect().operation_count, 1)
            finally:
                window.close()

    def test_switching_source_requires_sync_before_discarding_project_edits(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "unit.bin"
            source.write_bytes(_project_ui_bile())
            source.with_suffix(".xml").write_text(
                '<TextureAtlas><SubTexture name="sprite" x="0" y="0" width="2" height="2"/></TextureAtlas>',
                encoding="utf-8",
            )
            Image.new("RGBA", (2, 2), (0, 0, 0, 0)).save(source.with_suffix(".png"))
            other = root / "other.bin"
            other.write_bytes(source.read_bytes())
            other.with_suffix(".xml").write_text(source.with_suffix(".xml").read_text(encoding="utf-8"), encoding="utf-8")
            Image.new("RGBA", (2, 2), (0, 0, 0, 0)).save(other.with_suffix(".png"))

            window = MainWindow()
            try:
                window.load_workspace(source)
                with patch.object(QFileDialog, "getExistingDirectory", return_value=str(root)), patch.object(QMessageBox, "information"):
                    window.new_project_dialog()
                service = window.project_service
                self.assertIsNotNone(service)
                window.edit_session.set_keyframe(0, {"x": 13.5}, 0xFFFFFFFF, 0)
                window.document_session.refresh()

                with patch.object(QMessageBox, "question", return_value=QMessageBox.No) as question:
                    window.load_workspace(other)
                question.assert_called_once()
                self.assertEqual(window.workspace.bin_path, source)
                self.assertEqual(service.inspect().operation_count, 0)

                with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes) as question, patch.object(QMessageBox, "critical") as critical:
                    window.load_workspace(other)
                question.assert_called_once()
                critical.assert_not_called()
                self.assertEqual(service.inspect().operation_count, 1)
                self.assertIsNone(window.project_service)
                self.assertEqual(window.workspace.bin_path, other)
            finally:
                window.close()

    def test_switching_to_spine_requires_sync_and_cancel_preserves_bile_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "unit.bin"
            source.write_bytes(_project_ui_bile())
            source.with_suffix(".xml").write_text(
                '<TextureAtlas><SubTexture name="sprite" x="0" y="0" width="2" height="2"/></TextureAtlas>',
                encoding="utf-8",
            )
            Image.new("RGBA", (2, 2), (0, 0, 0, 0)).save(source.with_suffix(".png"))
            window = MainWindow()
            try:
                window.load_workspace(source)
                with patch.object(QFileDialog, "getExistingDirectory", return_value=str(root)), patch.object(QMessageBox, "information"):
                    window.new_project_dialog()
                service = window.project_service
                window.edit_session.set_keyframe(0, {"x": 15.5}, 0xFFFFFFFF, 0)
                window.document_session.refresh()
                with patch("bile_workbench.app.load_spine_static_workspace", return_value=object()), patch.object(
                    QMessageBox, "question", return_value=QMessageBox.No
                ) as question:
                    window.load_spine_workspace(root / "not-opened.bin")
                question.assert_called_once()
                self.assertIs(window.project_service, service)
                self.assertEqual(window.workspace.bin_path, source)
                self.assertEqual(service.inspect().operation_count, 0)
            finally:
                with patch.object(QMessageBox, "question", return_value=QMessageBox.No):
                    window.close()

    def test_close_requires_explicit_sync_or_discard_for_project_edits(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "unit.bin"
            source.write_bytes(_project_ui_bile())
            source.with_suffix(".xml").write_text(
                '<TextureAtlas><SubTexture name="sprite" x="0" y="0" width="2" height="2"/></TextureAtlas>',
                encoding="utf-8",
            )
            Image.new("RGBA", (2, 2), (0, 0, 0, 0)).save(source.with_suffix(".png"))
            window = MainWindow()
            service = None
            try:
                window.load_workspace(source)
                with patch.object(QFileDialog, "getExistingDirectory", return_value=str(root)), patch.object(QMessageBox, "information"):
                    window.new_project_dialog()
                service = window.project_service
                window.edit_session.set_keyframe(0, {"x": 16.5}, 0xFFFFFFFF, 0)
                window.document_session.refresh()

                with patch.object(QMessageBox, "question", return_value=QMessageBox.Cancel) as question:
                    self.assertFalse(window.close())
                question.assert_called_once()
                self.assertIsNotNone(window.document_session)
                self.assertEqual(service.inspect().operation_count, 0)

                with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes) as question, patch.object(QMessageBox, "critical") as critical:
                    self.assertTrue(window.close())
                question.assert_called_once()
                critical.assert_not_called()
                self.assertEqual(service.inspect().operation_count, 1)
                self.assertIsNone(window.document_session)
            finally:
                window.close()

    def test_project_create_sync_restore_and_candidate_build(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "unit.bin"
            source.write_bytes(_project_ui_bile())
            source.with_suffix(".xml").write_text(
                '<TextureAtlas><SubTexture name="sprite" x="0" y="0" width="2" height="2"/></TextureAtlas>',
                encoding="utf-8",
            )
            Image.new("RGBA", (2, 2), (0, 0, 0, 0)).save(source.with_suffix(".png"))

            window = MainWindow()
            try:
                with patch.object(QMessageBox, "critical") as critical:
                    window.load_workspace(source)
                    critical.assert_not_called()
                self.assertTrue(window.new_project_action.isEnabled())
                self.assertEqual(window.project_status_label.text(), "Project · 未打开")
                self.assertTrue(any(action.text() == "工程" for action in window.menuBar().actions()))

                with patch.object(QFileDialog, "getExistingDirectory", return_value=str(root)), patch.object(QMessageBox, "information"):
                    window.new_project_dialog()
                project_dir = root / "unit.bileproj"
                self.assertTrue(project_dir.is_dir())
                self.assertEqual(window.project_service.inspect().operation_count, 0)

                window.edit_session.set_keyframe(0, {"x": 12.5}, 0xFFFFFFFF, 0)
                window.document_session.refresh()
                with patch.object(QMessageBox, "information"):
                    window.sync_project_dialog()
                self.assertEqual(window.project_service.inspect().operation_count, 1)

                window.document_session.clear_edits()
                with patch.object(QFileDialog, "getExistingDirectory", return_value=str(project_dir)), patch.object(QMessageBox, "information"):
                    window.open_project_dialog()
                self.assertTrue(window.edit_session.dirty)
                self.assertEqual(window.display_document.keyframes[0].x, 12.5)
                self.assertIn("Edit Set 1 项", window.project_status_label.text())

                # 重新加载同一 source 时，已打开的 Project 必须自动恢复，而不是退化成空会话。
                window.load_workspace(source)
                self.assertIsNotNone(window.project_service)
                self.assertTrue(window.edit_session.dirty)
                self.assertEqual(window.display_document.keyframes[0].x, 12.5)
                self.assertIn("暂存状态已同步", window.project_status_label.text())

                candidate = root / "candidate.bin"
                with patch.object(QFileDialog, "getSaveFileName", return_value=(str(candidate), "BILE Candidate (*.bin)")), patch.object(QMessageBox, "information"):
                    window.build_project_candidate_dialog()
                self.assertTrue(candidate.is_file())
                self.assertEqual(window.project_service.inspect().candidate.status, "Current")
                with patch.object(QMessageBox, "information") as info, patch.object(QMessageBox, "warning") as warning:
                    window.validate_project_candidate_dialog()
                info.assert_called_once()
                warning.assert_not_called()

                # 未同步编辑不得验证旧候选；同步后旧候选必须变为 Stale。
                window.edit_session.set_keyframe(0, {"x": 14.5}, 0xFFFFFFFF, 0)
                window.document_session.refresh()
                with patch.object(QMessageBox, "warning") as warning:
                    window.validate_project_candidate_dialog()
                warning.assert_called_once()
                self.assertEqual(window.project_service.inspect().candidate.status, "Current")

                with patch.object(QMessageBox, "information"):
                    window.sync_project_dialog()
                self.assertEqual(window.project_service.inspect().candidate.status, "Stale")
                with patch.object(QMessageBox, "warning") as warning:
                    window.validate_project_candidate_dialog()
                warning.assert_called_once()
            finally:
                window.close()


class MainWindowDocumentSessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def require_sample_bile(self) -> Path:
        sample = ROOT / "sample_assets" / "anim_failure.bin"
        if not sample.is_file():
            self.skipTest("sample_assets/anim_failure.bin 未随当前工作树提供")
        return sample

    def test_ribbon_context_tabs_and_command_availability_follow_session(self) -> None:
        sample = self.require_sample_bile()
        window = MainWindow()
        try:
            tab_bar = window.ribbon.findChild(QTabWidget).tabBar()
            visible_before = [tab_bar.tabText(index) for index in range(tab_bar.count()) if tab_bar.isTabVisible(index)]
            self.assertEqual(visible_before, ["文件", "编辑", "验证", "实验", "视图"])
            self.assertFalse(window.export_json_action.isEnabled())
            self.assertFalse(window.export_scene_interchange_action.isEnabled())
            self.assertFalse(window.play_action.isEnabled())
            self.assertFalse(window.focus_track_action.isEnabled())

            window.load_workspace(sample)
            animation = window.display_document.animations[0]
            window.select_element(animation)
            visible_after_animation = [tab_bar.tabText(index) for index in range(tab_bar.count()) if tab_bar.isTabVisible(index)]
            self.assertIn("动画工具", visible_after_animation)
            self.assertNotIn("轨道工具", visible_after_animation)
            self.assertTrue(window.export_json_action.isEnabled())
            self.assertTrue(window.export_scene_interchange_action.isEnabled())
            self.assertTrue(window.play_action.isEnabled())
            self.assertFalse(window.focus_track_action.isEnabled())

            context = tracks_for_animation(window.display_document, animation.index)[0]
            window._select_track_context(context)
            visible_after_track = [tab_bar.tabText(index) for index in range(tab_bar.count()) if tab_bar.isTabVisible(index)]
            self.assertIn("轨道工具", visible_after_track)
            self.assertTrue(window.focus_track_action.isEnabled())
            self.assertIn(f"BELE[{context.keyframe_index}]", window.status_context_label.text())

            window.clear_track_selection()
            self.assertFalse(window.focus_track_action.isEnabled())
        finally:
            window.close()

    def test_workbench_canvas_is_expanding_and_ribbon_pages_have_scroll_path(self) -> None:
        window = MainWindow()
        try:
            self.assertEqual(QSizePolicy.Policy.Expanding, window.preview.sizePolicy().horizontalPolicy())
            self.assertEqual(QSizePolicy.Policy.Expanding, window.preview.sizePolicy().verticalPolicy())
            self.assertGreaterEqual(window.preview.minimumHeight(), 280)
            scroll_areas = tuple(window.ribbon._scroll_areas.values())
            self.assertEqual(8, len(scroll_areas))
            self.assertTrue(all(area.widgetResizable() for area in scroll_areas))
            self.assertTrue(all(area.verticalScrollBarPolicy().name in {"ScrollBarAsNeeded", "ScrollBarAlwaysOn"} for area in scroll_areas))
            self.assertGreaterEqual(window.ribbon.maximumHeight(), window.ribbon.minimumHeight())
            window.show()
            self.app.processEvents()
            file_page = window.ribbon._scroll_areas["file"]
            scrollbar = file_page.verticalScrollBar()
            self.assertGreater(scrollbar.maximum(), 0)
            scrollbar.setValue(scrollbar.maximum())
            event = QWheelEvent(
                QPointF(10, 10), QPointF(10, 10), QPoint(0, 0), QPoint(0, 120),
                Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                Qt.ScrollPhase.ScrollUpdate, False,
            )
            before = scrollbar.value()
            file_page.wheelEvent(event)
            self.assertLess(scrollbar.value(), before)
        finally:
            window.close()

    def test_external_theme_presets_are_discovered_and_switchable(self) -> None:
        window = MainWindow()
        try:
            self.assertEqual({"anime-claude-girl", "anime-openai-girl"}, set(window.theme_plugins.plugins))
            self.assertEqual({"二次元 ClaudeAI 少女", "二次元 OpenAI 少女"}, {action.text() for action in window._plugin_actions.values()})
            window._set_plugin_theme("anime-claude-girl")
            self.assertEqual("anime-claude-girl", window.theme_plugins.active_plugin_id)
            self.assertIn("#A967B8", self.app.styleSheet())
            self.assertIn("二次元 ClaudeAI 少女", window.plugin_badge_title.text())
            window._set_base_theme("light")
            self.assertEqual("light", window.theme_plugins.base_mode)
            self.assertIn("#FFF9F2", self.app.styleSheet())
            self.assertIn("#A967B8", self.app.styleSheet())
            window._set_plugin_theme("anime-openai-girl")
            self.assertIn("#168F97", self.app.styleSheet())
            self.assertIn("二次元 OpenAI 少女", window.plugin_badge_title.text())
            window._set_plugin_theme(None)
            self.assertIsNone(window.theme_plugins.active_plugin_id)
            self.assertNotIn("#A967B8", self.app.styleSheet())
            window._set_base_theme("dark")
        finally:
            window.close()

    def test_sprite_canvas_hotspot_is_directly_draggable_and_commits_once(self) -> None:
        sample = self.require_sample_bile()
        window = MainWindow()
        try:
            window.load_workspace(sample)
            sprites = window.display_document.sprites
            self.assertTrue(sprites, "样本应至少包含一个图片元素")
            sprite = sprites[0]
            window.select_element(sprite)
            self.app.processEvents()
            self.assertTrue(window.preview._has_content)
            self.assertIsNotNone(window.preview._hotspot_handle)
            handle = window.preview._hotspot_handle
            assert handle is not None
            before_changes = window.document_session.snapshot.change_count
            refx, refy = window._sprite_reference
            manual_anchor_x = sprite.x + 1.5
            window.anchor_x_spin.setValue(manual_anchor_x)
            self.assertAlmostEqual(refx - manual_anchor_x, handle.x(), places=3)
            self.assertEqual(before_changes, window.document_session.snapshot.change_count)
            new_x, new_y = handle.x() + 3.0, handle.y() + 2.0
            window._on_hotspot_preview_changed(new_x, new_y)
            self.assertAlmostEqual(refx - new_x, window.anchor_x_spin.value(), places=3)
            self.assertAlmostEqual(refy - new_y, window.anchor_y_spin.value(), places=3)
            self.assertEqual(before_changes, window.document_session.snapshot.change_count)
            window._on_hotspot_preview_drag_finished(new_x, new_y)
            self.assertEqual(before_changes + 1, window.document_session.snapshot.change_count)
            self.assertIn("BMTI", window.anchor_live_label.text())
        finally:
            window.close()

    def test_first_show_focus_canvas_and_restore_layout_resize_preview(self) -> None:
        sample = self.require_sample_bile()
        window = MainWindow()
        try:
            window.show()
            self.app.processEvents()
            self.assertTrue(window.isMaximized() or window.isVisible())
            window.load_workspace(sample)
            self.app.processEvents()
            self.assertTrue(window.preview._has_content)
            self.assertGreater(window.preview.viewport().height(), 200)
            default_area = window.preview.viewport().width() * window.preview.viewport().height()
            dock_names = (
                "ResourceBrowserDock", "AnimationNavigatorDock", "InspectorDock", "TrackInspectorDock",
                "TimelineDock", "SpineTimelineDock", "DiagnosticsDock", "ChangeLedgerDock",
            )
            self.assertTrue(all(window.findChild(QDockWidget, name) is not None for name in dock_names))
            window.toggle_canvas_focus()
            self.app.processEvents()
            self.assertTrue(window._canvas_focus_active)
            self.assertTrue(all(not window.findChild(QDockWidget, name).isVisible() for name in dock_names))
            self.assertFalse(window._ribbon_toolbar.isVisible())
            focus_area = window.preview.viewport().width() * window.preview.viewport().height()
            self.assertGreater(focus_area, default_area)
            window.toggle_canvas_focus()
            self.app.processEvents()
            self.assertFalse(window._canvas_focus_active)
            self.assertTrue(window._ribbon_toolbar.isVisible())
            window.restore_default_layout()
            self.app.processEvents()
            self.assertFalse(window._canvas_focus_active)
            self.assertTrue(window._ribbon_toolbar.isVisible())
            self.assertTrue(window.preview._has_content)
            window.resize(1180, 760)
            self.app.processEvents()
            self.assertGreater(window.preview.viewport().height(), 200)
            self.assertFalse(window.preview.scene().sceneRect().isEmpty())
        finally:
            window.close()

    def test_bile_scene_proposal_action_stages_only_bound_v4_candidate(self) -> None:
        source = self.require_sample_bile()
        before = source.read_bytes()
        window = MainWindow()
        try:
            self.assertFalse(window.export_bile_scene_proposal_template_action.isEnabled())
            self.assertFalse(window.load_bile_scene_proposal_action.isEnabled())
            self.assertFalse(window.export_bile_scene_proposal_evidence_action.isEnabled())
            window.load_workspace(source)
            self.assertTrue(window.export_bile_scene_proposal_template_action.isEnabled())
            self.assertTrue(window.load_bile_scene_proposal_action.isEnabled())
            self.assertFalse(window.export_bile_scene_proposal_evidence_action.isEnabled())
            payload = proposal_template(window.document_session)
            payload["keyframes"][0]["transform"]["x"] += 1.0
            with tempfile.TemporaryDirectory() as directory:
                proposal_path = Path(directory) / "candidate.json"
                proposal_path.write_text(json.dumps(payload), encoding="utf-8")
                with patch("bile_workbench.app.QFileDialog.getOpenFileName", return_value=(str(proposal_path), "JSON (*.json)")), patch("bile_workbench.app.QMessageBox.information"):
                    window.load_bile_scene_proposal_dialog()
            self.assertTrue(window.document_session.snapshot.dirty)
            self.assertTrue(window.export_bile_scene_proposal_evidence_action.isEnabled())
            self.assertIn("暂存变更 1 项", window.change_ledger.summary.text())
            ledger_rows = [
                " · ".join(window.change_ledger.tree.topLevelItem(index).child(child).text(column) for column in range(3))
                for index in range(window.change_ledger.tree.topLevelItemCount())
                for child in range(window.change_ledger.tree.topLevelItem(index).childCount())
            ]
            self.assertTrue(any("AI 场景提案" in row and "已接受哈希绑定候选" in row for row in ledger_rows))
            with tempfile.TemporaryDirectory() as directory:
                evidence_path = Path(directory) / "evidence.json"
                with patch("bile_workbench.app.QFileDialog.getSaveFileName", return_value=(str(evidence_path), "JSON (*.json)")):
                    window.export_bile_scene_proposal_evidence_dialog()
                evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            self.assertEqual("none", evidence["binary_writeback"])
            window.load_workspace(source)
            self.assertFalse(window.export_bile_scene_proposal_evidence_action.isEnabled())
            reloaded_ledger_rows = [
                " · ".join(window.change_ledger.tree.topLevelItem(index).child(child).text(column) for column in range(3))
                for index in range(window.change_ledger.tree.topLevelItemCount())
                for child in range(window.change_ledger.tree.topLevelItem(index).childCount())
            ]
            self.assertTrue(any("当前会话未加载可追溯的 AI 场景候选" in row for row in reloaded_ledger_rows))
            self.assertEqual(before, source.read_bytes())
        finally:
            window.close()

    def test_bile_scene_proposal_actions_are_disabled_for_v2_and_spine(self) -> None:
        window = MainWindow()
        try:
            v2 = ROOT / "cross_game_assets" / "general1" / "mtank.bin"
            if v2.exists():
                window.load_workspace(v2)
                self.assertFalse(window.export_bile_scene_proposal_template_action.isEnabled())
                self.assertFalse(window.load_bile_scene_proposal_action.isEnabled())
                self.assertFalse(window.export_bile_scene_proposal_evidence_action.isEnabled())
            spine = ROOT / "incoming/cross_era_20260822/欧7测试/animation/Arthur2.bin"
            if not spine.exists():
                self.skipTest("欧7 Spine GUI 验证样本未附加")
            window.load_spine_workspace(spine)
            self.assertFalse(window.export_bile_scene_proposal_template_action.isEnabled())
            self.assertFalse(window.load_bile_scene_proposal_action.isEnabled())
            self.assertFalse(window.export_bile_scene_proposal_evidence_action.isEnabled())
        finally:
            window.close()

    def test_spine_sequence_time_audit_action_follows_spine41_pose_and_current_time(self) -> None:
        sample = self.require_sample_bile()
        spine41 = ROOT / "incoming/cross_era_20260822/征2测试/animation/EmpireCityFire01.bin"
        spine38 = ROOT / "incoming/cross_era_20260822/欧7测试/animation/Arthur2.bin"
        if not spine41.exists():
            self.skipTest("征2 Spine 4.1 GUI 验证样本未附加")
        before = spine41.read_bytes()
        window = MainWindow()
        try:
            self.assertFalse(window.export_spine_sequence_time_audit_evidence_action.isEnabled())
            window.load_spine_workspace(spine41)
            self.assertTrue(window.export_spine_sequence_time_audit_evidence_action.isEnabled())
            self.assertEqual(0.0, window.spine_pose_time)
            with tempfile.TemporaryDirectory() as directory:
                evidence_path = Path(directory) / "sequence-time-audit.json"
                with patch("bile_workbench.app.QFileDialog.getSaveFileName", return_value=(str(evidence_path), "JSON (*.json)")):
                    window.export_spine_sequence_time_audit_evidence_dialog()
                payload = json.loads(evidence_path.read_text(encoding="utf-8"))
            self.assertEqual(("easytech-spine-sequence-time-audit/v1", 0.0, "forbidden", "forbidden"), (payload["schema"], payload["target_time"], payload["frame_selection"], payload["rendering"]))
            self.assertEqual(before, spine41.read_bytes())
            if spine38.exists():
                window.load_spine_workspace(spine38)
                self.assertFalse(window.export_spine_sequence_time_audit_evidence_action.isEnabled())
            window.load_workspace(sample)
            self.assertFalse(window.export_spine_sequence_time_audit_evidence_action.isEnabled())
        finally:
            window.close()

    def test_spine_two_color_evidence_action_follows_pose_session(self) -> None:
        sample = self.require_sample_bile()
        spine41 = ROOT / "incoming/cross_era_20260822/征2测试/animation/EmpireCityFire01.bin"
        if not spine41.exists():
            self.skipTest("征2 Spine 4.1 two-color GUI 验证样本未附加")
        before = spine41.read_bytes()
        window = MainWindow()
        try:
            self.assertFalse(window.export_spine_two_color_evidence_action.isEnabled())
            window.load_spine_workspace(spine41)
            self.assertTrue(window.export_spine_two_color_evidence_action.isEnabled())
            with tempfile.TemporaryDirectory() as directory:
                evidence_path = Path(directory) / "two-color-audit.json"
                with patch("bile_workbench.app.QFileDialog.getSaveFileName", return_value=(str(evidence_path), "JSON (*.json)")):
                    window.export_spine_two_color_evidence_dialog()
                payload = json.loads(evidence_path.read_text(encoding="utf-8"))
            self.assertEqual(("easytech-spine-two-color-audit/v1", 4, "forbidden", "forbidden"), (payload["schema"], payload["timeline_count"], payload["pixel_application"], payload["rendering"]))
            self.assertEqual(before, spine41.read_bytes())
            window.load_workspace(sample)
            self.assertFalse(window.export_spine_two_color_evidence_action.isEnabled())
        finally:
            window.close()

    def test_spine_deform_audit_export_action_follows_pose_session(self) -> None:
        sample = self.require_sample_bile()
        spine = ROOT / "incoming/cross_era_20260822/欧7测试/animation/Arthur2.bin"
        if not spine.exists():
            self.skipTest("欧7 Spine GUI 验证样本未附加")
        window = MainWindow()
        try:
            self.assertFalse(window.export_spine_deform_evidence_action.isEnabled())
            window.load_spine_workspace(spine)
            self.assertTrue(window.export_spine_deform_evidence_action.isEnabled())
            self.assertFalse(window.load_bile_scene_proposal_action.isEnabled())
            window.load_workspace(sample)
            self.assertFalse(window.export_spine_deform_evidence_action.isEnabled())
        finally:
            window.close()

    def test_change_ledger_and_keyframe_scope_follow_staged_edit(self) -> None:
        sample = self.require_sample_bile()
        window = MainWindow()
        try:
            window.load_workspace(sample)
            animation = window.display_document.animations[0]
            window.select_element(animation)
            context = tracks_for_animation(window.display_document, animation.index)[0]
            window._select_track_context(context)
            self.assertIn(f"BELE[{context.keyframe_index}]", window.keyframe_scope_label.text())
            self.assertIn("全文档共", window.keyframe_scope_label.text())
            self.assertIn("暂存变更 0 项", window.change_ledger.summary.text())

            before = window.display_document.keyframes[context.keyframe_index]
            window.xform_controls["x"].setValue(before.x + 1.0)
            window._apply_keyframe_edit()
            self.assertIn("暂存变更 1 项", window.change_ledger.summary.text())
            ledger_text = "\n".join(
                window.change_ledger.tree.topLevelItem(index).text(0)
                for index in range(window.change_ledger.tree.topLevelItemCount())
            )
            self.assertIn("实时预检", ledger_text)
        finally:
            window.close()

    def test_inspector_edit_uses_document_session_and_undo(self) -> None:
        sample = self.require_sample_bile()
        window = MainWindow()
        try:
            window.load_workspace(sample)
            self.assertIsNotNone(window.document_session)
            self.assertIn("BILE v4", window.document_status_label.text())
            self.assertIn("保守编辑", window.document_status_label.text())
            animation = window.display_document.animations[0]
            window.select_element(animation)
            self.assertEqual(window.document_session.snapshot.selection.element_index, animation.index)
            context = tracks_for_animation(window.display_document, animation.index)[0]
            window.set_slot(context.frame_slot)
            window._select_track_context(context)
            track_selection = window.document_session.snapshot.selection
            self.assertEqual(track_selection.keyframe_index, context.keyframe_index)
            self.assertEqual(track_selection.channel_index, context.channel_index)
            self.assertEqual(window.keyframe_spin.value(), context.keyframe_index)
            self.assertIn("已选择轨道", window.edit_target_label.text())
            keyframe_index = window.keyframe_spin.value()
            before = window.display_document.keyframes[keyframe_index]
            window.xform_controls["x"].setValue(before.x + 1.25)
            window._apply_keyframe_edit()
            self.assertTrue(window.document_session.snapshot.dirty)
            self.assertIn("暂存 1 项变更", window.document_status_label.text())
            self.assertEqual(window.display_document.keyframes[keyframe_index].x, before.x + 1.25)
            window.undo_pending_edit()
            self.assertFalse(window.document_session.snapshot.dirty)
            self.assertIn("原始基线未修改", window.document_status_label.text())
            self.assertEqual(window.display_document.keyframes[keyframe_index].x, before.x)
        finally:
            window.close()


if __name__ == "__main__":
    unittest.main()
