from qtpy.QtCore import QSize
from qtpy.QtWidgets import QApplication, QPushButton

from superqt import QIconifyIcon

app = QApplication([])

btn = QPushButton()
# search https://icon-sets.iconify.design for available icon keys
# btn.setIcon(QIconifyIcon("fluent-emoji-flat:alarm-clock"))
i = QIconifyIcon("bi:bell")
btn.setIcon(i)
btn.setIconSize(QSize(60, 60))
btn.show()
QIconifyIcon.installPaletteEventFilter(btn)
app.exec()
