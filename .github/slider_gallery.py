"""Render range sliders in every Qt style on this machine, to compare two versions.

    python slider_gallery.py render <label> <out_dir>    # e.g. "before", then "after"
    python slider_gallery.py compose <out_dir>           # before | after, side by side

`render` saves one image per style and color scheme, and `bars.json`: whether each
slider's bar is visible (the middle of the bar looks different from both ends of the
slider).
"""

from __future__ import annotations

import json
import platform
import sys
from pathlib import Path

from qtpy import API_NAME, QT_VERSION
from qtpy.QtCore import Qt
from qtpy.QtGui import QColor, QFont, QImage, QPainter, QPixmap
from qtpy.QtTest import QTest
from qtpy.QtWidgets import (
    QApplication,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QSlider,
    QStyleFactory,
    QVBoxLayout,
    QWidget,
)

import superqt
from superqt import (
    QDoubleRangeSlider,
    QLabeledDoubleRangeSlider,
    QLabeledRangeSlider,
    QRangeSlider,
)

H, V = Qt.Orientation.Horizontal, Qt.Orientation.Vertical
QSS = """
QSlider::groove:horizontal {
    height: 6px; background: #b0b0b0; border-radius: 3px; margin: 0 4px;
}
QSlider::handle:horizontal {
    width: 14px; margin: -5px 0; background: #f0f0f0; border: 1px solid #777;
    border-radius: 7px;
}
"""
NDV_GRADIENT = (
    "QRangeSlider { qproperty-barColor: qlineargradient(x1:0, y1:0, x2:0, y2:1, "
    "stop:0 #6e5a87, stop:1 #c9a0ff); }"
)


def _variants() -> list[tuple[str, QWidget]]:
    def rs(*args, values=(20, 70), cls=QRangeSlider, **setters):
        slider = cls(*args)
        for name, value in setters.items():
            method = getattr(slider, name)
            method(*value) if isinstance(value, tuple) else method(value)
        slider.setValue(values)
        return slider

    custom = rs(H)
    custom.barColor = "red"
    gradient = rs(H)
    gradient.barColor = (
        "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 red, stop:1 blue)"
    )
    disabled = rs(H, setEnabled=False)
    qss_color = rs(
        H, setStyleSheet=QSS + "QRangeSlider { qproperty-barColor: orange; }"
    )
    patched = rs(H)
    patched.applyMacStylePatch()
    return [
        ("plain", rs(H)),
        ("inverted", rs(H, setInvertedAppearance=True)),
        ("ticks above", rs(H, setTickPosition=QSlider.TickPosition.TicksAbove)),
        ("ticks below", rs(H, setTickPosition=QSlider.TickPosition.TicksBelow)),
        ("ticks both", rs(H, setTickPosition=QSlider.TickPosition.TicksBothSides)),
        ("3 handles", rs(H, values=(10, 40, 80))),
        ("full range", rs(H, values=(0, 99))),
        ("float", rs(H, values=(0.2, 0.7), cls=QDoubleRangeSlider, setRange=(0, 1))),
        ("disabled", disabled),
        ("barColor red", custom),
        ("barColor gradient", gradient),
        ("QSS groove", rs(H, setStyleSheet=QSS)),
        ("QSS + barColor", qss_color),
        ("ndv gradient", rs(H, setStyleSheet=NDV_GRADIENT)),
        ("mac style patch", patched),
        ("labeled", rs(H, cls=QLabeledRangeSlider)),
        ("labeled float", rs(H, values=(0.2, 0.7), cls=QLabeledDoubleRangeSlider)),
    ]


def _verticals() -> list[tuple[str, QWidget]]:
    out = []
    for name, inverted in (("vertical", False), ("v. inverted", True)):
        slider = QRangeSlider(V)
        slider.setValue((20, 70))
        slider.setInvertedAppearance(inverted)
        slider.setFixedHeight(150)
        out.append((name, slider))
    return out


def _bar_visible(slider: QWidget) -> bool | None:
    """Whether the middle of the bar looks different from both ends of the slider."""
    inner = getattr(slider, "_slider", slider)
    if not isinstance(inner, QSlider):
        return None
    image = inner.grab().toImage()
    horizontal = inner.orientation() == H
    size = image.width() if horizontal else image.height()
    handles = [inner._handleRect(i) for i in (0, -1)]
    centers = [r.center().x() if horizontal else r.center().y() for r in handles]
    ratio = image.width() / max(1, inner.width())
    mid = round(sum(centers) / 2 * ratio)

    def line(at: int) -> list[int]:
        n = image.height() if horizontal else image.width()
        pick = (
            (lambda i: image.pixel(at, i))
            if horizontal
            else (lambda i: image.pixel(i, at))
        )
        return [pick(i) for i in range(n)]

    # (away from the ends: some styles fill a bit of the groove at the minimum)
    ends = [round(size * 0.1), round(size * 0.9)]
    lo, hi = sorted(centers)
    ends = [e for e in ends if not (lo * ratio - 2 <= e <= hi * ratio + 2)]
    return all(line(mid) != line(e) for e in ends) if ends else None


def _set_scheme(app: QApplication, scheme: str) -> bool:
    """Whether to render `scheme`: light always, dark if the platform switches."""
    hints = app.styleHints()
    if hasattr(hints, "setColorScheme"):  # (Qt >= 6.8)
        target = Qt.ColorScheme.Dark if scheme == "dark" else Qt.ColorScheme.Light
        hints.setColorScheme(target)
        QTest.qWait(50)
        if hints.colorScheme() == target:
            return True
    return scheme == "light"


def render(label: str, out: Path) -> None:
    """Save the sliders in each style and scheme, and `bars-<label>.json`."""
    app = QApplication.instance() or QApplication([])
    default = (
        app.style().name() if hasattr(app.style(), "name") else app.style().objectName()
    )
    out.mkdir(parents=True, exist_ok=True)
    system = f"{platform.system()} {platform.release()} {platform.machine()}"
    tag = f"{system} | {API_NAME} {QT_VERSION} | superqt {superqt.__version__}"
    bars: dict[str, dict[str, bool | None]] = {}
    for key in QStyleFactory.keys():
        style = QStyleFactory.create(key)  # (kept: PySide may not transfer ownership)
        app.setStyle(style)
        for scheme in ("light", "dark"):
            if not _set_scheme(app, scheme):
                continue
            window = QWidget()
            window.setWindowTitle(f"{key} {scheme}")
            col = QVBoxLayout(window)
            kind = "default style" if key.lower() == default.lower() else "style"
            title = QLabel(f"{key} ({kind}), {scheme} | {label}\n{tag}")
            col.addWidget(title)
            form = QFormLayout()
            col.addLayout(form)
            variants = _variants()
            for name, slider in variants:
                slider.setFixedWidth(300)
                form.addRow(name, slider)
            row = QHBoxLayout()
            col.addLayout(row)
            verticals = _verticals()
            for name, slider in verticals:
                row.addWidget(QLabel(name))
                row.addWidget(slider)
            row.addStretch()
            window.show()
            window.raise_()
            window.activateWindow()
            QTest.qWaitForWindowExposed(window)
            QTest.qWaitForWindowActive(window, 2000)
            QTest.qWait(150)

            result = {n: _bar_visible(s) for n, s in variants + verticals}
            bars[f"{key} {scheme}"] = result
            pixmap = QPixmap(window.size() * 2)
            pixmap.setDevicePixelRatio(2)
            pixmap.fill(window.palette().window().color())
            window.render(pixmap)
            pixmap.save(str(out / f"{key}-{scheme}-{label}.png"))
            missing = [n for n, ok in result.items() if ok is False]
            print(f"{key} {scheme} {label}: missing bars: {missing or 'none'}")
            window.close()
            window.deleteLater()
            QTest.qWait(50)
    (out / f"bars-{label}.json").write_text(json.dumps(bars, indent=2))


def compose(out: Path) -> None:
    """`<style>-<scheme>-before.png` and `-after.png`, side by side."""
    app = QApplication.instance() or QApplication([])  # noqa: F841
    dest = out / "compare"
    dest.mkdir(exist_ok=True)
    for before in sorted(out.glob("*-before.png")):
        after = before.with_name(before.name.replace("-before", "-after"))
        images = [QImage(str(p)) for p in (before, after) if p.exists()]
        width = sum(i.width() for i in images) + 20 * (len(images) - 1)
        canvas = QImage(
            width, max(i.height() for i in images) + 50, QImage.Format.Format_RGB32
        )
        canvas.fill(QColor("white"))
        painter = QPainter(canvas)
        font = QFont()
        font.setPixelSize(28)
        painter.setFont(font)
        x = 0
        for name, image in zip(("before", "after"), images, strict=False):
            painter.drawText(x + 10, 34, name)
            painter.drawImage(x, 50, image)
            x += image.width() + 20
        painter.end()
        canvas.save(str(dest / before.name.replace("-before", "")))
    # bars that were visible before, but not after
    try:
        old = json.loads((out / "bars-before.json").read_text())
        new = json.loads((out / "bars-after.json").read_text())
    except FileNotFoundError:
        return
    lost = [
        f"{page}: {name}"
        for page, results in new.items()
        for name, ok in results.items()
        if ok is False and old.get(page, {}).get(name) is True
    ]
    (dest / "lost_bars.txt").write_text("\n".join(lost) + "\n")
    print("bars visible before but not after:", lost or "none")


if __name__ == "__main__":
    if sys.argv[1] == "render":
        render(sys.argv[2], Path(sys.argv[3]))
    else:
        compose(Path(sys.argv[2]))
