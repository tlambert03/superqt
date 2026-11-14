"""The bar between the handles of range sliders: always visible, and its color."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from qtpy.QtCore import QPoint, QRect, Qt
from qtpy.QtGui import QBrush, QColor, QGradient, QImage
from qtpy.QtWidgets import QProxyStyle, QSlider, QStyle, QStyleFactory

from superqt import QLabeledDoubleRangeSlider, QLabeledRangeSlider, QRangeSlider
from superqt.sliders._generic_range_slider import _PAGES_WITH_EACH_HANDLE
from superqt.sliders._generic_slider import CC_SLIDER, SC_GROOVE, SC_HANDLE

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


PAGES = """
QSlider::groove:horizontal { height: 6px; background: gray; }
QSlider::groove:vertical { width: 6px; background: gray; }
QSlider::handle:horizontal { width: 10px; background: white; }
QSlider::handle:vertical { height: 10px; background: white; }
QSlider::sub-page { background: #00ff00; }
QSlider::add-page { background: #0000ff; }
"""


@pytest.mark.parametrize("orientation", [H, V])
@pytest.mark.parametrize("inverted", [False, True])
def test_style_sheet_sub_page_is_the_bar(
    qtbot: QtBot, orientation: Qt.Orientation, inverted: bool
) -> None:
    slider = QRangeSlider(orientation)
    qtbot.addWidget(slider)
    slider.setStyleSheet(PAGES)
    slider.setInvertedAppearance(inverted)
    slider.resize(200, 30) if orientation == H else slider.resize(30, 200)
    slider.setValue((30, 70))
    assert _bar_center(slider) == QColor("#00ff00")
    assert QColor("#00ff00") not in _before_first_handle(slider)


class _FillsFromStart(QProxyStyle):
    """Fusion, with red over the groove from its start up to the handle.

    From the start of the slider (left, or top), like style sheets' sub-page once Qt
    draws it with the groove; or, if `follows`, from the minimum, like Windows 11.
    """

    def __init__(self, follows: bool) -> None:
        super().__init__("Fusion")
        self.follows = follows

    def drawComplexControl(self, control, option, painter, widget=None) -> None:
        super().drawComplexControl(control, option, painter, widget)
        if control != CC_SLIDER or not option.subControls & SC_GROOVE:
            return
        groove = self.subControlRect(control, option, SC_GROOVE, widget)
        center = self.subControlRect(control, option, SC_HANDLE, widget).center()
        fill = QRect(groove)
        backwards = self.follows and option.upsideDown
        if option.orientation == H:
            fill.setLeft(center.x()) if backwards else fill.setRight(center.x())
        else:
            fill.setTop(center.y()) if backwards else fill.setBottom(center.y())
        painter.fillRect(fill, QColor("#ff0000"))


@pytest.mark.parametrize("follows", [True, False])
@pytest.mark.parametrize("orientation", [H, V])
@pytest.mark.parametrize("inverted", [False, True])
def test_no_fill_before_the_first_handle(
    qtbot: QtBot, follows: bool, orientation: Qt.Orientation, inverted: bool
) -> None:
    slider = QRangeSlider(orientation)
    qtbot.addWidget(slider)
    style = _FillsFromStart(follows)  # (the widget doesn't own it)
    slider.setStyle(style)
    slider.setInvertedAppearance(inverted)
    slider.resize(200, 30) if orientation == H else slider.resize(30, 200)
    slider.setValue((30, 70))
    assert _bar_center(slider) == QColor("#ff0000")
    assert QColor("#ff0000") not in _before_first_handle(slider)


@pytest.mark.skipif(
    not _PAGES_WITH_EACH_HANDLE, reason="Qt draws style sheets' pages with the groove"
)
def test_round_handle_without_the_bar_before_it(qtbot: QtBot) -> None:
    # (with Qt <= 6.10.0, which draws style sheets' sub-page with each handle)
    slider = QRangeSlider(H)
    qtbot.addWidget(slider)
    slider.setStyleSheet(
        "QSlider::groove:horizontal { height: 20px; background: gray;"
        " border-radius: 10px; }"
        "QSlider::handle:horizontal { width: 20px; background: white;"
        " border-radius: 10px; }"
        "QSlider::sub-page:horizontal { background: #ff0000; }"
    )
    slider.resize(200, 30)
    slider.setValue((30, 70))
    image = slider.grab().toImage()
    ratio = image.width() / slider.width()
    corner = slider._handleRect(0).topLeft() + QPoint(1, 1)  # (outside the circle)
    color = image.pixelColor(round(corner.x() * ratio), round(corner.y() * ratio))
    assert color != QColor("#ff0000")


def _before_first_handle(slider: QRangeSlider) -> list[QColor]:
    """The colors on the groove's center line, from the start to the first handle."""
    image = slider.grab().toImage()
    ratio = image.width() / slider.width()
    groove = slider.style().subControlRect(
        CC_SLIDER, slider._styleOption, SC_GROOVE, slider
    )
    handles = [slider._handleRect(i) for i in range(len(slider.value()))]
    if slider.orientation() == H:
        end = min(r.left() for r in handles)
        points = [(x, groove.center().y()) for x in range(end)]
    else:
        end = min(r.top() for r in handles)
        points = [(groove.center().x(), y) for y in range(end)]
    return [image.pixelColor(round(x * ratio), round(y * ratio)) for x, y in points]


def _bar_center(slider: QRangeSlider) -> QColor:
    """The color in the middle of the bar, on the groove's center line."""
    image = slider.grab().toImage()
    ratio = image.width() / slider.width()
    centers = [slider._handleRect(i).center() for i in (0, -1)]
    groove = slider.style().subControlRect(
        QStyle.ComplexControl.CC_Slider,
        slider._styleOption,
        QStyle.SubControl.SC_SliderGroove,
        slider,
    )
    x, y = (centers[0].x() + centers[1].x()) / 2, groove.center().y()
    if slider.orientation() == V:
        x, y = groove.center().x(), (centers[0].y() + centers[1].y()) / 2
    return image.pixelColor(round(x * ratio), round(y * ratio))


@pytest.mark.parametrize("style", QStyleFactory.keys())
@pytest.mark.parametrize("orientation", [H, V])
@pytest.mark.parametrize("ticks", TICKS)
def test_bar_color_is_drawn_as_is(
    qtbot: QtBot, style: str, orientation: Qt.Orientation, ticks: QSlider.TickPosition
) -> None:
    slider = QRangeSlider(orientation)
    qtbot.addWidget(slider)
    qstyle = QStyleFactory.create(style)  # (the widget doesn't own it)
    slider.setStyle(qstyle)
    slider.setTickPosition(ticks)
    slider.resize(200, 30) if orientation == H else slider.resize(30, 200)
    slider.setValue((30, 70))
    slider.barColor = "#ff0000"
    assert _bar_center(slider) == QColor("#ff0000")
    slider.barColor = "rgba(0, 0, 255, 255)"
    assert _bar_center(slider) == QColor("#0000ff")


def test_translucent_bar_color(qtbot: QtBot) -> None:
    # (like ndv's: a translucent groove and sub-page, and a translucent bar color)
    slider = QRangeSlider(H)
    qtbot.addWidget(slider)
    slider.setStyleSheet(
        "QSlider::groove:horizontal { height: 10px; background: rgba(0, 0, 0, 25); }"
        "QSlider::sub-page:horizontal { background: rgba(0, 0, 0, 25); }"
        "QRangeSlider { qproperty-barColor: rgba(255, 0, 0, 128); }"
    )
    slider.resize(200, 30)
    slider.setValue((30, 70))
    color = _bar_center(slider)
    assert color.red() - color.green() > 100, color.name()  # (half red, at least)


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
