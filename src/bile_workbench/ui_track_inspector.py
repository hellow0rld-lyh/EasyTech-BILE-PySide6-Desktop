"""当前动画槽位的活动 BILE Track 检查器。"""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QTreeView, QVBoxLayout, QWidget

from .track_context import TrackContext


ROLE_TRACK_CONTEXT = int(Qt.ItemDataRole.UserRole) + 121


class TrackInspector(QWidget):
    """只读列出活动 Track；选择动作由上层文档会话验证并同步。"""

    def __init__(self) -> None:
        super().__init__()
        self.on_track_selected: Callable[[TrackContext], None] | None = None
        self._model = QStandardItemModel()
        self._model.setHorizontalHeaderLabels(["通道", "保持段", "BELE", "目标", "类型"])
        self._view = QTreeView()
        self._view.setModel(self._model)
        self._view.setRootIsDecorated(False)
        self._view.setAlternatingRowColors(True)
        self._view.clicked.connect(self._on_clicked)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(self._view)

    def set_contexts(self, contexts: tuple[TrackContext, ...], selected_keyframe_index: int | None = None) -> None:
        self._model.removeRows(0, self._model.rowCount())
        selected = QModelIndex()
        for context in contexts:
            channel = QStandardItem(f"通道 {context.channel_index + 1} · Track {context.track_index + 1}")
            channel.setData(context, ROLE_TRACK_CONTEXT)
            hold = QStandardItem(f"{context.frame_slot}–{context.hold_end_slot}")
            keyframe = QStandardItem(f"BELE[{context.keyframe_index}]")
            target = QStandardItem(context.target_element_name)
            kind = QStandardItem("精灵" if context.target_is_sprite else "子动画")
            for item in (channel, hold, keyframe, target, kind):
                item.setEditable(False)
            self._model.appendRow([channel, hold, keyframe, target, kind])
            if context.keyframe_index == selected_keyframe_index:
                selected = channel.index()
        for column in range(self._model.columnCount()):
            self._view.resizeColumnToContents(column)
        if selected.isValid():
            self._view.setCurrentIndex(selected)

    def _on_clicked(self, index: QModelIndex) -> None:
        root = self._model.item(index.row(), 0)
        context = root.data(ROLE_TRACK_CONTEXT) if root is not None else None
        if isinstance(context, TrackContext) and self.on_track_selected is not None:
            self.on_track_selected(context)
