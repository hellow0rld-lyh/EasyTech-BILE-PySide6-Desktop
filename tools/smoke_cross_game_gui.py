#!/usr/bin/env python3
"""离屏验证跨游戏 BILE 样本在工作台中的加载、标题和诊断画像。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDockWidget

from bile_workbench.app import MainWindow
from bile_workbench.preview_renderer import render_frame
from bile_workbench.track_context import active_tracks_at_slot
from bile_workbench.theme import apply_dark_theme, configure_high_dpi

SAMPLES = [
    (ROOT / "cross_game_assets" / "general3" / "anim_fire.bin", "BILE v4", "WEBP"),
    (ROOT / "cross_game_assets" / "eu6" / "anim_newui.bin", "BILE v4", "XML 声明"),
    (ROOT / "cross_game_assets" / "wc3" / "anim_gameover.bin", "BILE v3", "PNG"),
]


def main() -> int:
    configure_high_dpi()
    app = QApplication([])
    apply_dark_theme(app)
    window = MainWindow()
    window.show()
    summaries = []
    for path, version, marker in SAMPLES:
        window.load_workspace(path)
        subtitle = window.subtitle_label.text()
        diagnostics = window.diagnostic_view.toPlainText()
        assert version in subtitle, subtitle
        assert marker in subtitle, subtitle
        assert "BILE_CROSS_GAME_PROFILE" in diagnostics, diagnostics
        summaries.append({"file": path.name, "subtitle": subtitle})
    # 最后一项为世界征服者3：在每个动画的首/中/末槽位中选择 RGB 非黑像素最多者，避免验证图误截默认低对比帧。
    assert window.workspace is not None
    selected_visible = None
    best_score = -1
    best_target = None
    for animation in window.workspace.document.animations:
        for slot in sorted({0, max(0, animation.frame_count // 2), max(0, animation.frame_count - 1)}):
            frame = render_frame(window.workspace.document, window.workspace.atlas, animation.name, slot)
            score = sum(1 for red, green, blue, alpha in frame.getdata() if alpha and max(red, green, blue) > 48)
            if score > best_score:
                best_score = score
                best_target = (animation, slot)
    assert best_target is not None and best_score > 0, "世界征服者3样本中未找到高对比动画帧"
    animation, slot = best_target
    window.select_element(animation)
    window.set_slot(slot)
    contexts = active_tracks_at_slot(window.display_document, animation.index, slot)
    assert contexts, "当前可见帧应有活动 Track"
    window._select_track_context(contexts[0])
    track_dock = window.findChild(QDockWidget, "TrackInspectorDock")
    assert track_dock is not None
    assert window.track_inspector._model.rowCount() > 0, "当前可见帧应有活动 Track"
    track_dock.raise_()
    app.processEvents()
    selected_visible = f"{animation.name}@{slot}，非黑像素 {best_score}；活动 Track {window.track_inspector._model.rowCount()} 条"
    summaries.append({"visible_frame": selected_visible})
    output = ROOT / "research" / "gui_cross_game_wc3.png"
    window.grab().save(str(output))
    for item in summaries:
        if "file" in item:
            print(f"{item['file']}: {item['subtitle']}")
        else:
            print(f"世界征服者3可见验证帧：{item['visible_frame']}")
    print(f"截图：{output}")
    window.close()
    QTimer.singleShot(0, app.quit)
    app.exec()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
