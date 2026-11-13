"""Render range sliders in every Qt style on this machine, to compare two versions.

    python slider_gallery.py render <before|after> <out_dir> <styles|napari>
    python slider_gallery.py compose <out_dir>  # before | after, side by side

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

HERE = Path(__file__).parent
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
# (the bar: before, superqt ignored sub-pages and add-pages)
PAGES = (
    QSS
    + """
QSlider::sub-page:horizontal { background: seagreen; border-radius: 3px; }
QSlider::sub-page:horizontal:disabled { background: #9a9a9a; }
QSlider::add-page:horizontal { background: #d8d8d8; border-radius: 3px; }
"""
)
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
        ("QSS sub-page", rs(H, setStyleSheet=PAGES)),
        ("QSS sub-page, disabled", rs(H, setStyleSheet=PAGES, setEnabled=False)),
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


def _page(name: str, label: str, out: Path, tag: str) -> dict[str, bool | None]:
    """Render the sliders in a window, save it, and return which bars are visible."""
    window = QWidget()
    window.setWindowTitle(name)
    col = QVBoxLayout(window)
    col.addWidget(QLabel(f"{name} | {label}\n{tag}"))
    form = QFormLayout()
    col.addLayout(form)
    variants = _variants()
    for row_name, slider in variants:
        slider.setFixedWidth(300)
        form.addRow(row_name, slider)
    row = QHBoxLayout()
    col.addLayout(row)
    verticals = _verticals()
    for row_name, slider in verticals:
        row.addWidget(QLabel(row_name))
        row.addWidget(slider)
    row.addStretch()
    window.show()
    window.raise_()
    window.activateWindow()
    QTest.qWaitForWindowExposed(window)
    QTest.qWaitForWindowActive(window, 2000)
    QTest.qWait(150)

    result = {n: _bar_visible(s) for n, s in variants + verticals}
    pixmap = QPixmap(window.size() * 2)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(window.palette().window().color())
    window.render(pixmap)
    pixmap.save(str(out / f"{name.replace(' ', '-')}-{label}.png"))
    missing = [n for n, ok in result.items() if ok is False]
    print(f"{name} {label}: missing bars: {missing or 'none'}")
    window.close()
    window.deleteLater()
    QTest.qWait(50)
    return result


def render(label: str, out: Path, pages: str) -> None:
    """Save the sliders, and `bars-<label>-<pages>.json`.

    `pages` is "styles": in the platform's styles (except the classic "Windows"
    style) and Fusion, in each scheme; or "napari": with napari's style sheets, on
    the default style. (Separately, as main's sliders crash with napari's.)
    """
    # (log errors in paint events, as main's raise with napari's style sheet, instead
    # of aborting: PyQt aborts unless there's an excepthook)
    sys.excepthook = lambda *exc: print("error:", exc[1], file=sys.stderr)
    app = QApplication.instance() or QApplication([])
    default = app.style().name() if hasattr(app.style(), "name") else ""
    default = default or app.style().objectName()
    out.mkdir(parents=True, exist_ok=True)
    system = f"{platform.system()} {platform.release()} {platform.machine()}"
    tag = f"{system} | {API_NAME} {QT_VERSION} | superqt {superqt.__version__}"
    bars: dict[str, dict[str, bool | None]] = {}
    # (the app deletes its previous style: so each is new, and kept here for PySide)
    styles = []
    for key in QStyleFactory.keys() if pages == "styles" else ():
        if key.lower() == "windows":
            continue
        styles.append(QStyleFactory.create(key))
        app.setStyle(styles[-1])
        for scheme in ("light", "dark"):
            if _set_scheme(app, scheme):
                bars[f"{key} {scheme}"] = _page(f"{key} {scheme}", label, out, tag)

    # napari's style sheets, which it applies to the app, on the default style
    styles.append(QStyleFactory.create(default))
    app.setStyle(styles[-1])
    for theme in ("dark", "light") if pages == "napari" else ():
        _set_scheme(app, theme)
        app.setStyleSheet((HERE / f"napari_{theme}.qss").read_text())
        bars[f"napari {theme}"] = _page(f"napari {theme}", label, out, tag)
        app.setStyleSheet("")
    (out / f"bars-{label}-{pages}.json").write_text(json.dumps(bars, indent=2))


def compose(out: Path) -> None:
    """`<page>-before.png` and `<page>-after.png`, side by side."""
    app = QApplication.instance() or QApplication([])  # noqa: F841
    dest = out / "compare"
    dest.mkdir(exist_ok=True)
    for after in sorted(out.glob("*-after.png")):
        before = after.with_name(after.name.replace("-after", "-before"))
        image = QImage(str(after))
        # (main may have crashed before saving its image)
        old = QImage(str(before)) if before.exists() else QImage()
        width = image.width() * 2 + 20
        canvas = QImage(width, image.height() + 50, QImage.Format.Format_RGB32)
        canvas.fill(QColor("white"))
        painter = QPainter(canvas)
        font = QFont()
        font.setPixelSize(28)
        painter.setFont(font)
        painter.drawText(10, 34, "before" if before.exists() else "before: crashed")
        painter.drawImage(0, 50, old)
        painter.drawText(image.width() + 30, 34, "after")
        painter.drawImage(image.width() + 20, 50, image)
        painter.end()
        canvas.save(str(dest / after.name.replace("-after", "")))
    # bars that were visible before, but not after
    try:
        old = {
            k: v
            for f in out.glob("bars-before-*.json")
            for k, v in json.loads(f.read_text()).items()
        }
        new = {
            k: v
            for f in out.glob("bars-after-*.json")
            for k, v in json.loads(f.read_text()).items()
        }
    except ValueError:
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
        render(sys.argv[2], Path(sys.argv[3]), sys.argv[4])
    else:
        compose(Path(sys.argv[2]))
