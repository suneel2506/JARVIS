import math
from PyQt5.QtWidgets import QWidget
from PyQt5.QtGui import QPainter, QPen, QColor
from PyQt5.QtCore import Qt


class ArcReactor(QWidget):
    def __init__(self):
        super().__init__()
        self.angle = 0

    def update_angle(self, angle):
        self.angle = angle
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        cx = self.width() // 2
        cy = self.height() // 2

        # outer ring
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(self.angle)
        pen = QPen(QColor(0, 255, 255), 4)
        painter.setPen(pen)
        painter.drawEllipse(-120, -120, 240, 240)
        painter.restore()

        # inner segments
        pen = QPen(QColor(0, 180, 255), 5)
        painter.setPen(pen)
        for i in range(0, 360, 20):
            rad = math.radians(i)
            x1 = cx + 80 * math.cos(rad)
            y1 = cy + 80 * math.sin(rad)
            x2 = cx + 100 * math.cos(rad)
            y2 = cy + 100 * math.sin(rad)
            painter.drawLine(int(x1), int(y1), int(x2), int(y2))

        # core
        painter.setBrush(QColor(0, 255, 255, 180))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(cx - 30, cy - 30, 60, 60)
