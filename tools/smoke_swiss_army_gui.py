from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication, QDockWidget

from bile_workbench.app import MainWindow
from bile_workbench.theme import apply_dark_theme
from bile_workbench.track_context import tracks_for_animation


def main() -> int:
    app = QApplication.instance() or QApplication([])
    apply_dark_theme(app)
    window = MainWindow()
    try:
        window.load_workspace(ROOT / "sample_assets" / "anim_failure.bin")
        animation = window.display_document.animations[0]
        window.select_element(animation)
        context = tracks_for_animation(window.display_document, animation.index)[0]
        window._select_track_context(context)
        before = window.display_document.keyframes[context.keyframe_index]
        window.xform_controls["x"].setValue(before.x + 1.0)
        window._apply_keyframe_edit()
        assert "暂存变更 1 项" in window.change_ledger.summary.text()
        assert window.change_ledger.tree.topLevelItemCount() >= 3
        ledger = window.findChild(QDockWidget, "ChangeLedgerDock")
        assert ledger is not None
        ledger.show()
        ledger.raise_()
        window.resize(1540, 960)
        window.show()
        QCoreApplication.processEvents()
        screenshot = ROOT / "research" / "gui_swiss_army_ledger.png"
        window.grab().save(str(screenshot))
        print(f"动画档案/变更账本冒烟通过：BELE[{context.keyframe_index}]；截图：{screenshot}")
        return 0
    finally:
        window.close()


if __name__ == "__main__":
    raise SystemExit(main())
