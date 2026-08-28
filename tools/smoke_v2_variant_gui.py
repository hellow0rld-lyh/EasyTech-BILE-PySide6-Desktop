"""离屏验证零轨帧 BILE v2 变体在真实工作台中的加载、预览和轨道导航。"""
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
from bile_workbench.theme import apply_dark_theme, configure_high_dpi
from bile_workbench.track_context import active_tracks_at_slot

SAMPLES = [
    ROOT / "incoming" / "cross_era_20260822" / "世2测试" / "artillery_cn.bin",
    ROOT / "incoming" / "cross_era_20260822" / "欧3测试" / "artillery_am.bin",
]


def main() -> int:
    configure_high_dpi()
    app = QApplication([])
    apply_dark_theme(app)
    window = MainWindow()
    window.show()
    summaries: list[str] = []
    for path in SAMPLES:
        if not path.exists():
            raise FileNotFoundError(path)
        window.load_workspace(path)
        assert window.workspace is not None
        assert window.workspace.document.header.version == 2
        assert "BILE v2" in window.subtitle_label.text(), window.subtitle_label.text()
        track_count = sum(
            len(frame.tracks)
            for element in window.workspace.document.elements
            for channel in element.channels
            for frame in channel.frames
        )
        assert track_count == len(window.workspace.document.keyframes)
        best: tuple[object, int, int] | None = None
        for animation in window.workspace.document.animations:
            for slot in sorted({0, max(0, animation.frame_count // 2), max(0, animation.frame_count - 1)}):
                image = render_frame(window.workspace.document, window.workspace.atlas, animation.name, slot)
                score = sum(1 for red, green, blue, alpha in image.getdata() if alpha and max(red, green, blue) > 48)
                if best is None or score > best[2]:
                    best = (animation, slot, score)
        assert best is not None and best[2] > 0, f"未找到可见代表帧：{path.name}"
        animation, slot, score = best
        window.select_element(animation)
        window.set_slot(slot)
        contexts = active_tracks_at_slot(window.display_document, animation.index, slot)
        if contexts:
            window._select_track_context(contexts[0])
        summaries.append(f"{path.name}: {animation.name}@{slot}，非黑像素 {score}，活动 Track {len(contexts)}")
    dock = window.findChild(QDockWidget, "TrackInspectorDock")
    assert dock is not None
    dock.raise_()
    app.processEvents()
    output = ROOT / "research" / "gui_v2_variant_eu3.png"
    window.grab().save(str(output))
    for summary in summaries:
        print(summary)
    print(f"截图：{output}")
    window.close()
    QTimer.singleShot(0, app.quit)
    app.exec()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
