from PySide6.QtWidgets import QWidget, QApplication, QHBoxLayout
from PySide6.QtCore import Qt
import sys
from ui.arc_reactor import ArcReactor
from ui.panels import InfoPanel
import json

theme = json.load(open("ui/theme.json"))

class JarvisHUD(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("JARVIS")
        self.setStyleSheet(f"background:{theme['background']};")
        self.showFullScreen()

        layout = QHBoxLayout()

        left = InfoPanel("SYSTEM")
        center = ArcReactor()
        right = InfoPanel("COMMANDS")

        layout.addWidget(left, 1)
        layout.addWidget(center, 2)
        layout.addWidget(right, 1)

        self.setLayout(layout)
