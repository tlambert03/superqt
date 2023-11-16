from qtpy.QtCore import QSize
from qtpy.QtGui import QIcon
from qtpy.QtWidgets import QApplication, QPushButton

from superqt import QIconifyIcon
from superqt.utils import PaletteIconEventFilter

app = QApplication([])

btn = QPushButton()
btn.setCheckable(True)
f = PaletteIconEventFilter()
btn.installEventFilter(f)

# search https://icon-sets.iconify.design for available icon keys
ic = QIconifyIcon("bi:bell")
ic.addKey("bi:alarm-fill", color="red", rotate=90, state=QIcon.State.On)

btn.setIcon(ic)
btn.setIconSize(QSize(60, 60))

btn.show()
btn.setStyleSheet("background-color: blue; color: white")
app.exec()
