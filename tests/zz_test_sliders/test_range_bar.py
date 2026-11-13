"""The bar between the handles of range sliders: always visible, and its color."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from qtpy.QtCore import Qt
from qtpy.QtGui import QBrush, QColor, QGradient, QImage
from qtpy.QtWidgets import QSlider, QStyleFactory

from superqt import QLabeledDoubleRangeSlider, QLabeledRangeSlider, QRangeSlider
from superqt.sliders._generic_range_slider import _PAGES_WITH_EACH_HANDLE

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot

H, V = Qt.Orientation.Horizontal, Qt.Orientation.Vertical
TICKS = [QSlider.TickPosition.NoTicks, QSlider.TickPosition.TicksBelow]


def _bar_visible(slider: QRangeSlider) -> bool:
    """Whether the middle of the bar looks different from both ends of the slider."""
    image: QImage = slider.grab().toImage()
    horizontal = slider.orientation() == H
    ratio = image.width() / slider.width()
    centers = [slider._handleRect(i).center() for i in (0, -1)]
    mid = sum((c.x() if horizontal else c.y()) for c in centers) / 2 * ratio
    size = image.width() if horizontal else image.height()

    def line(at: float) -> list[int]:
        at = round(at)
        if horizontal:
            return [image.pixel(at, y) for y in range(image.height())]
        return [image.pixel(x, at) for x in range(image.width())]

    # (away from the ends: some styles fill a bit of the groove at the minimum)
    return all(line(mid) != line(end) for end in (size * 0.1, size * 0.9))


@pytest.mark.parametrize("style", QStyleFactory.keys())
@pytest.mark.parametrize("orientation", [H, V])
@pytest.mark.parametrize("ticks", TICKS)
def test_bar_is_visible(
    qtbot: QtBot, style: str, orientation: Qt.Orientation, ticks: QSlider.TickPosition
) -> None:
    slider = QRangeSlider(orientation)
    qtbot.addWidget(slider)
    qstyle = QStyleFactory.create(style)  # (the widget doesn't own it)
    slider.setStyle(qstyle)
    slider.setTickPosition(ticks)
    slider.resize(200, 30) if orientation == H else slider.resize(30, 200)
    slider.setValue((30, 70))
    assert _bar_visible(slider)

    slider.setInvertedAppearance(True)
    assert _bar_visible(slider)

    slider.barColor = "red"
    assert _bar_visible(slider)


def test_bar_with_style_sheet(qtbot: QtBot) -> None:
    slider = QRangeSlider(H)
    qtbot.addWidget(slider)
    slider.setStyleSheet(
        "QSlider::groove:horizontal { height: 6px; background: gray; }"
    )
    slider.resize(200, 30)
    slider.setValue((30, 70))
    assert _bar_visible(slider)


@pytest.mark.skipif(_PAGES_WITH_EACH_HANDLE, reason="sub-pages are hidden (Qt<6.10.1)")
def test_bar_from_style_sheet_sub_page(qtbot: QtBot) -> None:
    slider = QRangeSlider(H)
    qtbot.addWidget(slider)
    slider.setStyleSheet(
        "QSlider::groove:horizontal { height: 6px; background: gray; }"
        "QSlider::sub-page:horizontal { background: #00ff00; }"
    )
    slider.resize(200, 30)
    slider.setValue((30, 70))
    image = slider.grab().toImage()
    ratio = image.width() / slider.width()
    middle = slider.rect().center()
    color = image.pixelColor(round(middle.x() * ratio), round(middle.y() * ratio))
    assert color == QColor("#00ff00")


@pytest.mark.parametrize("cls", [QRangeSlider, QLabeledRangeSlider])
def test_bar_color(qtbot: QtBot, cls: type) -> None:
    slider = cls(H)
    qtbot.addWidget(slider)
    assert isinstance(slider.barColor, QBrush)  # (the default: the style's)

    slider.barColor = "red"
    assert slider.barColor.color() == QColor("red")
    slider.barColor = QColor("blue")
    assert slider.barColor.color() == QColor("blue")
    slider.barColor = QBrush(QColor("green"))
    assert slider.barColor.color() == QColor("green")
    slider.barColor = "rgba(10, 20, 30, 40)"
    assert slider.barColor.color() == QColor(10, 20, 30, 40)
    slider.barColor = "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 red, stop:1 blue)"
    gradient = slider.barColor.gradient()
    assert gradient is not None and gradient.type() == QGradient.Type.LinearGradient
    slider.barColor = None
    assert isinstance(slider.barColor, QBrush)


def test_bar_color_from_style_sheet(qtbot: QtBot) -> None:
    slider = QRangeSlider(H)
    qtbot.addWidget(slider)
    slider.setStyleSheet("QRangeSlider { qproperty-barColor: #ff8800; }")
    slider.ensurePolished()
    assert slider.barColor.color() == QColor("#ff8800")


def test_bar_colors_by_state(qtbot: QtBot) -> None:
    # (the slider's `_style` attributes, which some projects set directly)
    slider = QLabeledDoubleRangeSlider(H)
    qtbot.addWidget(slider)
    slider._slider._style.brush_active = "red"
    assert slider.barColor.color() == QColor("red")
