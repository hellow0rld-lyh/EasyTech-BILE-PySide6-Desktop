#!/usr/bin/env python3
"""离屏验证将军的荣耀1 BILE v2 在工作台中以只读模式加载。"""
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
from bile_workbench.theme import apply_dark_theme, configure_high_dpi


def main() -> int:
    configure_high_dpi()
    app = QApplication([])
    apply_dark_theme(app)
    window = MainWindow()
    window.show()
    sample = ROOT / "cross_game_assets" / "general1" / "mtank.bin"
    window.load_workspace(sample)
    assert "BILE v2" in window.subtitle_label.text(), window.subtitle_label.text()
    diagnostics = window.diagnostic_view.toPlainText()
    assert "BILE_V2_FIVE_SECTION_READONLY_PROFILE" in diagnostics, diagnostics
    assert not window.apply_keyframe_button.isEnabled(), "BILE v2 不应开放关键帧写回"
    assert not window.apply_anchor_button.isEnabled(), "BILE v2 不应开放锚点写回"
    output = ROOT / "research" / "gui_general1_v2_readonly.png"
    window.grab().save(str(output))
    print(f"标题：{window.subtitle_label.text()}")
    print(f"截图：{output}")
    window.close()
    QTimer.singleShot(0, app.quit)
    app.exec()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
