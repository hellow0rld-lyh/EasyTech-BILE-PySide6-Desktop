"""Spine 3.8/4.1 完整时间线的只读树状审阅组件。"""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QTreeView, QVBoxLayout, QWidget

from .spine38_timeline import Spine38AnimationArchive
from .spine41_timeline import Spine41AnimationArchive

ROLE_SPINE_ANIMATION = int(Qt.ItemDataRole.UserRole) + 307


class SpineTimelineInspector(QWidget):
    """展示 Spine 已完整读取的 animation/timeline 档案，不提供编辑。"""

    def __init__(self) -> None:
        super().__init__()
        self.on_animation_selected: Callable[[str], None] | None = None
        self._model = QStandardItemModel()
        self._model.setHorizontalHeaderLabels(["动画 / 时间线", "时长或帧数", "目标 / 时间范围"])
        self._view = QTreeView()
        self._view.setModel(self._model)
        self._view.setAlternatingRowColors(True)
        self._view.setUniformRowHeights(True)
        self._view.clicked.connect(self._on_clicked)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(self._view)

    def clear(self) -> None:
        self._model.removeRows(0, self._model.rowCount())

    def set_archive(self, archive: Spine38AnimationArchive | Spine41AnimationArchive | None, selected_name: str | None = None) -> None:
        self.clear()
        if archive is None:
            return
        selected = QModelIndex()
        for animation in archive.animations:
            root = QStandardItem(animation.name)
            root.setEditable(False)
            root.setData(animation.name, ROLE_SPINE_ANIMATION)
            duration = QStandardItem(f"{animation.duration:.3f} s")
            details = QStandardItem(f"{len(animation.timelines)} 条 timeline")
            for item in (duration, details):
                item.setEditable(False)
            by_group: dict[str, list] = {}
            for timeline in animation.timelines:
                by_group.setdefault(timeline.group, []).append(timeline)
            for group, timelines in by_group.items():
                group_item = QStandardItem(f"{group}（{len(timelines)}）")
                group_item.setEditable(False)
                root.appendRow([group_item, QStandardItem(""), QStandardItem("")])
                for timeline in timelines:
                    name = QStandardItem(timeline.kind)
                    frames = QStandardItem(f"{timeline.frame_count} 帧")
                    target = QStandardItem(f"{timeline.target} · {timeline.first_time:.3f}–{timeline.last_time:.3f} s")
                    for item in (name, frames, target):
                        item.setEditable(False)
                    group_item.appendRow([name, frames, target])
            self._model.appendRow([root, duration, details])
            if animation.name == selected_name:
                selected = root.index()
        self._view.expandToDepth(1)
        for column in range(3):
            self._view.resizeColumnToContents(column)
        if selected.isValid():
            self._view.setCurrentIndex(selected)

    def _on_clicked(self, index: QModelIndex) -> None:
        current = index
        while current.isValid():
            name = current.data(ROLE_SPINE_ANIMATION)
            if isinstance(name, str):
                if self.on_animation_selected is not None:
                    self.on_animation_selected(name)
                return
            current = current.parent()
