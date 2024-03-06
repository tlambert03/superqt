from __future__ import annotations

from typing import TYPE_CHECKING, cast

from qtpy.QtCore import Qt
from qtpy.QtGui import QFont, QFontMetrics, QTextLayout

if TYPE_CHECKING:
    from qtpy.QtWidgets import QLabel


class _GenericEliding:
    """A mixin to provide capabilities to elide text (could add '…') to fit width."""

    _elide_mode: Qt.TextElideMode = Qt.TextElideMode.ElideRight
    _text: str = ""
    # the 2 is a magic number that prevents the ellipses from going missing
    # in certain cases (?)
    _ellipses_width: int = 2

    # Public methods

    def elideMode(self) -> Qt.TextElideMode:
        """The current Qt.TextElideMode."""
        return self._elide_mode

    def setElideMode(self, mode: Qt.TextElideMode) -> None:
        """Set the elide mode to a Qt.TextElideMode."""
        self._elide_mode = Qt.TextElideMode(mode)

    def full_text(self) -> str:
        """The current text without eliding."""
        return self._text

    def setEllipsesWidth(self, width: int) -> None:
        """A width value to take into account ellipses width when eliding text.

        The value is deducted from the widget width when computing the elided version
        of the text.
        """
        self._ellipses_width = width

    @staticmethod
    def wrapText(text: str, width: float, font: QFont | None = None) -> list[str]:
        """Returns `text`, split as it would be wrapped for `width`, given `font`.

        Static method.
        """
        tl = QTextLayout(text, font or QFont())
        tl.beginLayout()
        lines = []
        while True:
            ln = tl.createLine()
            if not ln.isValid():
                break
            ln.setLineWidth(width)
            start = ln.textStart()
            lines.append(text[start : start + ln.textLength()])
        tl.endLayout()
        return lines

    # private implementation methods

    def _elidedText(self) -> str:
        """Return `self._text` elided to `width`."""
        lbl = cast("QLabel", self)  # type: ignore
        fm = QFontMetrics(lbl.font())
        ellipses_width = 0
        if self._elide_mode != Qt.TextElideMode.ElideNone:
            ellipses_width = self._ellipses_width
        width = lbl.width() - ellipses_width
        if not getattr(self, "wordWrap", None) or not lbl.wordWrap():
            return fm.elidedText(self._text, self._elide_mode, width)

        # get number of lines we can fit without eliding
        nlines = lbl.height() // fm.height() - 1
        # get the last line (elided)
        text = self._wrappedText()
        last_line = fm.elidedText("".join(text[nlines:]), self._elide_mode, width)
        # join them
        return "".join(text[:nlines] + [last_line])

    def _wrappedText(self) -> list[str]:
        lbl = cast("QLabel", self)  # type: ignore
        return _GenericEliding.wrapText(self._text, lbl.width(), lbl.font())
