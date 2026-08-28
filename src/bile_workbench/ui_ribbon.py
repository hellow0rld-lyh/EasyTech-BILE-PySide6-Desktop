"""可测试的任务型 Ribbon 控件。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


@dataclass(frozen=True)
class RibbonGroupSpec:
    label: str
    actions: tuple[QAction, ...]
    columns: int = 2


class RibbonGroup(QFrame):
    """Ribbon 中的一个业务功能组；按钮直接复用既有 QAction。"""

    def __init__(self, spec: RibbonGroupSpec) -> None:
        super().__init__()
        self.setObjectName("RibbonGroup")
        self.setProperty("ribbonGroup", True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 5, 8, 4)
        outer.setSpacing(3)
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(3)
        grid.setVerticalSpacing(3)
        columns = max(1, spec.columns)
        for position, action in enumerate(spec.actions):
            button = QToolButton()
            button.setDefaultAction(action)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            button.setAutoRaise(True)
            button.setMinimumWidth(74)
            button.setMaximumWidth(122)
            button.setMinimumHeight(30)
            button.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
            grid.addWidget(button, position // columns, position % columns)
        outer.addLayout(grid, 1)
        caption = QLabel(spec.label)
        caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        caption.setProperty("muted", True)
        caption.setObjectName("RibbonGroupCaption")
        outer.addWidget(caption)


class RibbonScrollArea(QScrollArea):
    """Ribbon 页面滚动容器；内容超出时滚轮始终有明确的垂直入口。"""

    def __init__(self) -> None:
        super().__init__()
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def eventFilter(self, watched, event) -> bool:  # type: ignore[no-untyped-def]
        if event.type() == QEvent.Type.Wheel:
            self.wheelEvent(event)
            return event.isAccepted()
        return super().eventFilter(watched, event)

    def wheelEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        """优先纵向滚动 Ribbon；没有纵向溢出时再允许横向浏览。"""
        delta = event.angleDelta().y() or event.pixelDelta().y()
        if delta:
            bar = self.verticalScrollBar()
            if bar.maximum() > 0:
                bar.setValue(bar.value() - delta)
                event.accept()
                return
        horizontal_delta = event.angleDelta().x() or event.pixelDelta().x()
        if horizontal_delta:
            bar = self.horizontalScrollBar()
            if bar.maximum() > 0:
                bar.setValue(bar.value() - horizontal_delta)
                event.accept()
                return
        super().wheelEvent(event)


class TaskRibbon(QWidget):
    """以任务为核心的 Ribbon，支持上下文页、滚轮和窄窗口溢出。"""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("TaskRibbon")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMinimumHeight(86)
        # Ribbon 不再无限向下挤压画布；超出区域进入页面滚动容器。
        self.setMaximumHeight(220)
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        self._tabs.setMovable(False)
        self._tabs.setUsesScrollButtons(True)
        self._tabs.tabBar().setExpanding(False)
        self._tabs.tabBar().setUsesScrollButtons(True)
        self._pages: dict[str, QWidget] = {}
        self._scroll_areas: dict[str, RibbonScrollArea] = {}
        self._tab_indices: dict[str, int] = {}
        self._contextual: set[str] = set()
        self._quick_bar = QFrame()
        self._quick_bar.setObjectName("RibbonQuickAccess")
        self._quick_layout = QHBoxLayout(self._quick_bar)
        self._quick_layout.setContentsMargins(8, 2, 8, 2)
        self._quick_layout.setSpacing(2)
        quick_label = QLabel("快速操作")
        quick_label.setProperty("muted", True)
        self._quick_layout.addWidget(quick_label)
        self._quick_layout.addStretch(1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._quick_bar)
        layout.addWidget(self._tabs, 1)

    def add_quick_actions(self, actions: Iterable[QAction]) -> None:
        """添加紧凑的跨任务动作；不再用独立 QToolBar 占用功能区高度。"""
        for action in actions:
            button = QToolButton()
            button.setDefaultAction(action)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            button.setAutoRaise(True)
            self._quick_layout.insertWidget(self._quick_layout.count() - 1, button)

    def add_tab(self, tab_id: str, label: str, groups: Iterable[RibbonGroupSpec], *, contextual: bool = False) -> None:
        if tab_id in self._pages:
            raise ValueError(f"Ribbon 工具页已存在：{tab_id}")
        page = QWidget()
        page.setObjectName(f"RibbonPage_{tab_id}")
        page.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        row = QHBoxLayout(page)
        row.setContentsMargins(8, 5, 8, 5)
        row.setSpacing(5)
        for spec in groups:
            row.addWidget(RibbonGroup(spec))
        row.addStretch(1)

        scroll_area = RibbonScrollArea()
        scroll_area.setObjectName(f"RibbonScrollArea_{tab_id}")
        scroll_area.setWidget(page)
        # QToolButton 等子控件可能先收到 Wheel；统一转交给页面滚动区，
        # 这样用户不必把鼠标精确放在空白处才能滚动 Ribbon。
        for child in (page, *page.findChildren(QWidget)):
            child.installEventFilter(scroll_area)
        index = self._tabs.addTab(scroll_area, label)
        self._pages[tab_id] = page
        self._scroll_areas[tab_id] = scroll_area
        self._tab_indices[tab_id] = index
        if contextual:
            self._contextual.add(tab_id)
            self._tabs.setTabVisible(index, False)

    def set_context_visible(self, tab_id: str, visible: bool, *, activate: bool = False) -> None:
        if tab_id not in self._contextual:
            raise ValueError(f"Ribbon 工具页不是上下文页：{tab_id}")
        index = self._tab_indices[tab_id]
        self._tabs.setTabVisible(index, visible)
        if visible and activate:
            self._tabs.setCurrentIndex(index)
        elif not visible and self._tabs.currentIndex() == index:
            for candidate in range(self._tabs.count()):
                if self._tabs.isTabVisible(candidate):
                    self._tabs.setCurrentIndex(candidate)
                    break

    def select_tab(self, tab_id: str) -> None:
        index = self._tab_indices[tab_id]
        if self._tabs.isTabVisible(index):
            self._tabs.setCurrentIndex(index)
