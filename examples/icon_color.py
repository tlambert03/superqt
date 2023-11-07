from fonticon_mdi6 import MDI6
from qtpy.QtCore import QEvent, QObject
from qtpy.QtGui import QPalette
from qtpy.QtWidgets import QApplication, QPushButton, QVBoxLayout, QWidget

from superqt import QIconifyIcon, fonticon


class PaletteEventFilter(QObject):
    def eventFilter(self, obj, event) -> bool:
        """Change icon color when palette changes."""
        print(event.type())
        if event.type() == QEvent.Type.PaletteChange:
            print("PaletteEventFilter", obj, event)
            pal = (
                obj.palette() if hasattr(obj, "palette") else QGuiApplication.palette()
            )
            new_color = pal.color(QPalette.ColorRole.ButtonText)
            if new_icon := self.getNewIcon(obj, new_color):
                obj.setIcon(new_icon)
        return False

    def getNewIcon(self, obj, color):
        """Return an instance of QIcon suitable for obj using `color`."""
        print("getNewIcon", obj, color)


app = QApplication([])

widget = QWidget()
widget.show()

btn = QPushButton()
btn.setIcon(QIconifyIcon("bi:bell"))

btn2 = QPushButton()
btn2.setIcon(fonticon.icon(MDI6.bell))


layout = QVBoxLayout(widget)
layout.addWidget(btn)
layout.addWidget(btn2)

btn.installEventFilter(PaletteEventFilter())
btn2.installEventFilter(PaletteEventFilter())
widget.setStyleSheet("QWidget{background: #333};")
app.exec()
