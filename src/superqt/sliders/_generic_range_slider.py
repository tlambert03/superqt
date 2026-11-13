import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, TypeVar

from qtpy import QtGui
from qtpy.QtCore import (
    Property,
    QPoint,
    QPointF,
    QRect,
    QRectF,
    QSizeF,
    Qt,
    Signal,
)
from qtpy.QtGui import (
    QBrush,
    QColor,
    QGradient,
    QImage,
    QLinearGradient,
    QPainter,
    QPalette,
    QRadialGradient,
)
from qtpy.QtWidgets import (
    QApplication,
    QSlider,
    QStyle,
    QStyleOptionSlider,
    QStylePainter,
)

from ._generic_slider import (
    CC_SLIDER,
    MONTEREY_SLIDER_STYLES_FIX,
    SC_GROOVE,
    SC_HANDLE,
    SC_NONE,
    SC_TICKMARKS,
    _GenericSlider,
)

_T = TypeVar("_T")


SC_BAR = QStyle.SubControl.SC_ScrollBarSubPage


class _GenericRangeSlider(_GenericSlider):
    """MultiHandle Range Slider widget.

    Same API as QSlider, but `value`, `setValue`, `sliderPosition`, and
    `setSliderPosition` are all sequences of integers.

    The `valueChanged` and `sliderMoved` signals also both emit a tuple of
    integers.
    """

    # Emitted when the slider value has changed, with the new slider values
    valuesChanged = Signal(tuple)
    # this is just a hack to allow napari v0.4.19 tests to pass)
    # since it used the presence of this private signal as a duck-typing check.
    _valuesChanged = valuesChanged

    # Emitted when sliderDown is true and the slider moves
    # This usually happens when the user is dragging the slider
    # The value is the positions of *all* handles.
    slidersMoved = Signal(tuple)

    def __init__(self, *args, **kwargs):
        self._style = _BarColors()
        self._macpatch = False  # (whether `applyMacStylePatch` was called)

        super().__init__(*args, **kwargs)

        # list of values
        self._value: list[_T] = [20, 80]

        # list of current positions of each handle. same length as _value
        # If tracking is enabled (the default) this will be identical to _value
        self._position: list[_T] = [20, 80]

        # which handle is being pressed/hovered
        self._pressedIndex = 0
        self._hoverIndex = 0

        # whether bar length is constant when dragging the bar
        # if False, the bar can shorten when dragged beyond min/max
        self._bar_is_rigid = True
        # whether clicking on the bar moves all handles, or just the nearest handle
        self._bar_moves_all = True
        self._should_draw_bar = True

        # color

        self.setStyleSheet("")

    def _rename_signals(self) -> None:
        self.valueChanged = self.valuesChanged
        self.sliderMoved = self.slidersMoved

    # ###############  New Public API  #######################

    def barIsRigid(self) -> bool:
        """Whether bar length is constant when dragging the bar.

        If `False`, the bar can shorten when dragged beyond min/max. Default is `True`.
        """
        return self._bar_is_rigid

    def setBarIsRigid(self, val: bool = True) -> None:
        """Whether bar length is constant when dragging the bar.

        If `False`, the bar can shorten when dragged beyond min/max. Default is `True`.
        """
        self._bar_is_rigid = bool(val)

    def barMovesAllHandles(self) -> bool:
        """Whether clicking on the bar moves all handles, or just the nearest."""
        return self._bar_moves_all

    def setBarMovesAllHandles(self, val: bool = True) -> None:
        """Whether clicking on the bar moves all handles, or just the nearest."""
        self._bar_moves_all = bool(val)

    def barIsVisible(self) -> bool:
        """Whether to show the bar between the first and last handle."""
        return self._should_draw_bar

    def setBarVisible(self, val: bool = True) -> None:
        """Whether to show the bar between the first and last handle."""
        self._should_draw_bar = bool(val)

    def hideBar(self) -> None:
        """Hide the bar between the first and last handle."""
        self.setBarVisible(False)

    def showBar(self) -> None:
        """Show the bar between the first and last handle."""
        self.setBarVisible(True)

    def applyMacStylePatch(self) -> None:
        """Apply a QSS patch to fix sliders on macos>=12 with QT < 6.

        see [FAQ](../faq.md#sliders-not-dragging-properly-on-macos-12) for more details.
        """
        super().applyMacStylePatch()
        self._macpatch = True

    # ###############  QtOverrides  #######################

    def value(self) -> tuple[_T, ...]:
        """Get current value of the widget as a tuple of integers."""
        return tuple(self._value)

    def sliderPosition(self):
        """Get current value of the widget as a tuple of integers.

        If tracking is enabled (the default) this will be identical to value().
        """
        return tuple(float(i) for i in self._position)

    def setSliderPosition(  # type: ignore
        self,
        pos: float | Sequence[float],
        index: int | None = None,
        *,
        reversed: bool = False,
    ) -> None:
        """Set current position of the handles with a sequence of integers.

        Parameters
        ----------
        pos : Union[float, Sequence[float]]
            The new position of the slider handle(s). If a sequence, it must have the
            same length as `value()`. If it is a scalar, index will be used to set the
            position of the handle at that index.
        index : int | None
            The index of the handle to set the position of. If None, the "pressedIndex"
            will be used.
        reversed : bool
            Order in which to set the positions.  Can be useful when setting multiple
            positions, to avoid intermediate overlapping values.
        """
        if isinstance(pos, (list, tuple)):
            val_len = len(self.value())
            if len(pos) != val_len:
                msg = f"'sliderPosition' must have same length as 'value()' ({val_len})"
                raise ValueError(msg)
            pairs = list(enumerate(pos))
        else:
            pairs = [(self._pressedIndex if index is None else index, pos)]

        if reversed:
            pairs = pairs[::-1]

        for idx, position in pairs:
            self._position[idx] = self._bound(position, idx)

        self._doSliderMove()

    def setStyleSheet(self, styleSheet: str) -> None:
        return super().setStyleSheet(self._patch_style(styleSheet))

    def _patch_style(self, style: str):
        """Override to patch style options before painting."""
        if self._macpatch and not style:
            style = MONTEREY_SLIDER_STYLES_FIX
        return style

    def mouseMoveEvent(self, ev: QtGui.QMouseEvent) -> None:
        if self._pressedControl == SC_BAR:
            ev.accept()
            delta = self._clickOffset - self._pixelPosToRangeValue(
                self._pick(self._event_position(ev))
            )
            self._offsetAllPositions(-delta, self._sldPosAtPress)
        else:
            super().mouseMoveEvent(ev)

    def _event_position(self, event):
        # API changes between PyQt5 (.pos()) and PyQt6 (.position())
        return event.pos() if hasattr(event, "pos") else event.position()

    def paintEvent(self, ev: QtGui.QPaintEvent) -> None:
        painter = QStylePainter(self)
        opt = self._styleOption

        groove = self._drawGroove(painter, opt)
        if self._should_draw_bar:
            self._drawBar(painter, opt, groove)
        self._drawTicks(painter, opt)  # (after the bar, which could cover them)
        self._draw_handle(painter, opt)

    # ###############  Implementation Details  #######################

    def _setPosition(self, val):
        self._position = list(val)

    def _bound(self, value, index=None):
        if isinstance(value, (list, tuple)):
            return [self._bound(v) for v in value]
        pos = super()._bound(value)
        if index is not None:
            pos = self._neighbor_bound(pos, index)
        return self._type_cast(pos)

    def _neighbor_bound(self, val, index):
        # make sure we don't go lower than any preceding index:
        min_dist = self.singleStep()
        _lst = self._position
        if index > 0:
            val = max(_lst[index - 1] + min_dist, val)
        # make sure we don't go higher than any following index:
        if index < (len(_lst) - 1):
            val = min(_lst[index + 1] - min_dist, val)
        return val

    def _getBarColor(self) -> QBrush:
        opt = self._styleOption
        return self._barBrush(opt) or self._fillBrush(opt)

    def _setBarColor(self, color: Any) -> None:
        self._style.brush_active = color
        self.update()

    barColor = Property(QtGui.QBrush, _getBarColor, _setBarColor)
    """The color of the bar between the first and last handle."""

    def _offsetAllPositions(self, offset: float, ref=None) -> None:
        if ref is None:
            ref = self._position
        if self._bar_is_rigid:
            # NOTE: This assumes monotonically increasing slider positions
            if offset > 0 and ref[-1] + offset > self.maximum():
                offset = self.maximum() - ref[-1]
            elif ref[0] + offset < self.minimum():
                offset = self.minimum() - ref[0]
        self.setSliderPosition([i + offset for i in ref], reversed=offset > 0)

    def _fixStyleOption(self, option):
        pass

    @property
    def _optSliderPositions(self):
        return [self._to_qinteger_space(p - self._minimum) for p in self._position]

    # SubControl Positions

    def _handleRect(
        self, handle_index: int, opt: QStyleOptionSlider | None = None
    ) -> QRect:
        """Return the QRect for all handles."""
        opt = opt or self._styleOption
        opt.sliderPosition = self._optSliderPositions[handle_index]
        return self.style().subControlRect(CC_SLIDER, opt, SC_HANDLE, self)

    # Painting

    def _drawGroove(self, painter: QStylePainter, opt: QStyleOptionSlider) -> QImage:
        """Draw the style's groove, without any fill; return it (as drawn by the style).

        Some styles (e.g. Windows 11) fill the groove up to the handle even at the
        minimum. Drawn with the slider flipped, that bit of fill is at the other end:
        so the half of the groove with the minimum comes from the flipped one.
        """
        groove = self._grooveImage(opt, opt.minimum)
        flipped = QStyleOptionSlider(opt)
        flipped.upsideDown = not opt.upsideDown
        other = self._grooveImage(flipped, opt.minimum)

        half = QRectF(self.rect())
        start, center = self._startOfGroove(opt), half.center()
        if opt.orientation == Qt.Orientation.Horizontal:
            if start.x() < center.x():
                half.setRight(center.x())
            else:
                half.setLeft(center.x())
        elif start.y() < center.y():
            half.setBottom(center.y())
        else:
            half.setTop(center.y())

        ratio = groove.devicePixelRatio()
        clean = groove.copy()
        mix = QPainter(clean)
        mix.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        mix.drawImage(half, other, QRectF(half.topLeft() * ratio, half.size() * ratio))
        mix.end()
        painter.drawImage(0, 0, clean)
        return groove

    def _drawBar(
        self, painter: QStylePainter, opt: QStyleOptionSlider, groove: QImage
    ) -> None:
        """Draw the bar between the outer handles, in the style's groove (`groove`).

        It's the style's own fill of the groove, if it has one (as on macOS, with
        Fusion and Windows 11, or a style sheet's sub-page or add-page), in the
        `barColor` if there's one. Otherwise, it's a bar as thick as the groove, in the
        `barColor` or the style's fill color.
        """
        horizontal = opt.orientation == Qt.Orientation.Horizontal
        ends = [self._handleRect(i, opt).center() for i in (0, -1)]
        span = QRect(self.rect())  # (the part of the slider between the outer handles)
        if horizontal:
            span.setLeft(min(p.x() for p in ends))
            span.setRight(max(p.x() for p in ends))
        else:
            span.setTop(min(p.y() for p in ends))
            span.setBottom(max(p.y() for p in ends))

        # The groove, filled all along (styles fill it from the minimum up to the
        # handle), with a handle: style sheets only draw their sub-page and add-page
        # with one. That handle, at the maximum, isn't part of the bar.
        opt.sliderPosition = opt.maximum
        handle = self.style().subControlRect(CC_SLIDER, opt, SC_HANDLE, self)
        inner = _apart(span, handle, horizontal)
        if inner.isEmpty():  # (the bar is under the handles)
            return
        filled = _crop(self._grooveImage(opt, opt.maximum, handle=True), inner)
        empty = _crop(groove, inner)
        fills = filled != empty

        brush = self._barBrush(opt)
        if fills and brush is None:
            painter.drawImage(inner.topLeft(), filled)
            return
        bounds = _bounds(filled if fills else empty)
        if bounds.isEmpty():  # (the style draws no groove)
            painter.fillRect(self._plainBar(opt, span), brush or self._fillBrush(opt))
        elif fills:  # the style's own fill, in the bar color
            recolor = QPainter(filled)
            recolor.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_SourceIn
            )
            recolor.fillRect(bounds, brush)
            recolor.end()
            painter.drawImage(inner.topLeft(), filled)
        else:  # a solid bar, as thick as the groove (even if it's hollow)
            bounds.translate(QPointF(inner.topLeft()))
            bar = QRectF(span)
            if horizontal:
                bar.setTop(bounds.top())
                bar.setBottom(bounds.bottom())
            else:
                bar.setLeft(bounds.left())
                bar.setRight(bounds.right())
            painter.fillRect(bar, brush or self._fillBrush(opt))

    def _drawTicks(self, painter: QStylePainter, opt: QStyleOptionSlider) -> None:
        if opt.tickPosition != QSlider.TickPosition.NoTicks:
            opt.subControls = SC_TICKMARKS
            painter.drawComplexControl(CC_SLIDER, opt)
            self._draw_qss_ticks(painter, opt)

    def _startOfGroove(self, opt: QStyleOptionSlider) -> QPoint:
        """The center of a handle at the minimum."""
        opt.sliderPosition = opt.minimum
        return self.style().subControlRect(CC_SLIDER, opt, SC_HANDLE, self).center()

    def _plainBar(self, opt: QStyleOptionSlider, span: QRect) -> QRectF:
        """A 4px bar across `span`, centered on the style's groove."""
        groove = self.style().subControlRect(CC_SLIDER, opt, SC_GROOVE, self)
        bar = QRectF(span)
        if opt.orientation == Qt.Orientation.Horizontal:
            bar.setTop(groove.center().y() - 2)
            bar.setHeight(4)
        else:
            bar.setLeft(groove.center().x() - 2)
            bar.setWidth(4)
        return bar

    def _grooveImage(
        self,
        opt: QStyleOptionSlider,
        position: int,
        style: QStyle | None = None,
        handle: bool = False,
    ) -> QImage:
        """The style's groove (and `handle`), filled up to `position`."""
        option = QStyleOptionSlider(opt)
        option.subControls = SC_GROOVE | SC_HANDLE if handle else SC_GROOVE
        option.sliderPosition = position
        return self._sliderImage(option, style)

    def _sliderImage(
        self, opt: QStyleOptionSlider, style: QStyle | None = None
    ) -> QImage:
        """What the style draws for `opt`, as an image of the whole slider.

        (Of the whole slider: the macOS style mirrors inverted sliders around the
        slider's rect, and ignores clipping.)
        """
        ratio = self.devicePixelRatioF()
        image = QImage(self.size() * ratio, QImage.Format.Format_ARGB32_Premultiplied)
        image.setDevicePixelRatio(ratio)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        (style or self.style()).drawComplexControl(CC_SLIDER, opt, painter, self)
        painter.end()
        return image

    def _fillBrush(self, opt: QStyleOptionSlider) -> QBrush:
        """The color that the style fills slider grooves with (else the palette's).

        It's read from a groove that the style draws without tick marks (with them,
        macOS doesn't fill it), filled up to its maximum. (Not the style sheet's style,
        which may not fill it: the app's, unless the slider has its own.)
        """
        style = self.style()
        if not self.testAttribute(Qt.WidgetAttribute.WA_SetStyle):
            style = QApplication.style()
        option = QStyleOptionSlider(opt)
        option.tickPosition = QSlider.TickPosition.NoTicks
        empty = self._grooveImage(option, option.minimum, style)
        full = self._grooveImage(option, option.maximum, style)
        ratio = full.devicePixelRatio()
        center = _bounds(full).center() * ratio
        x, y = int(center.x()), int(center.y())
        if full.valid(x, y) and full.pixel(x, y) != empty.pixel(x, y):
            return QBrush(full.pixelColor(x, y))
        if opt.palette.currentColorGroup() == QPalette.ColorGroup.Disabled:
            return opt.palette.brush(QPalette.ColorRole.WindowText)  # (grayed)
        role = getattr(QPalette.ColorRole, "Accent", QPalette.ColorRole.Highlight)
        return opt.palette.brush(role)  # (`Accent` is new in Qt 6.6)

    def _barBrush(self, opt: QStyleOptionSlider) -> QBrush | None:
        """The custom color of the bar, in the slider's current state (if any)."""
        group = opt.palette.currentColorGroup()
        colors = self._style
        if group == QPalette.ColorGroup.Disabled:
            color = colors.brush_disabled
        elif group == QPalette.ColorGroup.Inactive:
            color = colors.brush_inactive or colors.brush_active
        else:
            color = colors.brush_active
        return _to_brush(color)

    def _draw_handle(self, painter: QStylePainter, opt: QStyleOptionSlider):
        opt.subControls = SC_HANDLE
        pidx = self._pressedIndex if self._pressedControl == SC_HANDLE else -1
        hidx = self._hoverIndex if self._hoverControl == SC_HANDLE else -1
        for idx, pos in enumerate(self._optSliderPositions):
            opt.sliderPosition = pos
            # make pressed handles appear sunken
            if idx == pidx:
                opt.state |= QStyle.StateFlag.State_Sunken
            else:
                opt.state = opt.state & ~QStyle.StateFlag.State_Sunken
            opt.activeSubControls = SC_HANDLE if idx == hidx else SC_NONE
            self._drawHandle(painter, opt)

    def _drawHandle(self, painter: QStylePainter, opt: QStyleOptionSlider) -> None:
        """Draw a handle, without the style sheet's sub-page and add-page.

        Up to 6.10.0, Qt draws them with each handle (so over the bar): then only
        the handle's own rect is drawn (https://bugreports.qt.io/browse/QTBUG-141157).
        """
        image = self._sliderImage(opt)
        rect = self.style().subControlRect(CC_SLIDER, opt, SC_HANDLE, self)
        # (with room for shadows and focus rings, which aren't sub-pages)
        if rect.adjusted(-4, -4, 4, 4).contains(_bounds(image).toAlignedRect()):
            painter.drawImage(0, 0, image)
        else:
            painter.drawImage(rect.topLeft(), _crop(image, rect))

    def _updateHoverControl(self, pos):
        old_hover = self._hoverControl, self._hoverIndex
        self._hoverControl, self._hoverIndex = self._getControlAtPos(pos)
        if (self._hoverControl, self._hoverIndex) != old_hover:
            self.update()

    def _updatePressedControl(self, pos):
        opt = self._styleOption
        self._pressedControl, self._pressedIndex = self._getControlAtPos(pos, opt)

    def _setClickOffset(self, pos):
        if self._pressedControl == SC_BAR:
            self._clickOffset = self._pixelPosToRangeValue(self._pick(pos))
            self._sldPosAtPress = tuple(self._position)
        elif self._pressedControl == SC_HANDLE:
            hr = self._handleRect(self._pressedIndex)
            self._clickOffset = self._pick(pos - hr.topLeft())

    # NOTE: this is very much tied to mousepress... not a generic "get control"
    def _getControlAtPos(
        self, pos: QPoint, opt: QStyleOptionSlider | None = None
    ) -> tuple[QStyle.SubControl, int]:
        """Update self._pressedControl based on ev.pos()."""
        opt = opt or self._styleOption

        if isinstance(pos, QPointF):
            pos = pos.toPoint()

        for i in range(len(self._position)):
            if self._handleRect(i, opt).contains(pos):
                return (SC_HANDLE, i)

        click_pos = self._pixelPosToRangeValue(self._pick(pos))
        for i, p in enumerate(self._position):
            if p > click_pos:
                if i > 0:
                    # the click was in an internal segment
                    if self._bar_moves_all:
                        return (SC_BAR, i)
                    avg = (self._position[i - 1] + self._position[i]) / 2
                    return (SC_HANDLE, i - 1 if click_pos < avg else i)
                # the click was below the minimum slider
                return (SC_HANDLE, 0)
        # the click was above the maximum slider
        return (SC_HANDLE, len(self._position) - 1)

    def _execute_scroll(self, steps_to_scroll, modifiers):
        if modifiers & Qt.KeyboardModifier.AltModifier:
            self._spreadAllPositions(shrink=steps_to_scroll < 0)
        else:
            self._offsetAllPositions(steps_to_scroll)
        self.triggerAction(QSlider.SliderAction.SliderMove)

    def _has_scroll_space_left(self, offset):
        return (offset > 0 and max(self._value) < self._maximum) or (
            offset < 0 and min(self._value) < self._minimum
        )

    def _spreadAllPositions(self, shrink=False, gain=1.1, ref=None) -> None:
        if ref is None:
            ref = self._position
        # if self._bar_is_rigid:  # TODO

        if shrink:
            gain = 1 / gain
        center = abs(ref[-1] + ref[0]) / 2
        self.setSliderPosition([((i - center) * gain) + center for i in ref])


@dataclass
class _BarColors:
    """Custom colors of the bar, for each state (`None`: the style's own).

    `barColor` sets `brush_active`, which is also used for inactive windows. (It's the
    slider's `_style`, whose attributes some projects set directly.)
    """

    brush_active: Any = None
    brush_inactive: Any = None
    brush_disabled: Any = None


def _apart(rect: QRect, other: QRect, horizontal: bool) -> QRect:
    """The part of `rect` that's not on `other`, on its side (along the slider)."""
    if not rect.intersects(other):
        return QRect(rect)
    out = QRect(rect)
    if horizontal and other.center().x() >= rect.center().x():
        out.setRight(other.left() - 1)
    elif horizontal:
        out.setLeft(other.right() + 1)
    elif other.center().y() >= rect.center().y():
        out.setBottom(other.top() - 1)
    else:
        out.setTop(other.bottom() + 1)
    return out


def _crop(image: QImage, rect: QRect) -> QImage:
    """The part of `image` in `rect` (in logical pixels)."""
    ratio = image.devicePixelRatio()
    pixels = QRectF(QPointF(rect.topLeft()) * ratio, QSizeF(rect.size()) * ratio)
    part = image.copy(pixels.toAlignedRect())
    part.setDevicePixelRatio(ratio)
    return part


def _bounds(image: QImage) -> QRectF:
    """The bounds of the image's pixels that aren't transparent (in logical pixels).

    (Even faint ones: the macOS groove is a black overlay with an alpha of ~5%.)
    """
    alpha = image.convertToFormat(QImage.Format.Format_Alpha8)
    bits = alpha.constBits()
    if hasattr(bits, "setsize"):  # (PyQt)
        bits.setsize(alpha.sizeInBytes())
    data, stride, width = bytes(bits), alpha.bytesPerLine(), alpha.width()
    rows, left, right = [], width, -1
    for y in range(alpha.height()):
        row = data[y * stride : y * stride + width]
        if visible := row.lstrip(b"\0"):
            rows.append(y)
            left = min(left, width - len(visible))
            right = max(right, len(row.rstrip(b"\0")) - 1)
    if not rows:
        return QRectF()
    ratio = image.devicePixelRatio()
    pixels = QRectF(left, rows[0], right - left + 1, rows[-1] - rows[0] + 1)
    return QRectF(pixels.topLeft() / ratio, pixels.size() / ratio)


def _to_brush(color: Any) -> QBrush | None:
    """`color` as a brush: a QBrush, QColor, QGradient, or a string (see `_parse`)."""
    if color is None or isinstance(color, QBrush):
        return color
    if isinstance(color, str):
        color = _parse(color)
        return None if color is None else QBrush(color)
    return QBrush(color)  # (a QColor, QGradient, or Qt.GlobalColor)


_NUM = r"(\d*\.?\d+)"
_RGBA = re.compile(r"rgba?\((\d+),\s*(\d+),\s*(\d+),?\s*(\d+)?\)")
_LINEAR = re.compile(
    rf"qlineargradient\(x1:\s*{_NUM},\s*y1:\s*{_NUM},\s*x2:\s*{_NUM},\s*"
    rf"y2:\s*{_NUM},\s*stop:0\s*(\S+),.*stop:1\s*(\S+)\)"
)
_RADIAL = re.compile(
    rf"qradialgradient\(cx:\s*{_NUM},\s*cy:\s*{_NUM},\s*radius:\s*{_NUM},\s*"
    rf"fx:\s*{_NUM},\s*fy:\s*{_NUM},\s*stop:0\s*(\S+),.*stop:1\s*(\S+)\)"
)


def _parse(color: str) -> QColor | QGradient | None:
    """A color name, `"#rrggbb"`, `"rgba(r, g, b, a)"`, or a QSS gradient."""
    if (qcolor := QColor(color)).isValid():
        return qcolor
    if match := _RGBA.search(color):
        return QColor(*(int(x) if x else 255 for x in match.groups()))
    gradient: QGradient
    if match := _LINEAR.search(color):
        *coords, stop0, stop1 = match.groups()
        gradient = QLinearGradient(*map(float, coords))
    elif match := _RADIAL.search(color):
        *coords, stop0, stop1 = match.groups()
        gradient = QRadialGradient(*map(float, coords))
    else:
        return None
    # (coordinates are relative to the bar, as in style sheets)
    gradient.setCoordinateMode(QGradient.CoordinateMode.ObjectBoundingMode)
    gradient.setColorAt(0, QColor(stop0))
    gradient.setColorAt(1, QColor(stop1))
    return gradient
