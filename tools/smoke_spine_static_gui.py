"""离屏核验欧7/征2 Spine 静态工作区的主窗口集成。"""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from bile_workbench.app import MainWindow
from bile_workbench.motion_dsl import parse_motion_proposal, proposal_template
from bile_workbench.theme import apply_dark_theme, configure_high_dpi

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = (
    (ROOT / "incoming/cross_era_20260822/欧7测试/animation/Arthur2.bin", "spine38", "剑", ROOT / "research/gui_spine_eu7.png"),
    (ROOT / "incoming/cross_era_20260822/征2测试/animation/[mini]effect_ui10.bin", "spine41", "羁绊墨环", ROOT / "research/gui_spine_zheng2.png"),
)


def main() -> int:
    configure_high_dpi()
    app = QApplication.instance() or QApplication([])
    apply_dark_theme(app)
    window = MainWindow()
    window.show()
    app.processEvents()
    for path, engine, region, screenshot in SAMPLES:
        window.load_spine_workspace(path)
        window.select_spine_region(region)
        app.processEvents()
        assert window.spine_workspace is not None, path
        assert window.ribbon._tabs.currentWidget().objectName() == "RibbonPage_spine", "加载 Spine 后应聚焦其上下文 Ribbon"
        assert window.spine_workspace.engine == engine, window.spine_workspace.engine
        assert window.spine_selected_region == region, window.spine_selected_region
        assert window.spine_workspace.timeline_archive is not None, "欧7/征2样本应完整读取 animations 段"
        assert window.spine_workspace.timeline_count > 0, "应存在已解析的 Spine timeline"
        animation_name = window.spine_workspace.timeline_archive.animations[0].name
        window.select_spine_animation(animation_name)
        assert window.spine_selected_animation == animation_name
        assert window.spine_pose_session is not None, "完整 timeline 样本应建立只读 pose 会话"
        assert window.spine_timeline_inspector._model.rowCount() > 0, "应建立 Spine 动画审阅树"
        window.set_slot(500)
        assert window.spine_pose_time > 0, "Spine 时间滑块应推进 pose 时间"
        prior = window.slot_slider.value()
        window.toggle_playback(True)
        window._advance_playhead()
        window.toggle_playback(False)
        assert window.slot_slider.value() > prior or window.slot_slider.value() == 0, "Spine 播放应推进或循环归一化时间"
        assert window.export_spine_static_action.isEnabled(), "Spine 结构与动画档案导出动作应可用"
        assert window.export_spine_pose_sequence_action.isEnabled(), "Spine 只读 pose 序列导出动作应可用"
        assert window.motion_proposal_session is not None, "Spine pose 会话必须可承载只读 AI Motion DSL"
        payload = proposal_template(window.spine_pose_session)
        payload["operations"] = [{
            "id": "gui_root_delta",
            "kind": "bone_delta",
            "bone": window.spine_workspace.document.bones[0].name,
            "time": {"start": 0.0, "end": min(0.1, window.spine_pose_session.animation.duration)},
            "delta": {"y": 1.0},
        }]
        window.motion_proposal_session.apply(parse_motion_proposal(payload, window.spine_pose_session))
        window.set_slot(500)
        window._refresh_command_availability()
        assert window.undo_motion_proposal_action.isEnabled(), "已应用的内存提案应允许撤销"
        window.undo_motion_proposal()
        assert not window.undo_motion_proposal_action.isEnabled(), "撤销后不应遗留 AI 提案历史状态"
        assert not window.save_pending_action.isEnabled(), "Spine 工作区不得启用 BILE 写回动作"
        assert window.resource_model.rowCount() == 1, "应建立 Spine 资源树"
        screenshot.parent.mkdir(parents=True, exist_ok=True)
        window.grab().save(str(screenshot))
        print(f"PASS {engine}: {path.name} -> {screenshot}")
    window.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
