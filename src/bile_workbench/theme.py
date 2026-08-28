"""BILE Workbench 的高 DPI 启动策略与基础主题。

宿主只提供 light/dark 两套基础主题；个性化视觉由外部主题插件通过 QSS 叠加。
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


DARK_QSS = """
* {
    font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif;
    font-size: 10pt;
}
QMainWindow, QDialog, QWidget {
    background: #171A1F;
    color: #E7EAF0;
}
QMenuBar {
    background: #171A1F;
    color: #C8CDD7;
    border-bottom: 1px solid #2A303A;
    padding: 2px 6px;
}
QMenuBar::item { padding: 6px 10px; border-radius: 4px; }
QMenuBar::item:selected { background: #293241; color: #FFFFFF; }
QMenu {
    background: #20252D;
    border: 1px solid #343C49;
    padding: 5px;
}
QMenu::item { padding: 7px 28px 7px 12px; border-radius: 4px; }
QMenu::item:selected { background: #245DAB; }
QToolBar {
    background: #1D222A;
    border: none;
    border-bottom: 1px solid #2A303A;
    spacing: 4px;
    padding: 4px 7px;
}
QToolButton {
    background: transparent;
    color: #C8CDD7;
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 5px 8px;
}
QToolButton:hover { background: #293241; border-color: #3C4656; }
QToolButton:pressed, QToolButton:checked { background: #1F4F8D; color: #FFFFFF; }
QToolButton:disabled { color: #657083; background: transparent; border-color: transparent; }
QFrame#RibbonQuickAccess {
    background: #171A1F;
    border-bottom: 1px solid #292F39;
}
QFrame#RibbonQuickAccess QToolButton { padding: 4px 7px; font-size: 9pt; }
QToolBar#TaskRibbonToolBar {
    background: #1A1F26;
    border-bottom: 1px solid #343D49;
    padding: 0;
    spacing: 0;
}
QWidget#TaskRibbon { background: #1A1F26; }
QWidget#TaskRibbon QTabWidget::pane {
    border: none;
    background: #202731;
    min-height: 86px;
}
QWidget#TaskRibbon QTabBar::tab {
    min-width: 62px;
    padding: 8px 15px;
    border: none;
    border-bottom: 3px solid transparent;
    border-radius: 0;
    background: #1A1F26;
    color: #9BA7B8;
    font-weight: 600;
}
QWidget#TaskRibbon QTabBar::tab:selected {
    background: #242D39;
    color: #F4F7FB;
    border-bottom-color: #3B8EEA;
}
QWidget#TaskRibbon QTabBar::tab:hover:!selected { background: #222B36; color: #E6EDF7; }
QFrame[ribbonGroup="true"] {
    background: #202731;
    border: 1px solid #303A48;
    border-radius: 5px;
    min-width: 96px;
}
QFrame[ribbonGroup="true"] QToolButton {
    min-height: 28px;
    padding: 4px 7px;
    border-radius: 4px;
    font-size: 9pt;
}
QLabel#RibbonGroupCaption {
    color: #8895A8;
    border-top: 1px solid #303A48;
    padding-top: 3px;
    font-size: 8pt;
    font-weight: 600;
}
QDockWidget { titlebar-close-icon: none; titlebar-normal-icon: none; }
QDockWidget::title {
    text-align: left;
    background: #1D222A;
    color: #BFC7D4;
    padding: 8px 10px;
    border-bottom: 1px solid #2A303A;
    font-weight: 600;
}
QTreeView, QListView, QTableView, QTextEdit, QPlainTextEdit {
    background: #1D222A;
    alternate-background-color: #222832;
    color: #DCE1E8;
    border: 1px solid #2D3541;
    border-radius: 5px;
    selection-background-color: #245DAB;
    selection-color: #FFFFFF;
}
QTreeView::item, QListView::item { padding: 5px 6px; border-radius: 3px; }
QTreeView::item:hover, QListView::item:hover { background: #28313E; }
QHeaderView::section {
    background: #222832;
    color: #AEB8C8;
    border: none;
    border-bottom: 1px solid #343D49;
    padding: 7px 8px;
    font-weight: 600;
}
QTabWidget::pane { border: 1px solid #2D3541; background: #1D222A; top: -1px; }
QTabBar::tab {
    background: #1A1F26;
    color: #8E99A9;
    border: 1px solid #2D3541;
    border-bottom: none;
    padding: 7px 13px;
    margin-right: 2px;
    border-top-left-radius: 5px;
    border-top-right-radius: 5px;
}
QTabBar::tab:selected { background: #242C36; color: #FFFFFF; }
QTabBar::tab:hover:!selected { background: #222832; color: #DCE1E8; }
QPushButton {
    background: #2A3646;
    color: #F3F6FA;
    border: 1px solid #3A495B;
    border-radius: 5px;
    padding: 6px 11px;
    min-height: 18px;
}
QPushButton:hover { background: #34465D; border-color: #53708F; }
QPushButton:pressed { background: #1E2D40; }
QPushButton[primary="true"] { background: #2365B3; border-color: #3A82D1; }
QPushButton[primary="true"]:hover { background: #2C74C7; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background: #202731;
    color: #E7EAF0;
    border: 1px solid #394454;
    border-radius: 4px;
    padding: 5px 7px;
    min-height: 18px;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border: 1px solid #4C95E9;
    background: #222C38;
}
QSlider::groove:horizontal { height: 5px; background: #303946; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #2C74C7; border-radius: 2px; }
QSlider::handle:horizontal { width: 13px; margin: -5px 0; border-radius: 7px; background: #E6EDF7; border: 1px solid #7A8799; }
QScrollBar:vertical { background: #1A1F26; width: 12px; margin: 0; }
QScrollBar::handle:vertical { background: #3B4655; min-height: 28px; border-radius: 5px; margin: 2px; }
QScrollBar::handle:vertical:hover { background: #54657A; }
QScrollBar:horizontal { background: #1A1F26; height: 12px; margin: 0; }
QScrollBar::handle:horizontal { background: #3B4655; min-width: 28px; border-radius: 5px; margin: 2px; }
QScrollBar::handle:horizontal:hover { background: #54657A; }
QStatusBar { background: #1D222A; color: #9DA8B8; border-top: 1px solid #2A303A; min-height: 23px; }
QLabel[muted="true"] { color: #8E99A9; }
QFrame[card="true"] { background: #202731; border: 1px solid #303A48; border-radius: 7px; }
QSplitter::handle { background: #252D38; }
QFrame#PluginBadge { background: #202731; border: 1px solid #3A4758; border-radius: 8px; }
QLabel#PluginBadgeTitle { color: #E7EAF0; font-weight: 700; }
QLabel#PluginBadgeMeta { color: #8E99A9; }
"""


LIGHT_QSS = """
* {
    font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif;
    font-size: 10pt;
}
QMainWindow, QDialog, QWidget { background: #F2F5F9; color: #1E2936; }
QMenuBar { background: #F2F5F9; color: #334155; border-bottom: 1px solid #D6DEE8; padding: 2px 6px; }
QMenuBar::item { padding: 6px 10px; border-radius: 4px; }
QMenuBar::item:selected { background: #DCE8F7; color: #17345C; }
QMenu { background: #FFFFFF; color: #223044; border: 1px solid #CBD5E1; padding: 5px; }
QMenu::item { padding: 7px 28px 7px 12px; border-radius: 4px; }
QMenu::item:selected { background: #D7E7FA; color: #17345C; }
QToolBar { background: #FFFFFF; border: none; border-bottom: 1px solid #D6DEE8; spacing: 4px; padding: 4px 7px; }
QToolButton { background: transparent; color: #334155; border: 1px solid transparent; border-radius: 4px; padding: 5px 8px; }
QToolButton:hover { background: #E6EEF9; border-color: #B7CBE4; }
QToolButton:pressed, QToolButton:checked { background: #C7DCF5; color: #143D6B; }
QToolButton:disabled { color: #9AA7B6; background: transparent; border-color: transparent; }
QFrame#RibbonQuickAccess { background: #F2F5F9; border-bottom: 1px solid #D6DEE8; }
QFrame#RibbonQuickAccess QToolButton { padding: 4px 7px; font-size: 9pt; }
QToolBar#TaskRibbonToolBar { background: #F8FAFC; border-bottom: 1px solid #C9D5E3; padding: 0; spacing: 0; }
QWidget#TaskRibbon { background: #F8FAFC; }
QWidget#TaskRibbon QTabWidget::pane { border: none; background: #EEF3F8; min-height: 86px; }
QWidget#TaskRibbon QTabBar::tab { min-width: 62px; padding: 8px 15px; border: none; border-bottom: 3px solid transparent; border-radius: 0; background: #F8FAFC; color: #64748B; font-weight: 600; }
QWidget#TaskRibbon QTabBar::tab:selected { background: #E3EDF9; color: #173B66; border-bottom-color: #3B82D0; }
QWidget#TaskRibbon QTabBar::tab:hover:!selected { background: #EDF3FA; color: #244B77; }
QFrame[ribbonGroup="true"] { background: #F8FAFC; border: 1px solid #C9D5E3; border-radius: 5px; min-width: 96px; }
QFrame[ribbonGroup="true"] QToolButton { min-height: 28px; padding: 4px 7px; border-radius: 4px; font-size: 9pt; }
QLabel#RibbonGroupCaption { color: #6B7C90; border-top: 1px solid #D5DEE9; padding-top: 3px; font-size: 8pt; font-weight: 600; }
QDockWidget { titlebar-close-icon: none; titlebar-normal-icon: none; }
QDockWidget::title { text-align: left; background: #FFFFFF; color: #3A4A5E; padding: 8px 10px; border-bottom: 1px solid #D6DEE8; font-weight: 600; }
QTreeView, QListView, QTableView, QTextEdit, QPlainTextEdit { background: #FFFFFF; alternate-background-color: #F4F7FA; color: #27364A; border: 1px solid #CBD5E1; border-radius: 5px; selection-background-color: #C7DCF5; selection-color: #17345C; }
QTreeView::item, QListView::item { padding: 5px 6px; border-radius: 3px; }
QTreeView::item:hover, QListView::item:hover { background: #E8F0F9; }
QHeaderView::section { background: #EDF2F7; color: #52657A; border: none; border-bottom: 1px solid #D6DEE8; padding: 7px 8px; font-weight: 600; }
QTabWidget::pane { border: 1px solid #CBD5E1; background: #FFFFFF; top: -1px; }
QTabBar::tab { background: #EEF2F7; color: #64748B; border: 1px solid #CBD5E1; border-bottom: none; padding: 7px 13px; margin-right: 2px; border-top-left-radius: 5px; border-top-right-radius: 5px; }
QTabBar::tab:selected { background: #FFFFFF; color: #1D3B60; }
QTabBar::tab:hover:!selected { background: #E4ECF5; color: #284A70; }
QPushButton { background: #E7EDF5; color: #26384E; border: 1px solid #B9C8D8; border-radius: 5px; padding: 6px 11px; min-height: 18px; }
QPushButton:hover { background: #DCE8F5; border-color: #8EACC9; }
QPushButton:pressed { background: #CBDCF0; }
QPushButton[primary="true"] { background: #3C78BB; color: #FFFFFF; border-color: #2C65A3; }
QPushButton[primary="true"]:hover { background: #4B89CF; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox { background: #FFFFFF; color: #233247; border: 1px solid #B9C8D8; border-radius: 4px; padding: 5px 7px; min-height: 18px; }
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus { border: 1px solid #4C88C7; background: #F8FBFF; }
QSlider::groove:horizontal { height: 5px; background: #CBD5E1; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #4B86C2; border-radius: 2px; }
QSlider::handle:horizontal { width: 13px; margin: -5px 0; border-radius: 7px; background: #FFFFFF; border: 1px solid #7295B6; }
QScrollBar:vertical { background: #E9EEF4; width: 12px; margin: 0; }
QScrollBar::handle:vertical { background: #AEBCCD; min-height: 28px; border-radius: 5px; margin: 2px; }
QScrollBar::handle:vertical:hover { background: #8FA5BD; }
QScrollBar:horizontal { background: #E9EEF4; height: 12px; margin: 0; }
QScrollBar::handle:horizontal { background: #AEBCCD; min-width: 28px; border-radius: 5px; margin: 2px; }
QScrollBar::handle:horizontal:hover { background: #8FA5BD; }
QStatusBar { background: #FFFFFF; color: #617286; border-top: 1px solid #D6DEE8; min-height: 23px; }
QLabel[muted="true"] { color: #6B7C90; }
QFrame[card="true"] { background: #FFFFFF; border: 1px solid #D0DAE5; border-radius: 7px; }
QSplitter::handle { background: #D1DCE8; }
QFrame#PluginBadge { background: #FFFFFF; border: 1px solid #C5D2E0; border-radius: 8px; }
QLabel#PluginBadgeTitle { color: #1E3B5E; font-weight: 700; }
QLabel#PluginBadgeMeta { color: #6B7C90; }
"""

BASE_QSS = {"light": LIGHT_QSS, "dark": DARK_QSS}


def configure_high_dpi() -> None:
    """在 QApplication 构造前调用，避免多显示器缩放被整数取整。"""
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )


def compose_theme(mode: str, plugin_qss: str = "") -> str:
    """返回基础主题加当前插件覆盖层；切换时由调用方完整替换。"""
    if mode not in BASE_QSS:
        raise ValueError(f"未知基础主题：{mode}")
    return BASE_QSS[mode] + ("\n/* external theme plugin */\n" + plugin_qss if plugin_qss.strip() else "")


def apply_theme(app: QApplication, mode: str, plugin_qss: str = "") -> None:
    """应用浅色/深色基础主题及可选外部插件 QSS。"""
    app.setStyle("Fusion")
    palette = QPalette()
    if mode == "dark":
        palette.setColor(QPalette.ColorRole.Window, QColor("#171A1F"))
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#E7EAF0"))
        palette.setColor(QPalette.ColorRole.Base, QColor("#1D222A"))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#222832"))
        palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#20252D"))
        palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#F3F6FA"))
        palette.setColor(QPalette.ColorRole.Text, QColor("#E7EAF0"))
        palette.setColor(QPalette.ColorRole.Button, QColor("#2A3646"))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor("#F3F6FA"))
        palette.setColor(QPalette.ColorRole.Highlight, QColor("#245DAB"))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#778398"))
    elif mode == "light":
        palette.setColor(QPalette.ColorRole.Window, QColor("#F2F5F9"))
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#1E2936"))
        palette.setColor(QPalette.ColorRole.Base, QColor("#FFFFFF"))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#F4F7FA"))
        palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#FFFFFF"))
        palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#1E2936"))
        palette.setColor(QPalette.ColorRole.Text, QColor("#233247"))
        palette.setColor(QPalette.ColorRole.Button, QColor("#E7EDF5"))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor("#26384E"))
        palette.setColor(QPalette.ColorRole.Highlight, QColor("#4B86C2"))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#8A99AA"))
    else:
        raise ValueError(f"未知基础主题：{mode}")
    app.setPalette(palette)
    app.setStyleSheet(compose_theme(mode, plugin_qss))


def apply_dark_theme(app: QApplication) -> None:
    """兼容旧入口：应用深色基础主题。"""
    apply_theme(app, "dark")


def apply_light_theme(app: QApplication) -> None:
    """应用浅色基础主题。"""
    apply_theme(app, "light")
