#!/usr/bin/env python3
"""离屏启动 BILE Workbench，验证真实 initial_phase 编辑并保存界面截图。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from bile_workbench.app import MainWindow
from bile_workbench.preflight import run_preflight
from bile_workbench.theme import apply_dark_theme, configure_high_dpi


def find_real_initial_phase_target(window: MainWindow) -> tuple[int, int, int]:
    assert window.workspace is not None
    doc = window.workspace.document
    for parent in doc.animations:
        for channel in parent.channels:
            for frame in channel.frames:
                for track in frame.tracks:
                    if track.element_index < 0 or doc.elements[track.element_index].has_texture:
                        continue
                    keyframe = doc.keyframes[track.keyframe_index]
                    if keyframe.initial_phase != 0:
                        return parent.index, frame.slot, track.keyframe_index
    raise RuntimeError("未找到真实非零 initial_phase 子动画轨道")


def main() -> int:
    configure_high_dpi()
    app = QApplication([])
    apply_dark_theme(app)
    window = MainWindow()
    window.show()
    window.load_workspace(ROOT / "sample_assets" / "anim_status.bin")
    parent_index, slot, active_index = find_real_initial_phase_target(window)
    assert window.workspace is not None
    window.select_element(window.workspace.document.elements[parent_index])
    window.set_slot(slot)
    window.keyframe_spin.setValue(active_index)
    original_phase = window.workspace.document.keyframes[active_index].initial_phase
    window.initial_phase_spin.setValue(original_phase + 1)
    window._apply_keyframe_edit()
    assert window.workspace.document.keyframes[active_index].initial_phase == original_phase + 1
    assert window.edit_session is not None and window.edit_session.dirty
    report = run_preflight(window.edit_session, window.workspace.atlas)
    assert not report.has_errors
    window.edit_session.write_patch(ROOT / "research" / "gui_pending_patch_example.json")
    app.processEvents()
    output = ROOT / "research" / "gui_smoke.png"
    window.grab().save(str(output))
    print(f"标题：{window.windowTitle()}")
    print(f"已选元素：{window.selected_element.name if window.selected_element else '无'}")
    print(f"已编辑 BELE：{active_index}，initial_phase：{original_phase} → {original_phase + 1}")
    print(f"保存前预检：{'通过' if not report.has_errors else '失败'}，待提交变更：{window.edit_session.change_count}")
    print(f"截图：{output}")
    window.close()
    QTimer.singleShot(0, app.quit)
    app.exec()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
