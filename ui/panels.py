from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout
from PySide6.QtGui import QColor
from PySide6.QtCore import Qt
import json

theme = json.load(open("ui/theme.json"))

class InfoPanel(QWidget):
    def __init__(self, title):
        super().__init__()
        self.setStyleSheet(
            f"background:{theme['panel_bg']}; color:{theme['text']};"
            "border:1px solid #00eaff;"
        )

        layout = QVBoxLayout()
        label = QLabel(title)
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)
        self.setLayout(layout)
