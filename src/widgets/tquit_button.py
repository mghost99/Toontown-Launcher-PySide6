from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QPushButton


class TQuit(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(19, 19)
        self.move(710, 1)
        self.default_icon = QIcon("assets/buttons/TQUIT1U.png")
        self.hover_icon = QIcon("assets/buttons/TQUIT1D.png")
        self.pressed_icon = QIcon("assets/buttons/TQUIT1D.png")
        self.setIcon(self.default_icon)
        self.setIconSize(QSize(122, 38))
        self.clicked.connect(self.quit_app)
        self.setMouseTracking(True)

    def enterEvent(self, event):
        self.setIcon(self.hover_icon)

    def leaveEvent(self, event):
        self.setIcon(self.default_icon)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.setIcon(self.pressed_icon)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self.setIcon(self.hover_icon)
        super().mouseReleaseEvent(event)

    def setEnabled(self, enabled):
        super().setEnabled(enabled)
        if not enabled:
            self.setIcon(self.disabled_icon)
        else:
            self.hide()

    def quit_app(self):
        self.parent().close()
