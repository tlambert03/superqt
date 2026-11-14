"""Contact sheets of QSlider and QRangeSlider, in states and stylings that matter.

They're the states and stylings that range sliders' bars have gotten wrong: one sheet
per OS, style and color scheme, with a column per Qt version; and one for napari's
style sheet.

    python visual_matrix.py render <out_dir> [--napari]
    python visual_matrix.py compose <renders_dir> <sheets_dir>

`render` saves, in `out_dir`, `meta.json` (the Qt version, the OS, the styles, which
pages were rendered, and the rows) and an image of each slider:
`<style>/<scheme>/<page>/<row>-qslider.png` and `<row>-range.png`.
"""

from __future__ import annotations

import json
import platform
import sys
from dataclasses import dataclass, field
from pathlib import Path

from qtpy import API_NAME
from qtpy.QtCore import QPoint, QRect, QRectF, Qt, qVersion
from qtpy.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter
from qtpy.QtTest import QTest
from qtpy.QtWidgets import (
    QApplication,
    QGridLayout,
    QSlider,
    QStyle,
    QStyleFactory,
    QStyleOptionSlider,
    QWidget,
)

from superqt import QDoubleRangeSlider, QLabeledDoubleRangeSlider, QRangeSlider

HERE = Path(__file__).parent
H, V = Qt.Orientation.Horizontal, Qt.Orientation.Vertical

# a groove and round handles, with or without the pages
QSS_GROOVE = """
QSlider::groove:horizontal { height: 6px; background: #b0b0b0; border-radius: 3px; }
QSlider::groove:vertical { width: 6px; background: #b0b0b0; border-radius: 3px; }
QSlider::handle:horizontal {
    width: 14px; margin: -5px 0; background: #f0f0f0; border: 1px solid #777;
    border-radius: 7px;
}
QSlider::handle:vertical {
    height: 14px; margin: 0 -5px; background: #f0f0f0; border: 1px solid #777;
    border-radius: 7px;
}
"""
QSS_PAGES = (
    QSS_GROOVE
    + """
QSlider::sub-page { background: seagreen; border-radius: 3px; }
QSlider::sub-page:disabled { background: #9a9a9a; }
QSlider::add-page { background: #d8d8d8; border-radius: 3px; }
"""
)
# superqt's docs: round handles as tall as the groove, which has a gradient along it
QSS_DOCS = """
QSlider { min-height: 20px; }
QSlider::groove:horizontal {
    border: 0px; height: 20px; border-radius: 10px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #888, stop:1 #ddd);
}
QSlider::handle {
    background: qradialgradient(cx:0, cy:0, radius: 1.2, fx:0.35, fy:0.3,
                                stop:0 #eef, stop:1 #002);
    height: 20px; width: 20px; border-radius: 10px;
}
QSlider::sub-page:horizontal {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #227, stop:1 #77a);
    border-top-left-radius: 10px; border-bottom-left-radius: 10px;
}
QRangeSlider {
    qproperty-barColor:
        qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #227, stop:1 #77a);
}
"""
# ndv's (and pymmcore-widgets'): translucent, with a translucent bar color
QSS_NDV = """
QSlider::groove:horizontal {
    height: 15px;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(128, 128, 128, 0.25), stop:1 rgba(128, 128, 128, 0.1));
    border-radius: 3px;
}
QSlider::handle:horizontal { width: 38px; background: #999999; border-radius: 3px; }
QSlider::sub-page:horizontal {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(100, 100, 100, 0.25), stop:1 rgba(100, 100, 100, 0.1));
}
QRangeSlider { qproperty-barColor: qlineargradient(x1:0, y1:0, x2:0, y2:1,
    stop:0 rgba(100, 80, 120, 0.2), stop:1 rgba(100, 80, 120, 0.4)) }
"""
GRADIENT = "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 red, stop:1 blue)"
TICKS = QSlider.TickPosition.TicksBelow


@dataclass
class Row:
    """A slider configuration: the QRangeSlider's, and (if `reference`) a QSlider's."""

    section: str
    label: str
    values: tuple = (20, 70)
    reference: float | None = 70  # (the QSlider's value: None for no QSlider)
    orientation: Qt.Orientation = H
    sheet: str = ""
    setters: dict = field(default_factory=dict)  # (for both sliders)
    bar_color: str | None = None
    mac_patch: bool = False
    inactive: bool = False  # (in a window that isn't the active one)
    cls: type = QRangeSlider
    range: tuple = (0, 99)


NATIVE = "Native style, nothing customized"
BAR = "A custom bar color (the barColor property)"
QSS = "Style sheets (QSS) on the slider"
API = "superqt API"
ROWS = [
    Row(NATIVE, "default (handles at 20 and 70)"),
    Row(NATIVE, "window not focused (another window is active)", inactive=True),
    Row(NATIVE, "disabled (setEnabled(False))", setters={"setEnabled": False}),
    Row(NATIVE, "tick marks below the groove", setters={"setTickPosition": TICKS}),
    Row(NATIVE, "inverted appearance", setters={"setInvertedAppearance": True}),
    Row(NATIVE, "handles at both ends (0 and 99)", values=(0, 99), reference=99),
    Row(NATIVE, "low handle at the minimum (0 and 60): QSlider at 0", (0, 60), 0),
    Row(NATIVE, "three handles (10, 40 and 80)", values=(10, 40, 80), reference=None),
    Row(NATIVE, "vertical", orientation=V),
    Row(
        NATIVE,
        "vertical, inverted appearance",
        orientation=V,
        setters={"setInvertedAppearance": True},
    ),
    Row(BAR, "custom barColor set (solid red)", reference=None, bar_color="red"),
    Row(
        BAR,
        "custom barColor set (solid red), window not focused",
        reference=None,
        bar_color="red",
        inactive=True,
    ),
    Row(
        BAR,
        "custom barColor set (solid red), disabled",
        reference=None,
        bar_color="red",
        setters={"setEnabled": False},
    ),
    Row(
        BAR,
        "custom barColor set (a red-to-blue gradient)",
        reference=None,
        bar_color=GRADIENT,
    ),
    Row(QSS, "QSS styles the groove and handle only (no ::sub-page)", sheet=QSS_GROOVE),
    Row(QSS, "::sub-page and ::add-page in the QSS", sheet=QSS_PAGES),
    Row(
        QSS,
        "::sub-page and ::add-page in the QSS, disabled (with a :disabled rule)",
        sheet=QSS_PAGES,
        setters={"setEnabled": False},
    ),
    Row(
        QSS,
        "::sub-page and ::add-page in the QSS, low handle at the minimum",
        (0, 60),
        0,
        sheet=QSS_PAGES,
    ),
    Row(
        QSS,
        "::sub-page and ::add-page in the QSS, three handles",
        (10, 40, 80),
        None,
        sheet=QSS_PAGES,
    ),
    Row(
        QSS,
        "::sub-page and ::add-page in the QSS, inverted appearance",
        sheet=QSS_PAGES,
        setters={"setInvertedAppearance": True},
    ),
    Row(
        QSS,
        "::sub-page and ::add-page in the QSS, vertical",
        sheet=QSS_PAGES,
        orientation=V,
    ),
    Row(
        QSS,
        "::sub-page and ::add-page in the QSS, vertical, inverted appearance",
        sheet=QSS_PAGES,
        orientation=V,
        setters={"setInvertedAppearance": True},
    ),
    Row(
        QSS,
        "::sub-page in the QSS and a custom barColor set (as napari does)",
        sheet=QSS_PAGES + "QRangeSlider { qproperty-barColor: orange; }",
    ),
    Row(
        QSS,
        "round handles as tall as the groove, gradient along the groove, "
        "barColor in the QSS (superqt's docs example)",
        sheet=QSS_DOCS,
    ),
    Row(
        QSS,
        "translucent groove and ::sub-page, translucent barColor in the QSS "
        "(ndv's and pymmcore-widgets' style sheet)",
        sheet=QSS_NDV,
    ),
    Row(API, "applyMacStylePatch() called", reference=None, mac_patch=True),
]

NAPARI_SECTION = "napari's dark theme (its style sheet, set on the main window)"
NAPARI_ROWS = [
    Row(
        NAPARI_SECTION,
        "layer controls' contrast limits (QDoubleRangeSlider)",
        values=(200, 700),
        cls=QDoubleRangeSlider,
        range=(0, 1000),
    ),
    Row(
        NAPARI_SECTION,
        "contrast limits at the full data range (napari's default)",
        values=(0, 1000),
        reference=99,
        cls=QDoubleRangeSlider,
        range=(0, 1000),
    ),
    Row(
        NAPARI_SECTION,
        "contrast limits, low handle at the minimum",
        values=(0, 600),
        reference=0,
        cls=QDoubleRangeSlider,
        range=(0, 1000),
    ),
    Row(
        NAPARI_SECTION,
        "contrast limits, window not focused",
        values=(200, 700),
        cls=QDoubleRangeSlider,
        range=(0, 1000),
        inactive=True,
    ),
    Row(
        NAPARI_SECTION,
        "contrast limits, disabled",
        values=(200, 700),
        cls=QDoubleRangeSlider,
        range=(0, 1000),
        setters={"setEnabled": False},
    ),
    Row(
        NAPARI_SECTION,
        "contrast limits popup (QLabeledDoubleRangeSlider)",
        values=(200, 700),
        reference=None,
        cls=QLabeledDoubleRangeSlider,
        range=(0, 1000),
    ),
]


# ---------------------------------------------------------------- rendering


def _sliders(row: Row) -> tuple[QSlider | None, QWidget]:
    """The row's QSlider (if any) and range slider."""
    reference = None
    if row.reference is not None:
        reference = QSlider(row.orientation)
        reference.setRange(0, 99)
        reference.setValue(int(row.reference))
    ranged = row.cls(row.orientation)
    ranged.setRange(*row.range)
    if row.mac_patch:
        ranged.applyMacStylePatch()
    if row.bar_color is not None:
        ranged.barColor = row.bar_color
    for slider in (reference, ranged):
        if slider is None:
            continue
        if row.sheet:
            slider.setStyleSheet(row.sheet)
        for name, value in row.setters.items():
            getattr(slider, name)(value)
        if row.orientation == H:
            slider.setFixedWidth(320 if row.cls is QLabeledDoubleRangeSlider else 200)
        else:
            slider.setFixedHeight(150)
    ranged.setValue(row.values)
    return reference, ranged


def _render_page(rows: list[Row], out: Path, window_sheet: str = "") -> dict:
    """Show the rows in two windows (the active one, and one that isn't), save them."""
    windows = {False: QWidget(), True: QWidget()}  # (by `inactive`)
    grids = {}
    for inactive, window in windows.items():
        window.setWindowTitle("not focused" if inactive else "focused")
        if window_sheet:
            window.setStyleSheet(window_sheet)
        grids[inactive] = QGridLayout(window)
    placed, counts = [], {False: 0, True: 0}
    for i, row in enumerate(rows):
        reference, ranged = _sliders(row)
        n, counts[row.inactive] = counts[row.inactive], counts[row.inactive] + 1
        grid, r, c = grids[row.inactive], n // 3, (n % 3) * 2  # (in three columns)
        if reference is not None:
            grid.addWidget(reference, r, c)
        grid.addWidget(ranged, r, c + 1)
        placed.append((i, reference, ranged, windows[row.inactive]))
    windows[True].move(20, 20)
    windows[False].move(60, 300)
    windows[True].show()
    windows[False].show()
    QTest.qWaitForWindowExposed(windows[True])
    QTest.qWaitForWindowExposed(windows[False])
    for _ in range(5):  # (activation is sometimes ignored: ask again)
        windows[False].raise_()
        windows[False].activateWindow()
        windows[False].windowHandle().requestActivate()
        if QTest.qWaitForWindowActive(windows[False], 1000):
            break
    QTest.qWait(300)
    states = {
        "focused window active": windows[False].isActiveWindow(),
        "unfocused window inactive": not windows[True].isActiveWindow(),
    }
    ratio = windows[False].devicePixelRatioF()
    out.mkdir(parents=True, exist_ok=True)
    for i, reference, ranged, window in placed:
        for name, widget in (("qslider", reference), ("range", ranged)):
            if widget is not None:
                rect = QRect(widget.mapTo(window, QPoint(0, 0)), widget.size())
                window.grab(rect).save(str(out / f"{i:02d}-{name}.png"))
    for window in windows.values():
        window.close()
        window.deleteLater()
    QTest.qWait(50)
    return {"states": states, "ratio": ratio}


def _set_scheme(app: QApplication, scheme: str) -> bool:
    """Whether the app is now in `scheme` (switching it needs Qt >= 6.8)."""
    hints = app.styleHints()
    if not hasattr(hints, "setColorScheme"):
        return scheme == "light"
    target = getattr(Qt.ColorScheme, scheme.title())
    hints.setColorScheme(target)
    QTest.qWait(100)
    return hints.colorScheme() == target


def _pages_drawn_with(controls: QStyle.SubControl) -> bool:
    """Whether a style sheet's sub-page is drawn with only `controls`."""
    slider = QSlider(H)
    slider.setStyleSheet(
        "QSlider::groove:horizontal { background: #000; height: 6px; }"
        "QSlider::handle:horizontal { width: 10px; background: #00f; }"
        "QSlider::sub-page:horizontal { background: #f00; }"
    )
    slider.resize(200, 20)
    slider.setValue(80)
    slider.ensurePolished()
    opt = QStyleOptionSlider()
    slider.initStyleOption(opt)
    opt.subControls = controls
    image = QImage(slider.size(), QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.white)
    painter = QPainter(image)
    slider.style().drawComplexControl(
        QStyle.ComplexControl.CC_Slider, opt, painter, slider
    )
    painter.end()
    return image.pixelColor(20, 10) == QColor("#ff0000")


def _os() -> str:
    system = platform.system()
    if system == "Darwin":
        return f"macOS {platform.mac_ver()[0]} ({platform.machine()})"
    if system == "Windows":
        return f"Windows {platform.version()} ({platform.machine()})"
    return f"{platform.freedesktop_os_release().get('PRETTY_NAME', 'Linux')}"


def _style_name(style: QStyle) -> str:
    return (style.name() if hasattr(style, "name") else "") or style.objectName()


def render(out: Path, napari: bool) -> None:
    """Render the rows in each style and scheme (and napari's, if `napari`)."""
    # (log errors in paint events instead of aborting, as PyQt does without a hook)
    sys.excepthook = lambda *exc: print("error:", exc[1], file=sys.stderr)
    app = QApplication.instance() or QApplication([])
    default = _style_name(app.style())
    keys = [default]
    if platform.system() == "Windows":  # (the default style on Windows 10)
        keys += [k for k in QStyleFactory.keys() if k.lower() == "windowsvista"]
    keys = list(dict.fromkeys(k.lower() for k in keys))
    sc = QStyle.SubControl
    meta: dict = {
        "qt": qVersion(),
        "api": API_NAME,
        "os": _os(),
        "default style": default.lower(),
        "pages with the groove alone": _pages_drawn_with(sc.SC_SliderGroove),
        "pages with a handle alone": _pages_drawn_with(sc.SC_SliderHandle),
        "pages": {},
        "rows": {
            "matrix": [_row_meta(r) for r in ROWS],
            "napari": [_row_meta(r) for r in NAPARI_ROWS],
        },
    }
    styles = []  # (the app deletes its previous style: keep them, for PySide)
    for key in keys:
        styles.append(QStyleFactory.create(key))
        app.setStyle(styles[-1])
        for scheme in ("light", "dark"):
            if _set_scheme(app, scheme):
                page = f"{key}/{scheme}/matrix"
                meta["pages"][page] = _render_page(ROWS, out / page)
    if napari:
        styles.append(QStyleFactory.create(default))
        app.setStyle(styles[-1])
        if _set_scheme(app, "dark"):
            sheet = (HERE / "napari_dark.qss").read_text()
            page = f"{default.lower()}/dark/napari"
            meta["pages"][page] = _render_page(NAPARI_ROWS, out / page, sheet)
    (out / "meta.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps({k: v for k, v in meta.items() if k != "rows"}, indent=2))


def _row_meta(row: Row) -> dict:
    return {
        "section": row.section,
        "label": row.label,
        "vertical": row.orientation == V,
        "reference": row.reference is not None,
    }


# ---------------------------------------------------------------- composing

QT_ORDER = ["qt5", "qt6.10.0", "qt6.12.0", "next"]
QT_NOTES = {
    "qt5": "style sheets' sub-page and add-page drawn with each handle",
    "qt6.10.0": "the last Qt 6 that draws style sheets' pages with each handle "
    "(QTBUG-141157)",
    "qt6.12.0": "style sheets' pages drawn only with the groove and a handle together",
    "next": "6.12.0 built with qtbase 4d278649f7: style sheets' pages drawn with the "
    "groove (QTBUG-141608), coming in a 6.12 patch release and 6.13",
}
LABEL_W, GAP, PAD = 300, 16, 8


def compose(renders: Path, sheets: Path) -> None:
    """Compose the renders of every job (in `renders/<os>-<qt>/`) into sheets."""
    app = QApplication.instance() or QApplication([])  # noqa: F841
    sheets.mkdir(parents=True, exist_ok=True)
    jobs: dict[str, dict[str, Path]] = {}  # {os: {qt: dir}}
    for meta in renders.glob("*/meta.json"):
        os_name, qt = meta.parent.name.rsplit("-", 1)
        jobs.setdefault(os_name, {})[qt] = meta.parent
    for os_name, by_qt in sorted(jobs.items()):
        metas = {
            qt: json.loads((d / "meta.json").read_text()) for qt, d in by_qt.items()
        }
        pages = sorted({p for m in metas.values() for p in m["pages"]})
        for page in pages:
            style, scheme, kind = page.split("/")
            if kind == "napari":
                continue
            title = f"{os_name}, {style} style, {scheme}"
            _sheet(
                title,
                page,
                "matrix",
                by_qt,
                metas,
                sheets / f"{os_name}-{style}-{scheme}.png",
            )
    linux = next((by_qt for os_name, by_qt in jobs.items() if "ubuntu" in os_name), {})
    metas = {qt: json.loads((d / "meta.json").read_text()) for qt, d in linux.items()}
    napari = sorted(
        {p for m in metas.values() for p in m["pages"] if p.endswith("napari")}
    )
    if napari:
        _sheet(
            "napari, dark theme (on Linux)",
            napari[0],
            "napari",
            linux,
            metas,
            sheets / "napari-dark.png",
        )


def _sheet(
    title: str,
    page: str,
    kind: str,
    dirs: dict[str, Path],
    metas: dict[str, dict],
    path: Path,
) -> None:
    """Rows of `page` (the QSlider, then the range slider) with a column per Qt."""
    columns = [qt for qt in QT_ORDER if qt in dirs and page in metas[qt]["pages"]]
    missing = [qt for qt in QT_ORDER if qt not in columns]
    rows = metas[columns[0]]["rows"][kind]

    def load(qt: str, i: int, name: str) -> QImage | None:
        file = dirs[qt] / page / f"{i:02d}-{name}.png"
        if not file.exists():
            return None
        image = QImage(str(file))
        image.setDevicePixelRatio(metas[qt]["pages"][page]["ratio"])
        return image

    images = {
        (qt, i, name): load(qt, i, name)
        for qt in columns
        for i in range(len(rows))
        for name in ("qslider", "range")
    }
    width = {}  # (of each half of each column)
    for qt in columns:
        for name in ("qslider", "range"):
            sizes = [
                img.deviceIndependentSize().width()
                for (q, _, n), img in images.items()
                if q == qt and n == name and img is not None
            ]
            width[qt, name] = max(sizes, default=60)
    col_w = {qt: width[qt, "qslider"] + PAD + width[qt, "range"] for qt in columns}
    small = QFont()
    small.setPixelSize(11)
    label = QRect(0, 0, LABEL_W - 2 * PAD, 1000)
    wrap = Qt.TextFlag.TextWordWrap
    heights = []
    for i, row in enumerate(rows):
        hs = [
            img.deviceIndependentSize().height()
            for (_, j, _), img in images.items()
            if j == i and img is not None
        ]
        text = QFontMetrics(small).boundingRect(label, wrap, row["label"]).height()
        heights.append(max([*hs, text, 20]) + 2 * PAD)
    sections = [r["section"] for r in rows]
    n_sections = len(dict.fromkeys(sections))
    head = 130
    total_w = LABEL_W + sum(col_w[qt] + GAP for qt in columns) + GAP
    total_h = head + sum(heights) + n_sections * 28 + 20
    ratio = max(
        (img.devicePixelRatio() for img in images.values() if img is not None),
        default=1.0,
    )
    sheet = QImage(
        int(total_w * ratio), int(total_h * ratio), QImage.Format.Format_RGB32
    )
    sheet.setDevicePixelRatio(ratio)
    background = _background(images)
    sheet.fill(background)
    dark = background.lightness() < 128
    ink, faint = QColor("#eee" if dark else "#111"), QColor("#999" if dark else "#666")
    p = QPainter(sheet)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    big, bold = QFont(), QFont()
    big.setPixelSize(18)
    big.setBold(True)
    bold.setPixelSize(13)
    bold.setBold(True)
    meta0 = metas[columns[0]]
    p.setPen(ink)
    p.setFont(big)
    p.drawText(QRectF(PAD, PAD, total_w, 24), title)
    p.setFont(small)
    p.setPen(faint)
    absent = f"   (no {', '.join(missing)} here)" if missing else ""
    p.drawText(QRectF(PAD, 34, total_w, 16), meta0["os"] + absent)
    x = LABEL_W + GAP
    xs = {}
    for qt in columns:
        meta = metas[qt]
        xs[qt] = x
        p.setPen(ink)
        p.setFont(bold)
        name = "next Qt" if qt == "next" else f"Qt {meta['qt']}"
        p.drawText(QRectF(x, 56, col_w[qt], 16), f"{name} ({meta['api']})")
        p.setPen(faint)
        p.setFont(small)
        p.drawText(QRectF(x, 74, col_w[qt], 32), wrap, QT_NOTES.get(qt, ""))
        states = meta["pages"][page]["states"]
        if not all(states.values()):
            bad = ", ".join(k for k, v in states.items() if not v)
            p.setPen(QColor("#d33"))
            p.drawText(QRectF(x, 104, col_w[qt], 14), f"not as intended: {bad}")
            p.setPen(faint)
        p.drawText(QRectF(x, 116, width[qt, "qslider"], 14), "QSlider")
        p.drawText(
            QRectF(x + width[qt, "qslider"] + PAD, 116, width[qt, "range"], 14),
            "range slider (this branch)",
        )
        x += col_w[qt] + GAP
    y, section = head, None
    for i, row in enumerate(rows):
        if row["section"] != section:
            section = row["section"]
            p.setPen(ink)
            p.setFont(bold)
            p.drawText(QRectF(PAD, y + 8, total_w, 18), section)
            y += 28
        if i % 2:
            p.fillRect(QRectF(0, y, total_w, heights[i]), _shade(background))
        p.setPen(ink)
        p.setFont(small)
        p.drawText(
            QRectF(PAD, y, LABEL_W - 2 * PAD, heights[i]),
            Qt.AlignmentFlag.AlignVCenter | wrap,
            row["label"],
        )
        for qt in columns:
            left = xs[qt]
            for name in ("qslider", "range"):
                image = images[qt, i, name]
                if image is not None:
                    size = image.deviceIndependentSize()
                    top = y + (heights[i] - size.height()) / 2
                    p.drawImage(QRectF(left, top, size.width(), size.height()), image)
                elif name == "range" or row["reference"]:
                    p.setPen(faint)
                    p.drawText(
                        QRectF(left, y, 120, heights[i]),
                        Qt.AlignmentFlag.AlignVCenter,
                        "(not rendered)",
                    )
                left += width[qt, "qslider"] + PAD
        y += heights[i]
    p.end()
    sheet.save(str(path))
    print(path)


def _background(images: dict) -> QColor:
    for image in images.values():
        if image is not None:
            return image.pixelColor(0, 0)
    return QColor("white")


def _shade(color: QColor) -> QColor:
    return color.lighter(108) if color.lightness() < 128 else color.darker(104)


if __name__ == "__main__":
    command, *args = sys.argv[1:]
    if command == "render":
        render(Path(args[0]), napari="--napari" in args)
    elif command == "compose":
        compose(Path(args[0]), Path(args[1]))
    else:
        sys.exit(__doc__)
