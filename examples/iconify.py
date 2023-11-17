from qtpy.QtCore import QSize
from qtpy.QtGui import QIcon
from qtpy.QtWidgets import QApplication, QPushButton

from superqt import QIconifyIcon
from superqt.utils import IconPaletteEventFilter

app = QApplication([])

btn = QPushButton()
btn.setCheckable(True)
btn.show()
f = IconPaletteEventFilter()
btn.installEventFilter(f)

# search https://icon-sets.iconify.design for available icon keys
ic = QIconifyIcon("bi:alarm")
ic.addKey("bi:alarm-fill", color="yellow", state=QIcon.State.On)

btn.setIcon(ic)
btn.setIconSize(QSize(60, 60))

btn.setStyleSheet("background-color: blue; color: #333")
app.exec()
