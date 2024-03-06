from typing import Any, Iterable, Optional

from qtpy import QT_VERSION
from qtpy.QtCore import Qt, Signal
from qtpy.QtWidgets import QComboBox, QCompleter, QWidget

try:
    is_qt_bellow_5_14 = tuple(int(x) for x in QT_VERSION.split(".")[:2]) < (5, 14)
except ValueError:
    is_qt_bellow_5_14 = False


class QSearchableComboBox(QComboBox):
    """ComboCox with completer for fast search in multiple options."""

    if is_qt_bellow_5_14:
        textActivated = Signal(str)  # pragma: no cover

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setEditable(True)
        self.completer_object = QCompleter()
        self.completer_object.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer_object.setCompletionMode(
            QCompleter.CompletionMode.PopupCompletion
        )
        self.completer_object.setFilterMode(Qt.MatchFlag.MatchContains)
        self.setCompleter(self.completer_object)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        if is_qt_bellow_5_14:  # pragma: no cover
            self.currentIndexChanged.connect(self._text_activated)

    def _text_activated(self):  # pragma: no cover
        self.textActivated.emit(self.currentText())

    def addItem(self, *args: Any) -> None:
        super().addItem(*args)
        self.completer_object.setModel(self.model())

    def addItems(self, texts: Iterable[str | None]) -> None:
        super().addItems(texts)
        self.completer_object.setModel(self.model())

    def insertItem(self, *args: Any) -> None:
        super().insertItem(*args)
        self.completer_object.setModel(self.model())

    def insertItems(self, index: int, texts: Iterable[str | None]) -> None:
        super().insertItems(index, texts)
        self.completer_object.setModel(self.model())
