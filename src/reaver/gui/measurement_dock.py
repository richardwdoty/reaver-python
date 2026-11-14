"""Dockable results panel retaining its last floating geometry."""
from PySide6.QtCore import QByteArray, Signal
from PySide6.QtWidgets import QDockWidget


class MeasurementDock(QDockWidget):
    closing = Signal()

    def __init__(self, parent):
        super().__init__('Vessel Measurements', parent)
        self.floating_geometry = QByteArray()

    def remember_geometry(self):
        if self.isFloating() and self.isVisible():
            self.floating_geometry = self.saveGeometry()

    def moveEvent(self, event):
        super().moveEvent(event)
        self.remember_geometry()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.remember_geometry()

    def closeEvent(self, event):
        self.remember_geometry()
        self.closing.emit()
        super().closeEvent(event)
