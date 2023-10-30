from qtpy.QtCore import QEvent, QObject
from qtpy.QtWidgets import QApplication, QPushButton

app = QApplication.instance() or QApplication([])

btn = QPushButton("Click me")
btn.show()


class Filter(QObject):
    def eventFilter(self, obj, event: QEvent):
        if event.type() == QEvent.Type.Enter:
            pass
        print(obj, event, QEvent.Type(event.type()).name)
        return False


filter = Filter()
btn.installEventFilter(filter)

# app.exec_()
