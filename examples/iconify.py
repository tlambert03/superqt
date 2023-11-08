from qtpy.QtCore import QSize
from qtpy.QtWidgets import QApplication, QPushButton

from superqt import QIconifyIcon
from superqt.iconify import PaletteIconEventFilter

app = QApplication([])

btn = QPushButton()
f = PaletteIconEventFilter()
btn.installEventFilter(f)

# search https://icon-sets.iconify.design for available icon keys
btn.setIcon(QIconifyIcon("bi:bell"))
btn.setIconSize(QSize(60, 60))
btn.show()

app.exec()
