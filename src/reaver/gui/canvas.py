"""Pixel-coordinate image canvas: wheel zoom, middle-drag pan, square brush."""
import math
from PySide6.QtCore import Qt, QPointF, QRectF, Signal
from PySide6.QtGui import QPainter, QPixmap, QPen, QColor
from PySide6.QtWidgets import QLabel


class ImageCanvas(QLabel):
    stroke = Signal(object, object, bool)
    brush_step = Signal(int)
    view_changed = Signal()

    def __init__(self, text='', parent=None):
        super().__init__(text, parent)
        self._image = QPixmap()
        self.zoom = 1.0
        self.origin = QPointF()
        self.scale_factor = 1.0
        self.editable = False
        self.brush_size = 1
        self.last_pixel = None
        self.pan_point = None
        self.hover = None
        self.markers = []
        self.setMouseTracking(True)

    def pixmap(self):
        return self._image

    def clear(self):
        self._image = QPixmap()
        super().clear()

    def setPixmap(self, pixmap):
        changed = pixmap.size() != self._image.size()
        self._image = pixmap
        if changed:
            self.fit()
        self.update()

    def fit(self):
        self.zoom = 1.0
        if not self._image.isNull():
            self.scale_factor = min(self.width()/self._image.width(), self.height()/self._image.height())
            self.origin = QPointF((self.width()-self._image.width()*self.scale_factor)/2,
                                  (self.height()-self._image.height()*self.scale_factor)/2)
        self.update()
        self.view_changed.emit()

    def pixel_at(self, point):
        p = (QPointF(point)-self.origin)/self.scale_factor
        return (math.floor(p.x()), math.floor(p.y()))

    def inside(self, pixel):
        return 0 <= pixel[0] < self._image.width() and 0 <= pixel[1] < self._image.height()

    def bound(self):
        for axis, extent, viewport in [('x',self._image.width(),self.width()),('y',self._image.height(),self.height())]:
            length = extent*self.scale_factor
            value = (viewport-length)/2 if length <= viewport else min(0,max(viewport-length,getattr(self.origin,axis)()))
            getattr(self.origin,'set'+axis.upper())(value)

    def zoom_at(self, point, factor):
        if self._image.isNull():
            return
        new_zoom = max(1, self.zoom*factor)
        if not math.isfinite(new_zoom):
            return
        ratio = new_zoom/self.zoom
        self.origin = QPointF(point) - (QPointF(point)-self.origin)*ratio
        self.scale_factor *= ratio
        self.zoom = new_zoom
        self.bound()
        self.update()
        self.view_changed.emit()

    def wheelEvent(self, event):
        if self.last_pixel is not None:
            return
        if event.angleDelta().y() == 0:
            return
        steps = 1 if event.angleDelta().y()>0 else -1
        if event.modifiers() == Qt.ControlModifier:
            self.brush_step.emit(steps)
        else:
            self.zoom_at(event.position(), (10/9)**steps)
        event.accept()

    def mousePressEvent(self, event):
        if self._image.isNull() or self.last_pixel is not None or self.pan_point is not None:
            return
        if event.button() == Qt.MiddleButton:
            self.pan_point = event.position()
            self.setCursor(Qt.ClosedHandCursor)
        elif self.editable and event.button() in (Qt.LeftButton, Qt.RightButton):
            point = self.pixel_at(event.position())
            if self.inside(point):
                self.last_pixel = point
                self.add = event.button() == Qt.LeftButton
                self.stroke.emit(point, point, self.add)

    def mouseMoveEvent(self, event):
        self.hover = event.position()
        if self.pan_point is not None:
            self.origin += event.position()-self.pan_point
            self.pan_point = event.position()
            self.bound()
        elif self.last_pixel is not None and self.editable:
            point = self.pixel_at(event.position())
            self.stroke.emit(self.last_pixel, point, self.add)
            self.last_pixel = point
        self.update()

    def mouseReleaseEvent(self, event):
        self.last_pixel = None
        self.pan_point = None
        self.unsetCursor()

    def leaveEvent(self, event):
        self.hover = None
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.zoom == 1:
            self.fit()
        elif not self._image.isNull():
            center = (QPointF(event.oldSize().width()/2, event.oldSize().height()/2)-self.origin)/self.scale_factor
            self.scale_factor = self.zoom * min(self.width()/self._image.width(), self.height()/self._image.height())
            self.origin = QPointF(self.width()/2, self.height()/2)-center*self.scale_factor
            self.bound()

    def paintEvent(self, event):
        if self._image.isNull():
            super().paintEvent(event)
            return
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.palette().window())
        painter.drawPixmap(QRectF(self.origin,QPointF(self.origin.x()+self._image.width()*self.scale_factor,
                            self.origin.y()+self._image.height()*self.scale_factor)), self._image, QRectF(self._image.rect()))
        painter.save()
        painter.setClipRect(QRectF(self.origin.x(),self.origin.y(),self._image.width()*self.scale_factor,self._image.height()*self.scale_factor))
        painter.setRenderHint(QPainter.Antialiasing)
        radius = 3*self.logicalDpiX()/72  # MATLAB default six-point filled circles.
        for points, color in self.markers:
            painter.setPen(QPen(QColor(*color), .5*self.logicalDpiX()/72))
            painter.setBrush(QColor(*color))
            for x,y in points:
                center = self.origin + QPointF((x+.5)*self.scale_factor,(y+.5)*self.scale_factor)
                painter.drawEllipse(center,radius,radius)
        painter.restore()
        if self.editable and self.hover is not None:
            x,y = self.pixel_at(self.hover)
            radius = self.brush_size-1
            painter.setPen(QPen(Qt.yellow,1))
            painter.drawRect(QRectF(self.origin.x()+(x-radius)*self.scale_factor,
                                   self.origin.y()+(y-radius)*self.scale_factor,
                                   (2*radius+1)*self.scale_factor,(2*radius+1)*self.scale_factor))
