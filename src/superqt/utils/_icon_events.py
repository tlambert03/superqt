from __future__ import annotations

from typing import TYPE_CHECKING, Callable, ClassVar, Protocol, cast

from qtpy.QtCore import QEvent, QObject
from qtpy.QtGui import QColor, QGuiApplication, QIcon, QPalette

if TYPE_CHECKING:
    from typing import Literal

    Flip = Literal["horizontal", "vertical", "horizontal,vertical"]
    Rotation = Literal["90", "180", "270", 90, 180, 270, "-90", 1, 2, 3]
    NewIconCallable = Callable[[QColor], QIcon]

    class SupportsIcon(Protocol):
        def icon(self) -> QIcon:
            """Return icon for this object."""

        def setIcon(self, icon: QIcon) -> None:
            """Set icon for this object."""


class IconPaletteEventFilter(QObject):
    """Event filter that updates icon color when palette changes.

    This Filter works by listening for a `QEvent.Type.PaletteChange` event on an
    object. When the event is received, if the object has icon/setIcon() methods,
    an updateIconColor() method is called to update the icon color to match the
    current palette.

    Identity of QIcon data is challenging, because almost all info about a QIcon
    subclass is lost once you call `setIcon()` and retrieve it with `icon()`. The only
    identifying information is the `cacheKey()`, which is a unique integer that changes
    only when the data underlying a `QIcon` changes by calling `addFile()`,
    `addPixmap()`, or `setIsMask()`.

    This class allows users to register a function (`Callable[[QColor], QIcon]`)

    """

    _ICON_CACHE_TO_CONSTRUCTOR: ClassVar[dict[int, NewIconCallable]] = {}

    def __init__(
        self,
        color_role: QPalette.ColorRole = QPalette.ColorRole.ButtonText,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.color_role = color_role

    def eventFilter(self, obj: QObject | None, event: QEvent | None) -> bool:
        """Update icon color when palette changes."""
        if event and event.type() == QEvent.Type.PaletteChange and obj:
            if hasattr(obj, "icon") and hasattr(obj, "setIcon"):
                self.updateIconColor(obj)
        return False

    def updateIconColor(self, obj: SupportsIcon) -> None:
        """Set icon color on `obj` to match palette."""
        if (icon := obj.icon()).isNull():
            return
        if hasattr(obj, "palette"):
            palette = cast("QPalette", obj.palette())
        else:
            palette = QGuiApplication.palette()
        if new_icon := self.getNewIcon(icon, palette.color(self.color_role)):
            obj.setIcon(new_icon)

    def getNewIcon(self, icon: QIcon, new_color: QColor) -> QIcon | None:
        """Return a new icon with `new_color` if possible, otherwise return None."""
        if make_icon := self.get_constructor(icon):
            return make_icon(new_color)
        return None

    @classmethod
    def set_constructor(cls, icon: QIcon | int, constructor: NewIconCallable) -> None:
        """Set `constructor` as the constructor for `icon`."""
        key = icon.cacheKey() if isinstance(icon, QIcon) else icon
        cls._ICON_CACHE_TO_CONSTRUCTOR[key] = constructor

    @classmethod
    def get_constructor(cls, icon: QIcon | int) -> NewIconCallable | None:
        """Get the constructor for `icon`."""
        key = icon.cacheKey() if isinstance(icon, QIcon) else icon
        return cls._ICON_CACHE_TO_CONSTRUCTOR.get(key)
