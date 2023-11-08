from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, ClassVar

from qtpy.QtCore import QEvent, QObject, QSize
from qtpy.QtGui import QColor, QGuiApplication, QIcon, QPalette

if TYPE_CHECKING:
    from typing import Literal

    Flip = Literal["horizontal", "vertical", "horizontal,vertical"]
    Rotation = Literal["90", "180", "270", 90, 180, 270, "-90", 1, 2, 3]
    NewIconCallable = Callable[[QColor], QIcon | None]

try:
    from pyconify import svg_path
except ModuleNotFoundError:  # pragma: no cover
    svg_path = None


class PaletteIconEventFilter(QObject):
    _ICON_CACHE_TO_CONSTRUTOR: ClassVar[dict[int, NewIconCallable]] = {}

    def eventFilter(self, obj: QObject | None, event: QEvent | None) -> bool:
        """Update icon color when palette changes."""
        if event and event.type() == QEvent.Type.PaletteChange and obj:
            self.updateIconColor(obj)
        return False

    def updateIconColor(self, obj: QObject) -> None:
        """Set icon color on `obj` to match palette."""
        if hasattr(obj, "icon") and hasattr(obj, "setIcon"):
            palette = (
                obj.palette() if hasattr(obj, "palette") else QGuiApplication.palette()
            )
            if make_icon := self.get_constructor(obj.icon()):
                new_color = palette.color(QPalette.ColorRole.ButtonText)
                if new_icon := make_icon(new_color):
                    obj.setIcon(new_icon)

    @classmethod
    def set_constructor(cls, icon: QIcon, constructor: NewIconCallable) -> None:
        """Set `constructor` as the constructor for `icon`."""
        print("set", icon.cacheKey())
        cls._ICON_CACHE_TO_CONSTRUTOR[icon.cacheKey()] = constructor

    @classmethod
    def get_constructor(cls, icon: QIcon) -> NewIconCallable | None:
        """Get the constructor for `icon`."""
        print("get", icon.cacheKey())
        return cls._ICON_CACHE_TO_CONSTRUTOR.get(icon.cacheKey())


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

    Parameters are the same as `QIconifyIcon.addKey`, which can be used to add
    additional icons for various modes and states to the same QIcon.

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

    def __init__(
        self,
        *key: str,
        color: str | None = None,
        flip: Flip | None = None,
        rotate: Rotation | None = None,
        dir: str | None = None,
    ):
        if svg_path is None:  # pragma: no cover
            raise ModuleNotFoundError(
                "pyconify is required to use QIconifyIcon. "
                "Please install it with `pip install pyconify` or use the "
                "`pip install superqt[iconify]` extra."
            )
        super().__init__()
        if key:
            self.addKey(*key, color=color, flip=flip, rotate=rotate, dir=dir)

    def addKey(
        self,
        *key: str,
        color: str | None = None,
        flip: Flip | None = None,
        rotate: Rotation | None = None,
        dir: str | None = None,
        mode: QIcon.Mode = QIcon.Mode.Normal,
        state: QIcon.State = QIcon.State.Off,
    ) -> None:
        """Add an icon to this QIcon.

        This is a variant of `QIcon.addFile` that uses an iconify icon keys and
        arguments instead of a file path.

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
            Rotate icon. Must be one of 0, 90, 180, 270, or 0, 1, 2, 3 (equivalent to 0,
            90, 180, 270, respectively)
        dir : str, optional
            If 'dir' is not None, the file will be created in that directory, otherwise
            a default
            [directory](https://docs.python.org/3/library/tempfile.html#tempfile.mkstemp)
            is used.
        size : QSize, optional
            Size specified for the icon, passed to `QIcon.addFile`.
        mode : QIcon.Mode, optional
            Mode specified for the icon, passed to `QIcon.addFile`.
        state : QIcon.State, optional
            State specified for the icon, passed to `QIcon.addFile`.
        """
        previous_constructor = PaletteIconEventFilter.get_constructor(self)
        kwargs = {"color": color, "flip": flip, "rotate": rotate, "dir": dir}
        self._add_file(key, mode, state, **kwargs)
        self._store_key(key, previous_constructor, **kwargs)

    def _add_file(
        self,
        key: tuple[str, ...],
        mode: QIcon.Mode = QIcon.Mode.Normal,
        state: QIcon.State = QIcon.State.Off,
        **kwargs: Any,
    ) -> None:
        self.addFile(str(svg_path(*key, **kwargs)), QSize(), mode, state)

    def _store_key(
        self,
        key: tuple[str, ...],
        previous_constructor: NewIconCallable | None = None,
        **kwargs: Any,
    ) -> None:
        def make_new(qcolor: QColor) -> QIcon | None:
            print("make new for", self.cacheKey(), qcolor.name())
            icon = (
                QIconifyIcon()
                if previous_constructor is None
                else previous_constructor(qcolor)
            )
            if addKey := getattr(icon, "addKey", None):
                kwargs.setdefault("color", qcolor.name())
                addKey(*key, **kwargs)
            return icon

        PaletteIconEventFilter.set_constructor(self, make_new)
