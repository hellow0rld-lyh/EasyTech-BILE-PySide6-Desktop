"""文档驱动的动画根导航视图。"""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QTreeView, QVBoxLayout, QWidget

from .bile_format import BileDocument


ROLE_ELEMENT_INDEX = int(Qt.ItemDataRole.UserRole) + 101


class AnimationNavigator(QWidget):
    """只呈现可播放的根动画；精灵仍保留在资源浏览器中。"""

    def __init__(self) -> None:
        super().__init__()
        self.on_animation_selected: Callable[[int], None] | None = None
        self._model = QStandardItemModel()
        self._model.setHorizontalHeaderLabels(["动画", "槽位", "通道"])
        self._view = QTreeView()
        self._view.setModel(self._model)
        self._view.setRootIsDecorated(False)
        self._view.setAlternatingRowColors(True)
        self._view.setSortingEnabled(False)
        self._view.clicked.connect(self._on_clicked)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(self._view)

    def set_document(self, document: BileDocument | None, selected_index: int | None = None) -> None:
        self._model.removeRows(0, self._model.rowCount())
        if document is None:
            return
        selected_model_index = QModelIndex()
        for element in document.animations:
            name = QStandardItem(element.name)
            name.setEditable(False)
            name.setData(element.index, ROLE_ELEMENT_INDEX)
            slots = QStandardItem(str(element.frame_count))
            channels = QStandardItem(str(element.channel_count))
            for item in (slots, channels):
                item.setEditable(False)
            self._model.appendRow([name, slots, channels])
            if element.index == selected_index:
                selected_model_index = name.index()
        self._view.resizeColumnToContents(0)
        self._view.resizeColumnToContents(1)
        self._view.resizeColumnToContents(2)
        if selected_model_index.isValid():
            self._view.setCurrentIndex(selected_model_index)

    def _on_clicked(self, index: QModelIndex) -> None:
        root = self._model.item(index.row(), 0)
        element_index = root.data(ROLE_ELEMENT_INDEX) if root is not None else None
        if isinstance(element_index, int) and self.on_animation_selected is not None:
            self.on_animation_selected(element_index)
