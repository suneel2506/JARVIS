import sys
from PyQt5.QtWidgets import QApplication

from core.listener import listen_continuous
from core.commands import execute_command
from ui.hud import JarvisHUD


def main():
    # 1️⃣ Create Qt application FIRST
    app = QApplication(sys.argv)

    # 2️⃣ Create UI
    hud = JarvisHUD()
    hud.show()

    # 3️⃣ Start continuous listening
    listen_continuous(execute_command)

    # 4️⃣ Run Qt event loop
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
