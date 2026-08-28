from __future__ import annotations

from typing import Callable

from PIL import Image, ImageChops
from PySide6.QtCore import QPoint, QRectF, QTimer, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QWidget,
)

from .bile_format import Element


def pil_to_pixmap(image: Image.Image) -> QPixmap:
    """以独立 RGBA 缓冲转换 Pillow 图像，避免 QImage 持有短生命周期内存。"""
    rgba = image.convert("RGBA")
    raw = rgba.tobytes("raw", "RGBA")
    qimage = QImage(raw, rgba.width, rgba.height, QImage.Format.Format_RGBA8888).copy()
    return QPixmap.fromImage(qimage)


class _HotspotHandle(QGraphicsEllipseItem):
    """画布中的可拖拽热点，不在拖拽过程中触发文档重解析。"""

    def __init__(self, position_changed: Callable[[float, float], None], drag_finished: Callable[[float, float], None]) -> None:
        super().__init__(-9, -9, 18, 18)
        self._position_changed = position_changed
        self._drag_finished = drag_finished
        self.setZValue(50)
        self.setBrush(QBrush(QColor("#FFCC66")))
        self.setPen(QPen(QColor("#2A2030"), 2))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        horizontal = QGraphicsLineItem(-17, 0, 17, 0, self)
        vertical = QGraphicsLineItem(0, -17, 0, 17, self)
        for line in (horizontal, vertical):
            line.setPen(QPen(QColor("#FFF4C7"), 1.5))
            line.setZValue(-1)
        label = QGraphicsSimpleTextItem("热点", self)
        label.setBrush(QBrush(QColor("#FFF4C7")))
        label.setPos(12, -24)
        label.setScale(0.85)

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value):  # type: ignore[no-untyped-def]
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            position = self.pos()
            self._position_changed(position.x(), position.y())
        return super().itemChange(change, value)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().mouseReleaseEvent(event)
        position = self.pos()
        self._drag_finished(position.x(), position.y())


class PreviewView(QGraphicsView):
    """主画布：支持适配、滚轮缩放、手掌平移和直接拖拽热点。"""

    hotspot_changed = Signal(float, float)
    hotspot_drag_finished = Signal(float, float)

    def __init__(self) -> None:
        super().__init__()
        self._scene = QGraphicsScene(self)
        self._pixmap_item = QGraphicsPixmapItem()
        self._scene.addItem(self._pixmap_item)
        self.setScene(self._scene)
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.setBackgroundBrush(QBrush(QColor("#10161D")))
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setMouseTracking(True)
        self._has_content = False
        self._user_zoomed = False
        self._hotspot_handle: _HotspotHandle | None = None
        self._hotspot_signals_suppressed = False
        self._focus_rect = QRectF()

    def set_image(self, image: Image.Image, fit: bool = False, hotspot: tuple[float, float] | None = None, hotspot_editable: bool = False) -> None:
        was_empty = not self._has_content
        self._pixmap_item.setPixmap(pil_to_pixmap(image))
        width, height = image.size
        # 播放动画时不重复扫描每一帧的像素边界；换选内容或显式适配时才重新检测。
        if fit or was_empty:
            self._focus_rect = self._detect_content_rect(image)
        # 预留少量可拖拽空间，但 fit 时不把这部分空白算进图像比例。
        margin = max(64.0, min(512.0, max(width, height) * 0.12))
        self._scene.setSceneRect(QRectF(-margin, -margin, width + margin * 2, height + margin * 2))
        self._has_content = True
        self._set_hotspot_internal(hotspot, hotspot_editable)
        if fit:
            self.fit_content()

    def set_hotspot(self, x: float, y: float, editable: bool = True) -> None:
        """设置图像像素坐标中的热点；拖动只发信号，不直接修改文档。"""
        self._set_hotspot_internal((x, y), editable)

    def clear_hotspot(self) -> None:
        self._set_hotspot_internal(None, False)

    def _set_hotspot_internal(self, hotspot: tuple[float, float] | None, editable: bool) -> None:
        if hotspot is None:
            if self._hotspot_handle is not None:
                self._scene.removeItem(self._hotspot_handle)
                self._hotspot_handle = None
            return
        if self._hotspot_handle is None:
            self._hotspot_handle = _HotspotHandle(self._on_hotspot_position_changed, self._on_hotspot_drag_finished)
            self._scene.addItem(self._hotspot_handle)
        self._hotspot_handle.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, editable)
        self._hotspot_signals_suppressed = True
        self._hotspot_handle.setPos(float(hotspot[0]), float(hotspot[1]))
        self._hotspot_signals_suppressed = False
        self._hotspot_handle.setVisible(True)
        self._hotspot_handle.setOpacity(1.0 if editable else 0.65)

    def _on_hotspot_position_changed(self, x: float, y: float) -> None:
        if not self._hotspot_signals_suppressed:
            rect = self._scene.sceneRect()
            if not rect.contains(self._hotspot_handle.pos() if self._hotspot_handle is not None else rect.center()):
                self._scene.setSceneRect(rect.united(QRectF(x - 64, y - 64, 128, 128)))
            self.hotspot_changed.emit(x, y)

    def _on_hotspot_drag_finished(self, x: float, y: float) -> None:
        if not self._hotspot_signals_suppressed:
            self.hotspot_drag_finished.emit(x, y)

    def fit_content(self) -> None:
        if self._has_content and not self._scene.sceneRect().isEmpty():
            self.resetTransform()
            focus_rect = self._focus_rect if not self._focus_rect.isEmpty() else self._pixmap_item.boundingRect()
            self.fitInView(focus_rect.adjusted(-10, -10, 10, 10), Qt.AspectRatioMode.KeepAspectRatio)
            self._user_zoomed = False

    @staticmethod
    def _detect_content_rect(image: Image.Image) -> QRectF:
        """从角落背景色推断内容区域，避免默认大画布把实际动画缩成小点。"""
        if image.width <= 2 or image.height <= 2:
            return QRectF(0, 0, image.width, image.height)
        background = Image.new("RGBA", image.size, image.getpixel((0, 0)))
        diff = ImageChops.difference(image.convert("RGBA"), background)
        bbox = diff.getbbox()
        if bbox is None:
            return QRectF(0, 0, image.width, image.height)
        left, top, right, bottom = bbox
        if (right - left) * (bottom - top) > image.width * image.height * 0.96:
            return QRectF(0, 0, image.width, image.height)
        return QRectF(float(left), float(top), float(right - left), float(bottom - top))

    def zoom_in(self) -> None:
        self._zoom_by(1.2)

    def zoom_out(self) -> None:
        self._zoom_by(1 / 1.2)

    def _zoom_by(self, factor: float) -> None:
        if not self._has_content:
            return
        current = abs(self.transform().m11()) or 1.0
        target = max(0.12, min(8.0, current * factor))
        self.scale(target / current, target / current)
        self._user_zoomed = True

    def wheelEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        delta = event.angleDelta().y() or event.pixelDelta().y()
        if not delta:
            event.ignore()
            return
        self._zoom_by(1.15 if delta > 0 else 1 / 1.15)
        event.accept()

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        if self._has_content and not self._user_zoomed:
            QTimer.singleShot(0, self.fit_content)


class TimelineWidget(QWidget):
    """只读时间线总览；点击槽位可定位，轨道编辑由上层工作台管理。"""

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumHeight(124)
        self.frame_count = 1
        self.current_slot = 0
        self.selected_channel_index: int | None = None
        self.selected_frame_slot: int | None = None
        self.element: Element | None = None
        self.slot_clicked: Callable[[int], None] | None = None
        self.track_region_clicked: Callable[[int, int], None] | None = None

    def set_element(self, element: Element | None) -> None:
        self.element = element
        self.frame_count = max(1, element.frame_count if element else 1)
        self.current_slot = min(self.current_slot, self.frame_count - 1)
        self.selected_channel_index = None
        self.selected_frame_slot = None
        self.update()

    def set_track_selection(self, channel_index: int | None, frame_slot: int | None) -> None:
        self.selected_channel_index = channel_index
        self.selected_frame_slot = frame_slot
        self.update()

    def set_slot(self, slot: int) -> None:
        self.current_slot = max(0, min(slot, self.frame_count - 1))
        self.update()

    def mousePressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.button() == Qt.MouseButton.LeftButton and self.frame_count > 1:
            left, top, right = 90, 25, max(91, self.width() - 18)
            slot = round((event.position().x() - left) / (right - left) * (self.frame_count - 1))
            slot = max(0, min(slot, self.frame_count - 1))
            rows = max(1, len(self.element.channels) if self.element else 1)
            row_h = max(19, min(30, (self.height() - top - 10) // rows))
            channel_index = int((event.position().y() - top) // row_h)
            if self.track_region_clicked is not None and 0 <= channel_index < rows:
                self.track_region_clicked(channel_index, slot)
            elif self.slot_clicked is not None:
                self.slot_clicked(slot)
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.palette().color(self.backgroundRole()))
        if self.element is None:
            painter.setPen(Qt.GlobalColor.gray)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "选择一个动画元素以查看时间线")
            return
        left, top, right = 90, 25, max(91, self.width() - 18)
        rows = max(1, len(self.element.channels))
        row_h = max(19, min(30, (self.height() - top - 10) // rows))
        width = right - left
        painter.setPen(Qt.GlobalColor.gray)
        painter.drawText(10, 17, f"{self.element.name}  ·  {self.frame_count} 槽位  ·  {len(self.element.channels)} 通道")
        for tick in range(0, self.frame_count, max(1, self.frame_count // 10)):
            x = left + tick / max(1, self.frame_count - 1) * width
            painter.setPen(Qt.GlobalColor.darkGray)
            painter.drawLine(int(x), top - 4, int(x), top + rows * row_h)
            painter.setPen(Qt.GlobalColor.lightGray)
            painter.drawText(int(x) + 2, top - 7, str(tick))
        for channel_index, channel in enumerate(self.element.channels):
            y = top + channel_index * row_h
            if channel_index == self.selected_channel_index:
                painter.fillRect(left, y, right - left, row_h - 8, self.palette().highlight().color().darker(260))
            painter.setPen(Qt.GlobalColor.gray)
            painter.drawText(10, y + row_h - 5, f"通道 {channel_index + 1}")
            painter.setPen(Qt.GlobalColor.darkGray)
            painter.drawLine(left, y + row_h - 8, right, y + row_h - 8)
            for frame in channel.frames:
                x = left + frame.slot / max(1, self.frame_count - 1) * width
                selected = channel_index == self.selected_channel_index and frame.slot == self.selected_frame_slot
                painter.setBrush(Qt.GlobalColor.white if selected else self.palette().highlight())
                painter.setPen(self.palette().highlight().color() if selected else Qt.PenStyle.NoPen)
                radius = 6 if selected else 4
                painter.drawEllipse(QPoint(int(x), y + row_h - 8), radius, radius)
        play_x = left + self.current_slot / max(1, self.frame_count - 1) * width
        painter.setPen(self.palette().highlight().color())
        painter.drawLine(int(play_x), top - 4, int(play_x), top + rows * row_h)
        painter.end()
