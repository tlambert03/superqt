from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING, Callable, ClassVar, Protocol, cast

from qtpy.QtCore import QEvent, QObject
from qtpy.QtGui import QColor, QGuiApplication, QIcon, QPalette

if TYPE_CHECKING:
    from typing import Literal

    Flip = Literal["horizontal", "vertical", "horizontal,vertical"]
    Rotation = Literal["90", "180", "270", 90, 180, 270, "-90", 1, 2, 3]

    class SupportsIcon(Protocol):
        def icon(self) -> QIcon:
            """Return the current icon."""

        def setIcon(self, icon: QIcon) -> None:
            """Set the icon."""

        def installEventFilter(self, a0: QObject | None) -> None:
            """Install an event filter on this object."""

    # these are Qt classes that support icons
    # QtWidgets.QListWidgetItem
    # QtWidgets.QTableWidgetItem
    # QtWidgets.QMenu
    # QtWidgets.QSystemTrayIcon
    # QtWidgets.QAbractButton
    # QtGui.QAction
    # QtGui.QWindow
    # QtGui.QStandardItem


class QIconifyIcon(QIcon):
    """QIcon backed by an iconify icon.

    Iconify includes 150,000+ icons from most major icon sets including Bootstrap,
    FontAwesome, Material Design, and many more.

    Search availble icons at https://icon-sets.iconify.design
    Once you find one you like, use the key in the format `"prefix:name"` to create an
    icon:  `QIconifyIcon("bi:bell")`.

    This class is a thin wrapper around the
    [pyconify](https://github.com/pyapp-kit/pyconify) `svg_path` function. It pulls SVGs
    from iconify, creates a temporary SVG file and uses it as the source for a QIcon.
    SVGs are cached to disk, and persist across sessions (until `pyconify.clear_cache()`
    is called).

    Parameters
    ----------
    *key: str
        Icon set prefix and name. May be passed as a single string in the format
        `"prefix:name"` or as two separate strings: `'prefix', 'name'`.
    color : str, optional
        Icon color. If not provided, the icon will appear black (the icon fill color
        will be set to the string "currentColor").
    flip : str, optional
        Flip icon.  Must be one of "horizontal", "vertical", "horizontal,vertical"
    rotate : str | int, optional
        Rotate icon. Must be one of 0, 90, 180, 270,
        or 0, 1, 2, 3 (equivalent to 0, 90, 180, 270, respectively)
    dir : str, optional
        If 'dir' is not None, the file will be created in that directory, otherwise a
        default
        [directory](https://docs.python.org/3/library/tempfile.html#tempfile.mkstemp) is
        used.

    Examples
    --------
    >>> from qtpy.QtWidgets import QPushButton
    >>> from superqt import QIconifyIcon
    >>> btn = QPushButton()
    >>> icon = QIconifyIcon("bi:alarm-fill", color="red", rotate=90)
    >>> btn.setIcon(icon)
    """

    _CACHE_KEYS: ClassVar[dict[int, tuple]] = {}

    def __init__(
        self,
        *key: str,
        color: str | None = None,
        flip: Flip | None = None,
        rotate: Rotation | None = None,
        dir: str | None = None,
    ):
        try:
            from pyconify import svg_path
        except ModuleNotFoundError as e:  # pragma: no cover
            raise ImportError(
                "pyconify is required to use QIconifyIcon. "
                "Please install it with `pip install pyconify` or use the "
                "`pip install superqt[iconify]` extra."
            ) from e
        self._name = key[0] if len(key) == 1 else ":".join(key)
        self.path = svg_path(*key, color=color, flip=flip, rotate=rotate, dir=dir)
        super().__init__(str(self.path))
        self._args = (self._name, color, flip, rotate)
        QIconifyIcon._CACHE_KEYS[self.cacheKey()] = self._args

    def name(self) -> str:
        """Return the iconify `prefix:icon` represented by this QIcon."""
        return self._name

    @classmethod
    def fromQIcon(
        cls,
        icon: QIcon,
        color: str | None = None,
        flip: Flip | None = None,
        rotate: Rotation | None = None,
    ) -> QIconifyIcon:
        """Return a QIconifyIcon instance from a cache key."""
        if (args := cls._CACHE_KEYS.get(icon.cacheKey())) is None:
            raise ValueError(f"Icon {icon} was not created as a QIconifyIcon.")
        name_, color_, flip_, rotate_ = args
        color = color or color_
        flip = flip or flip_
        rotate = rotate or rotate_
        return cls(name_, color=color, flip=flip, rotate=rotate)

    @staticmethod
    def installPaletteEventFilter(
        obj: SupportsIcon,
        role: QPalette.ColorRole = QPalette.ColorRole.ButtonText,
    ) -> IconifyPaletteEventFilter:
        """Install event filter on `obj` that keeps icon color in sync with palette.

        Parameters
        ----------
        obj : QObject
            The object to install the event filter on.  Must be a QObject with `icon`
            and `setIcon` methods.  And the icon must be a QIconifyIcon. If
            `obj.setIcon()` was not previously called with a QIconifyIcon, this filter
            will do nothing.
        role : QPalette.ColorRole, optional
            The palette color role to use for recoloring, by default
            `QPalette.ColorRole.ButtonText`
        parent : QObject, optional
            A parent object for the filter, by default None.

        Returns
        -------
        filter : _IconifyColorChanger
            The installed event filter. May be uninstalled with
            `obj.removeEventFilter(filter)`.
        """
        if (
            not isinstance(obj, QObject)
            or not hasattr(obj, "icon")
            or not hasattr(obj, "setIcon")
        ):
            raise TypeError(
                "Cannot install IconColorChanger event filter on object of type "
                f"{type(obj)}. It must be a QObject with `icon` and `setIcon` methods."
            )
        obj_filter = IconifyPaletteEventFilter(role, obj)
        obj.installEventFilter(obj_filter)
        return obj_filter


class IconifyPaletteEventFilter(QObject):
    def __init__(
        self,
        role: QPalette.ColorRole = QPalette.ColorRole.ButtonText,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.role = role

    def eventFilter(self, obj: QObject | None, event: QEvent | None) -> bool:
        """Change icon color when palette changes."""
        if (
            event is not None
            and event.type() == QEvent.Type.PaletteChange
            and obj is not None
            and hasattr(obj, "setIcon")
        ):
            new_color = self.getIconColor(obj)
            if new_icon := self.getNewIcon(obj, new_color):
                obj.setIcon(new_icon)
        return False

    def getIconColor(self, obj: QObject) -> QColor:
        """Return a suitable icon color for `obj`."""
        if hasattr(obj, "palette"):
            return cast("QPalette", obj.palette()).color(self.role)
        return QGuiApplication.palette().color(self.role)

    def getNewIcon(self, obj: QObject, color: QColor) -> QIcon | None:
        """Return an instance of QIcon suitable for obj using `color`."""
        if hasattr(obj, "icon"):
            icon = cast("QIcon", obj.icon())
            if isinstance(icon, QIconifyIcon):
                with suppress(ValueError):
                    return QIconifyIcon.fromQIcon(icon, color=color.name())
        return None
